from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key, require_admin
from src.cache.redis_client import redis_client
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
    JSONAPIMeta,
    create_pagination_links,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.database import get_db
from src.dbos_workflows.config import get_dbos_client
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.notes.models import Note, Rating
from src.simulation.constants import PROGRESS_CACHE_KEY_PREFIX, PROGRESS_CACHE_TTL_SECONDS
from src.simulation.models import SimAgentInstance, SimulationOrchestrator, SimulationRun
from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()

VALID_PAUSE_FROM = {"running"}
VALID_RESUME_FROM = {"paused", "failed"}
VALID_CANCEL_FROM = {"pending", "running", "paused"}
TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


class SimulationCreateAttributes(StrictInputSchema):
    orchestrator_id: UUID
    community_server_id: UUID


class SimulationCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["simulations"] = Field(..., description="Resource type must be 'simulations'")
    attributes: SimulationCreateAttributes


class SimulationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: SimulationCreateData


class SimulationAttributes(SQLAlchemySchema):
    orchestrator_id: str
    community_server_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    paused_at: datetime | None = None
    metrics: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SimulationResource(BaseModel):
    type: str = "simulations"
    id: str
    attributes: SimulationAttributes


class SimulationSingleResponse(SQLAlchemySchema):
    data: SimulationResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class SimulationListResponse(SQLAlchemySchema):
    data: list[SimulationResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class ProgressAttributes(SQLAlchemySchema):
    turns_completed: int = 0
    turns_errored: int = 0
    notes_written: int = 0
    ratings_given: int = 0
    active_agents: int = 0


class ProgressResource(BaseModel):
    type: str = "simulation-progress"
    id: str
    attributes: ProgressAttributes


class ProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    data: ProgressResource
    jsonapi: dict[str, str] = {"version": "1.1"}


class ResultNoteAttributes(SQLAlchemySchema):
    note_id: str
    summary: str
    classification: str
    note_status: str
    author_profile_id: str
    agent_instance_id: str
    created_at: datetime | None = None


class ResultNoteResource(BaseModel):
    type: str = "simulation-result-notes"
    id: str
    attributes: ResultNoteAttributes


class ResultsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    data: list[ResultNoteResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


def simulation_run_to_resource(run: SimulationRun) -> SimulationResource:
    return SimulationResource(
        type="simulations",
        id=str(run.id),
        attributes=SimulationAttributes(
            orchestrator_id=str(run.orchestrator_id),
            community_server_id=str(run.community_server_id),
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            paused_at=run.paused_at,
            metrics=run.metrics,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        ),
    )


def create_error_response(
    status_code: int,
    title: str,
    detail: str | None = None,
) -> JSONResponse:
    error_response = create_error_response_model(
        status_code=status_code,
        title=title,
        detail=detail,
    )
    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(by_alias=True),
        media_type=JSONAPI_CONTENT_TYPE,
    )


@router.post(
    "/simulations",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=SimulationSingleResponse,
)
async def create_simulation(
    request: HTTPRequest,
    body: SimulationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        attrs = body.data.attributes

        orch_result = await db.execute(
            select(SimulationOrchestrator).where(
                SimulationOrchestrator.id == attrs.orchestrator_id,
                SimulationOrchestrator.deleted_at.is_(None),
            )
        )
        orchestrator = orch_result.scalar_one_or_none()

        if not orchestrator:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationOrchestrator {attrs.orchestrator_id} not found",
            )

        cs_result = await db.execute(
            select(CommunityServer).where(
                CommunityServer.id == attrs.community_server_id,
                CommunityServer.is_active.is_(True),
            )
        )
        community_server = cs_result.scalar_one_or_none()

        if not community_server:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server {attrs.community_server_id} not found",
            )

        if community_server.platform != "playground":
            return create_error_response(
                422,
                "Validation Error",
                f"Community server {attrs.community_server_id} is not a playground community",
            )

        simulation_run = SimulationRun(
            orchestrator_id=attrs.orchestrator_id,
            community_server_id=attrs.community_server_id,
            status="pending",
        )
        db.add(simulation_run)
        await db.commit()
        await db.refresh(simulation_run)

        try:
            await dispatch_orchestrator(simulation_run.id)
        except Exception:
            logger.exception(
                "Failed to dispatch orchestrator workflow",
                extra={"simulation_run_id": str(simulation_run.id)},
            )
            now = pendulum.now("UTC")
            await db.execute(
                update(SimulationRun)
                .where(SimulationRun.id == simulation_run.id)
                .values(
                    status="failed",
                    error_message="Failed to dispatch orchestrator workflow",
                    completed_at=now,
                    updated_at=now,
                )
            )
            await db.commit()
            await db.refresh(simulation_run)

            resource = simulation_run_to_resource(simulation_run)
            response = SimulationSingleResponse(
                data=resource,
                links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{simulation_run.id}"),
            )

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response.model_dump(by_alias=True, mode="json"),
                media_type=JSONAPI_CONTENT_TYPE,
            )

        resource = simulation_run_to_resource(simulation_run)
        response = SimulationSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{simulation_run.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create simulation")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create simulation",
        )


@router.get(
    "/simulations",
    response_class=JSONResponse,
    response_model=SimulationListResponse,
)
async def list_simulations(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
) -> JSONResponse:
    require_admin(current_user)

    try:
        count_query = select(func.count(SimulationRun.id)).where(SimulationRun.deleted_at.is_(None))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page_number - 1) * page_size
        query = (
            select(SimulationRun)
            .where(SimulationRun.deleted_at.is_(None))
            .order_by(desc(SimulationRun.created_at))
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(query)
        runs = result.scalars().all()

        resources = [simulation_run_to_resource(run) for run in runs]

        base_url = str(request.url).split("?")[0]
        links = create_pagination_links(
            base_url=base_url,
            page=page_number,
            size=page_size,
            total=total,
        )

        response = SimulationListResponse(
            data=resources,
            links=links,
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to list simulations")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list simulations",
        )


@router.get(
    "/simulations/{simulation_id}",
    response_class=JSONResponse,
    response_model=SimulationSingleResponse,
)
async def get_simulation(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationRun).where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
        )
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        resource = simulation_run_to_resource(run)
        response = SimulationSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to get simulation")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get simulation",
        )


@router.post(
    "/simulations/{simulation_id}/pause",
    response_class=JSONResponse,
    response_model=SimulationSingleResponse,
)
async def pause_simulation(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationRun).where(SimulationRun.id == simulation_id).with_for_update()
        )
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        if run.status not in VALID_PAUSE_FROM:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Cannot pause simulation in '{run.status}' status (must be 'running')",
            )

        now = pendulum.now("UTC")
        await db.execute(
            update(SimulationRun)
            .where(SimulationRun.id == simulation_id)
            .values(status="paused", paused_at=now, updated_at=now)
        )
        await db.commit()

        await db.refresh(run)
        resource = simulation_run_to_resource(run)
        response = SimulationSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to pause simulation")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to pause simulation",
        )


@router.post(
    "/simulations/{simulation_id}/resume",
    response_class=JSONResponse,
    response_model=SimulationSingleResponse,
)
async def resume_simulation(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationRun).where(SimulationRun.id == simulation_id).with_for_update()
        )
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        if run.status not in VALID_RESUME_FROM:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Cannot resume simulation in '{run.status}' status "
                f"(must be one of: {', '.join(sorted(VALID_RESUME_FROM))})",
            )

        needs_redispatch = False
        dbos_check_failed = False
        try:
            client = get_dbos_client()
            wf_prefix = f"orchestrator-{simulation_id}"
            active_workflows = await asyncio.to_thread(
                client.list_workflows,
                workflow_id_prefix=wf_prefix,
                status=["ENQUEUED", "PENDING"],
                load_input=False,
                load_output=False,
            )
            needs_redispatch = len(active_workflows) == 0
        except Exception:
            logger.error(
                "Failed to check DBOS workflow status, cannot safely resume",
                exc_info=True,
                extra={"simulation_run_id": str(simulation_id)},
            )
            dbos_check_failed = True

        if dbos_check_failed:
            return create_error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Service Unavailable",
                "Unable to verify orchestrator workflow status. Please retry.",
            )

        now = pendulum.now("UTC")
        update_values: dict[str, Any] = {
            "status": "running",
            "paused_at": None,
            "updated_at": now,
        }

        if run.status == "failed":
            update_values["error_message"] = None
            update_values["completed_at"] = None

        new_generation = run.generation
        if needs_redispatch:
            new_generation = run.generation + 1
            update_values["generation"] = new_generation

        await db.execute(
            update(SimulationRun).where(SimulationRun.id == simulation_id).values(**update_values)
        )
        await db.commit()
        await db.refresh(run)

        if needs_redispatch:
            try:
                await dispatch_orchestrator(simulation_id, generation=new_generation)
            except Exception:
                logger.exception(
                    "Failed to re-dispatch orchestrator workflow on resume",
                    extra={"simulation_run_id": str(simulation_id)},
                )
                failure_now = pendulum.now("UTC")
                await db.execute(
                    update(SimulationRun)
                    .where(SimulationRun.id == simulation_id)
                    .where(SimulationRun.status == "running")
                    .values(
                        status="failed",
                        error_message="Failed to re-dispatch orchestrator workflow",
                        completed_at=failure_now,
                        updated_at=failure_now,
                    )
                )
                await db.commit()
                return create_error_response(
                    status.HTTP_502_BAD_GATEWAY,
                    "Bad Gateway",
                    "Failed to dispatch orchestrator workflow. "
                    "The simulation has been marked as failed.",
                )

        resource = simulation_run_to_resource(run)
        response = SimulationSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to resume simulation")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to resume simulation",
        )


@router.post(
    "/simulations/{simulation_id}/cancel",
    response_class=JSONResponse,
    response_model=SimulationSingleResponse,
)
async def cancel_simulation(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationRun).where(SimulationRun.id == simulation_id).with_for_update()
        )
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        if run.status not in VALID_CANCEL_FROM:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Cannot cancel simulation in '{run.status}' status",
            )

        now = pendulum.now("UTC")
        await db.execute(
            update(SimulationRun)
            .where(SimulationRun.id == simulation_id)
            .values(status="cancelled", completed_at=now, updated_at=now)
        )
        await db.commit()

        await db.refresh(run)
        resource = simulation_run_to_resource(run)
        response = SimulationSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to cancel simulation")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to cancel simulation",
        )


@router.get(
    "/simulations/{simulation_id}/progress",
    response_class=JSONResponse,
    response_model=ProgressResponse,
)
async def get_simulation_progress(
    simulation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        cache_key = f"{PROGRESS_CACHE_KEY_PREFIX}{simulation_id}"
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return JSONResponse(
                    content=json.loads(cached),
                    media_type=JSONAPI_CONTENT_TYPE,
                )
        except Exception:
            logger.warning("Failed to read simulation progress cache", exc_info=True)

        run_result = await db.execute(
            select(SimulationRun).where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
        )
        run = run_result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        instances_result = await db.execute(
            select(SimAgentInstance).where(
                SimAgentInstance.simulation_run_id == simulation_id,
            )
        )
        instances = instances_result.scalars().all()

        turns_completed = sum(inst.turn_count for inst in instances)
        active_agents = sum(
            1 for inst in instances if inst.state == "active" and inst.deleted_at is None
        )

        user_profile_ids = [inst.user_profile_id for inst in instances]

        notes_written = 0
        ratings_given = 0
        if user_profile_ids:
            notes_count_result = await db.execute(
                select(func.count(Note.id)).where(
                    Note.author_id.in_(user_profile_ids),
                    Note.deleted_at.is_(None),
                )
            )
            notes_written = notes_count_result.scalar() or 0

            ratings_count_result = await db.execute(
                select(func.count(Rating.id)).where(
                    Rating.rater_id.in_(user_profile_ids),
                )
            )
            ratings_given = ratings_count_result.scalar() or 0

        turns_errored = 0
        if run.metrics and isinstance(run.metrics, dict):
            turns_errored = run.metrics.get("turns_errored", 0)

        progress = ProgressResponse(
            data=ProgressResource(
                id=str(simulation_id),
                attributes=ProgressAttributes(
                    turns_completed=turns_completed,
                    turns_errored=turns_errored,
                    notes_written=notes_written,
                    ratings_given=ratings_given,
                    active_agents=active_agents,
                ),
            ),
        )

        response_content = progress.model_dump(by_alias=True, mode="json")

        try:
            await redis_client.set(
                cache_key, json.dumps(response_content), ttl=PROGRESS_CACHE_TTL_SECONDS
            )
        except Exception:
            logger.warning("Failed to cache simulation progress", exc_info=True)

        return JSONResponse(
            content=response_content,
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get simulation progress")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get simulation progress",
        )


@router.get(
    "/simulations/{simulation_id}/results",
    response_class=JSONResponse,
    response_model=ResultsListResponse,
)
async def get_simulation_results(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    agent_instance_id: UUID | None = Query(None),
) -> JSONResponse:
    require_admin(current_user)

    try:
        run_result = await db.execute(
            select(SimulationRun).where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
        )
        run = run_result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        instance_query = select(SimAgentInstance).where(
            SimAgentInstance.simulation_run_id == simulation_id,
            SimAgentInstance.deleted_at.is_(None),
        )
        if agent_instance_id is not None:
            instance_query = instance_query.where(SimAgentInstance.id == agent_instance_id)

        instances_result = await db.execute(instance_query)
        instances = instances_result.scalars().all()

        profile_to_instance: dict[UUID, UUID] = {}
        for inst in instances:
            profile_to_instance[inst.user_profile_id] = inst.id

        user_profile_ids = list(profile_to_instance.keys())

        if not user_profile_ids:
            base_url = str(request.url).split("?")[0]
            links = create_pagination_links(
                base_url=base_url, page=page_number, size=page_size, total=0
            )
            resp = ResultsListResponse(data=[], links=links, meta=JSONAPIMeta(count=0))
            return JSONResponse(
                content=resp.model_dump(by_alias=True, mode="json"),
                media_type=JSONAPI_CONTENT_TYPE,
            )

        count_query = select(func.count(Note.id)).where(
            Note.author_id.in_(user_profile_ids),
            Note.deleted_at.is_(None),
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page_number - 1) * page_size
        notes_query = (
            select(Note)
            .where(
                Note.author_id.in_(user_profile_ids),
                Note.deleted_at.is_(None),
            )
            .order_by(desc(Note.created_at))
            .limit(page_size)
            .offset(offset)
        )
        notes_result = await db.execute(notes_query)
        notes = notes_result.scalars().all()

        resources: list[ResultNoteResource] = []
        for note in notes:
            inst_id = profile_to_instance.get(note.author_id, note.author_id)
            resources.append(
                ResultNoteResource(
                    id=str(note.id),
                    attributes=ResultNoteAttributes(
                        note_id=str(note.id),
                        summary=note.summary,
                        classification=note.classification,
                        note_status=note.status,
                        author_profile_id=str(note.author_id),
                        agent_instance_id=str(inst_id),
                        created_at=note.created_at,
                    ),
                )
            )

        base_url = str(request.url).split("?")[0]
        links = create_pagination_links(
            base_url=base_url,
            page=page_number,
            size=page_size,
            total=total,
        )

        resp = ResultsListResponse(
            data=resources,
            links=links,
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=resp.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get simulation results")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get simulation results",
        )
