from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import pendulum
from dbos import DBOS
from dbos._utils import GlobalParams
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key, require_admin, require_scope_or_admin
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
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.notes.models import Note, Rating
from src.simulation.analysis import (
    compute_agent_profiles,
    compute_detailed_notes,
    compute_full_analysis,
    compute_request_variance,
    compute_timeline,
)
from src.simulation.constants import PROGRESS_CACHE_KEY_PREFIX, PROGRESS_CACHE_TTL_SECONDS
from src.simulation.models import SimAgentInstance, SimulationOrchestrator, SimulationRun
from src.simulation.restart import restartable_agents_filter, snapshot_restart_state
from src.simulation.schemas import (
    AnalysisResource,
    AnalysisResponse,
    DetailedAnalysisMeta,
    DetailedAnalysisResponse,
    DetailedNoteResource,
    RequestVarianceMeta,
    TimelineResource,
    TimelineResponse,
)
from src.simulation.workflows.orchestrator_workflow import (
    dispatch_orchestrator,
)
from src.users.models import User

logger = get_logger(__name__)

SCORING_PERSISTENCE_FAILURE_MESSAGE = "Required scoring snapshot persistence failed"

router = APIRouter()

VALID_PAUSE_FROM = {"running"}
VALID_RESUME_FROM = {"pending", "paused", "failed", "cancelled"}
VALID_CANCEL_FROM = {"pending", "running", "paused"}
TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


async def _cancel_turn_workflows(simulation_id: UUID, db: AsyncSession) -> int:
    try:
        result = await db.execute(
            select(SimAgentInstance.id).where(SimAgentInstance.simulation_run_id == simulation_id)
        )
        agent_ids = [str(row[0]) for row in result.all()]
        if not agent_ids:
            return 0

        list_tasks = [
            asyncio.to_thread(
                DBOS.list_workflows,
                workflow_id_prefix=f"turn-{agent_id}-",
                status=["ENQUEUED", "PENDING"],
                load_input=False,
                load_output=False,
            )
            for agent_id in agent_ids
        ]
        list_results = await asyncio.gather(*list_tasks, return_exceptions=True)

        all_workflow_ids: list[str] = []
        for r in list_results:
            if isinstance(r, BaseException):
                logger.warning(
                    "Failed to list workflows for agent (non-fatal)",
                    extra={"simulation_id": str(simulation_id), "error": str(r)},
                )
                continue
            for wf in r:
                all_workflow_ids.append(wf.workflow_id)

        if not all_workflow_ids:
            return 0

        cancel_tasks = [
            asyncio.to_thread(DBOS.cancel_workflow, wf_id) for wf_id in all_workflow_ids
        ]
        cancel_results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

        cancelled = 0
        for wf_id, cr in zip(all_workflow_ids, cancel_results, strict=True):
            if isinstance(cr, BaseException):
                logger.warning(
                    "Failed to cancel workflow (non-fatal)",
                    extra={"simulation_id": str(simulation_id), "workflow_id": wf_id},
                )
            else:
                cancelled += 1

        logger.info(
            "Cancelled turn workflows",
            extra={"simulation_id": str(simulation_id), "cancelled": cancelled},
        )
        return cancelled
    except Exception:
        logger.warning(
            "Failed to cancel turn workflows (non-fatal)",
            extra={"simulation_id": str(simulation_id)},
            exc_info=True,
        )
        return 0


class ResumeAttributes(StrictInputSchema):
    reset_turns: bool = False


class ResumeData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = "simulations"
    attributes: ResumeAttributes


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: ResumeData


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
    restart_count: int = 0
    cumulative_turns: int = 0
    is_public: bool = False
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


class CancelWorkflowsResponse(SQLAlchemySchema):
    simulation_id: str
    dry_run: bool
    generation: int | None = None
    workflow_ids: list[str]
    total: int
    cancelled: int
    errors: list[str] = []


def _sanitize_public_simulation_error_message(error_message: str | None) -> str | None:
    if error_message is None:
        return None
    if error_message == SCORING_PERSISTENCE_FAILURE_MESSAGE or error_message.startswith(
        f"{SCORING_PERSISTENCE_FAILURE_MESSAGE}:"
    ):
        return SCORING_PERSISTENCE_FAILURE_MESSAGE
    return error_message


def simulation_run_to_resource(
    run: SimulationRun, *, sanitize_error_message: bool = False
) -> SimulationResource:
    error_message = (
        _sanitize_public_simulation_error_message(run.error_message)
        if sanitize_error_message
        else run.error_message
    )

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
            error_message=error_message,
            restart_count=run.restart_count,
            cumulative_turns=run.cumulative_turns,
            is_public=run.is_public,
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
    is_public: bool | None = Query(None, alias="filter[is_public]"),
) -> JSONResponse:
    scoped = require_scope_or_admin(current_user, request, "simulations:read")
    if scoped:
        is_public = True

    try:
        base_filter: list[ColumnElement[bool]] = [SimulationRun.deleted_at.is_(None)]
        if is_public is not None:
            base_filter.append(SimulationRun.is_public == is_public)

        count_query = select(func.count(SimulationRun.id)).where(*base_filter)
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page_number - 1) * page_size
        query = (
            select(SimulationRun)
            .where(*base_filter)
            .order_by(desc(SimulationRun.created_at))
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(query)
        runs = result.scalars().all()

        resources = [simulation_run_to_resource(run, sanitize_error_message=scoped) for run in runs]

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
    scoped = require_scope_or_admin(current_user, request, "simulations:read")

    try:
        filters = [
            SimulationRun.id == simulation_id,
            SimulationRun.deleted_at.is_(None),
        ]
        if scoped:
            filters.append(SimulationRun.is_public == True)

        result = await db.execute(select(SimulationRun).where(*filters))
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        resource = simulation_run_to_resource(run, sanitize_error_message=scoped)
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

        await _cancel_turn_workflows(simulation_id, db)

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


async def _cancel_orphaned_workflows(workflows: list[Any]) -> None:
    cancel_tasks = [asyncio.to_thread(DBOS.cancel_workflow, wf.workflow_id) for wf in workflows]
    results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
    for wf, result in zip(workflows, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "Failed to cancel orphaned workflow",
                extra={"workflow_id": wf.workflow_id},
            )


async def _check_orchestrator_workflows(
    simulation_id: UUID,
) -> tuple[bool, bool]:
    wf_prefix = f"orchestrator-{simulation_id}"
    active_workflows = await asyncio.wait_for(
        asyncio.to_thread(
            DBOS.list_workflows,
            workflow_id_prefix=wf_prefix,
            status=["ENQUEUED", "PENDING"],
            load_input=False,
            load_output=False,
        ),
        timeout=10.0,
    )
    if len(active_workflows) == 0:
        return True, False

    current_app_version = GlobalParams.app_version
    if not current_app_version:
        logger.warning(
            "DBOS app_version is empty — skipping orphan detection",
            extra={"simulation_run_id": str(simulation_id)},
        )
        return False, False

    matching_workflows = [wf for wf in active_workflows if wf.app_version == current_app_version]
    orphaned = [wf for wf in active_workflows if wf.app_version != current_app_version]

    if orphaned:
        if not matching_workflows:
            logger.warning(
                "Orphaned orchestrator workflows detected (app version mismatch)",
                extra={
                    "simulation_run_id": str(simulation_id),
                    "orphaned_count": len(orphaned),
                    "old_app_versions": list({wf.app_version for wf in orphaned}),
                    "current_app_version": current_app_version,
                },
            )
        await _cancel_orphaned_workflows(orphaned)

    needs_redispatch = len(matching_workflows) == 0
    return needs_redispatch, False


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
    body: ResumeRequest | None = None,
) -> JSONResponse:
    require_admin(current_user)
    reset_turns = body.data.attributes.reset_turns if body else False
    start_time = time.monotonic()
    logger.info(
        "Resume simulation started",
        extra={
            "simulation_run_id": str(simulation_id),
            "reset_turns": reset_turns,
        },
    )

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

        valid_from = VALID_RESUME_FROM | ({"completed"} if reset_turns else set())
        if not reset_turns:
            valid_from = valid_from - {"cancelled"}
        if run.status not in valid_from:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Cannot resume simulation in '{run.status}' status "
                f"(must be one of: {', '.join(sorted(valid_from))})",
            )

        needs_redispatch = False
        dbos_check_failed = False
        try:
            needs_redispatch, dbos_check_failed = await _check_orchestrator_workflows(simulation_id)
        except TimeoutError:
            logger.warning(
                "DBOS list_workflows timed out",
                extra={"simulation_run_id": str(simulation_id)},
            )
            dbos_check_failed = True
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

        if run.status in ("failed", "cancelled"):
            update_values["error_message"] = None
            update_values["completed_at"] = None

        if reset_turns:
            agents_result = await db.execute(
                select(func.coalesce(func.sum(SimAgentInstance.turn_count), 0)).where(
                    restartable_agents_filter(simulation_id)
                )
            )
            current_total_turns = agents_result.scalar_one()

            snapshot = await snapshot_restart_state(db, simulation_id)

            await db.execute(
                update(SimAgentInstance)
                .where(restartable_agents_filter(simulation_id))
                .values(
                    cumulative_turn_count=SimAgentInstance.cumulative_turn_count
                    + SimAgentInstance.turn_count,
                    turn_count=0,
                    state="active",
                    removal_reason=None,
                    deleted_at=None,
                    retry_count=0,
                )
            )

            update_values["restart_count"] = run.restart_count + 1
            update_values["cumulative_turns"] = run.cumulative_turns + current_total_turns
            update_values["current_config_id"] = snapshot.config_id
            update_values["completed_at"] = None
            update_values["error_message"] = None
            needs_redispatch = True

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

        elapsed = time.monotonic() - start_time
        logger.info(
            "Resume simulation completed",
            extra={
                "simulation_run_id": str(simulation_id),
                "elapsed_seconds": round(elapsed, 3),
                "needs_redispatch": needs_redispatch,
            },
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        elapsed = time.monotonic() - start_time
        logger.exception(
            "Failed to resume simulation",
            extra={
                "simulation_run_id": str(simulation_id),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
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

        await _cancel_turn_workflows(simulation_id, db)

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


@router.post(
    "/simulations/{simulation_id}/cancel-workflows",
    response_class=JSONResponse,
    response_model=CancelWorkflowsResponse,
)
async def cancel_simulation_workflows(
    simulation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    dry_run: bool = False,
    generation: int | None = None,
) -> JSONResponse:
    """Cancel DBOS turn workflows for a simulation.

    This is an operational/debugging endpoint that returns plain JSON
    (not JSON:API format) for ease of scripting and monitoring.
    """
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

        result = await db.execute(
            select(SimAgentInstance.id).where(SimAgentInstance.simulation_run_id == simulation_id)
        )
        agent_ids = [str(row[0]) for row in result.all()]

        if not agent_ids:
            resp = CancelWorkflowsResponse(
                simulation_id=str(simulation_id),
                dry_run=dry_run,
                generation=generation,
                workflow_ids=[],
                total=0,
                cancelled=0,
            )
            return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

        list_tasks = [
            asyncio.to_thread(
                DBOS.list_workflows,
                workflow_id_prefix=(
                    f"turn-{agent_id}-gen{generation}-"
                    if generation is not None
                    else f"turn-{agent_id}-"
                ),
                status=["ENQUEUED", "PENDING"],
                load_input=False,
                load_output=False,
            )
            for agent_id in agent_ids
        ]
        list_results = await asyncio.gather(*list_tasks, return_exceptions=True)

        workflow_ids: list[str] = []
        for r in list_results:
            if isinstance(r, BaseException):
                logger.warning(
                    "Failed to list workflows for agent",
                    extra={"simulation_id": str(simulation_id), "error": str(r)},
                )
                continue
            for wf in r:
                workflow_ids.append(wf.workflow_id)

        cancelled = 0
        errors: list[str] = []
        if not dry_run and workflow_ids:
            cancel_tasks = [
                asyncio.to_thread(DBOS.cancel_workflow, wf_id) for wf_id in workflow_ids
            ]
            cancel_results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
            for wf_id, cr in zip(workflow_ids, cancel_results, strict=True):
                if isinstance(cr, BaseException):
                    errors.append(f"{wf_id}: {cr}")
                else:
                    cancelled += 1

        logger.info(
            "Cancel-workflows endpoint completed",
            extra={
                "simulation_id": str(simulation_id),
                "dry_run": dry_run,
                "generation": generation,
                "total": len(workflow_ids),
                "cancelled": cancelled,
                "errors": len(errors),
            },
        )

        resp = CancelWorkflowsResponse(
            simulation_id=str(simulation_id),
            dry_run=dry_run,
            generation=generation,
            workflow_ids=workflow_ids,
            total=len(workflow_ids),
            cancelled=cancelled,
            errors=errors,
        )
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    except Exception:
        logger.exception("Failed to cancel simulation workflows")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to cancel simulation workflows",
        )


@router.post(
    "/simulations/{simulation_id}/publish",
    response_class=JSONResponse,
    response_model=SimulationSingleResponse,
)
async def publish_simulation(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationRun)
            .where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
            .with_for_update()
        )
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        now = pendulum.now("UTC")
        await db.execute(
            update(SimulationRun)
            .where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
            .values(is_public=True, updated_at=now)
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
        logger.exception("Failed to publish simulation")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to publish simulation",
        )


@router.post(
    "/simulations/{simulation_id}/unpublish",
    response_class=JSONResponse,
    response_model=SimulationSingleResponse,
)
async def unpublish_simulation(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationRun)
            .where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
            .with_for_update()
        )
        run = result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        now = pendulum.now("UTC")
        await db.execute(
            update(SimulationRun)
            .where(
                SimulationRun.id == simulation_id,
                SimulationRun.deleted_at.is_(None),
            )
            .values(is_public=False, updated_at=now)
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
        logger.exception("Failed to unpublish simulation")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to unpublish simulation",
        )


@router.get(
    "/simulations/{simulation_id}/progress",
    response_class=JSONResponse,
    response_model=ProgressResponse,
)
async def get_simulation_progress(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    scoped = require_scope_or_admin(current_user, request, "simulations:read")

    try:
        if scoped:
            run_check = await db.execute(
                select(SimulationRun.is_public).where(
                    SimulationRun.id == simulation_id,
                    SimulationRun.deleted_at.is_(None),
                )
            )
            is_public = run_check.scalar_one_or_none()
            if is_public is None or not is_public:
                return create_error_response(
                    status.HTTP_404_NOT_FOUND,
                    "Not Found",
                    f"SimulationRun {simulation_id} not found",
                )

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
    scoped = require_scope_or_admin(current_user, request, "simulations:read")

    try:
        filters = [
            SimulationRun.id == simulation_id,
            SimulationRun.deleted_at.is_(None),
        ]
        if scoped:
            filters.append(SimulationRun.is_public == True)

        run_result = await db.execute(select(SimulationRun).where(*filters))
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
            inst_id = profile_to_instance.get(note.author_id)
            if inst_id is None:
                logger.warning(
                    "No agent instance mapping for author profile",
                    extra={
                        "author_id": str(note.author_id),
                        "note_id": str(note.id),
                        "simulation_id": str(simulation_id),
                    },
                )
            resources.append(
                ResultNoteResource(
                    id=str(note.id),
                    attributes=ResultNoteAttributes(
                        note_id=str(note.id),
                        summary=note.summary,
                        classification=note.classification,
                        note_status=note.status,
                        author_profile_id=str(note.author_id),
                        agent_instance_id=str(inst_id) if inst_id is not None else "",
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


@router.get(
    "/simulations/{simulation_id}/analysis",
    response_class=JSONResponse,
    response_model=AnalysisResponse,
)
async def get_simulation_analysis(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    scoped = require_scope_or_admin(current_user, request, "simulations:read")

    try:
        filters = [
            SimulationRun.id == simulation_id,
            SimulationRun.deleted_at.is_(None),
        ]
        if scoped:
            filters.append(SimulationRun.is_public == True)

        run_result = await db.execute(select(SimulationRun).where(*filters))
        run = run_result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        analysis = await compute_full_analysis(simulation_id, db)

        response = AnalysisResponse(
            data=AnalysisResource(
                id=str(simulation_id),
                attributes=analysis,
            ),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get simulation analysis")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get simulation analysis",
        )


@router.get(
    "/simulations/{simulation_id}/analysis/detailed",
    response_class=JSONResponse,
    response_model=DetailedAnalysisResponse,
)
async def get_simulation_detailed_analysis(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    sort_by: Literal["count", "has_score"] = Query("count", alias="sort_by"),
    filter_classification: list[str] = Query([], alias="filter[classification]"),
    filter_status: list[str] = Query([], alias="filter[status]"),
) -> JSONResponse:
    scoped = require_scope_or_admin(current_user, request, "simulations:read")

    try:
        filters = [
            SimulationRun.id == simulation_id,
            SimulationRun.deleted_at.is_(None),
        ]
        if scoped:
            filters.append(SimulationRun.is_public == True)

        run_result = await db.execute(select(SimulationRun).where(*filters))
        run = run_result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        offset = (page_number - 1) * page_size
        detailed_notes, total = await compute_detailed_notes(
            simulation_id,
            db,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            filter_classification=filter_classification or None,
            filter_status=filter_status or None,
        )

        if page_number == 1:
            request_variance = await compute_request_variance(simulation_id, db)
            variance_meta = RequestVarianceMeta(
                requests=request_variance,
                total_requests=len(request_variance),
            )
            agent_profiles = await compute_agent_profiles(simulation_id, db)
        else:
            variance_meta = RequestVarianceMeta()
            agent_profiles = []

        resources = [
            DetailedNoteResource(id=note.note_id, attributes=note) for note in detailed_notes
        ]

        base_url = str(request.url).split("?")[0]
        links = create_pagination_links(
            base_url=base_url,
            page=page_number,
            size=page_size,
            total=total,
        )

        meta = DetailedAnalysisMeta(
            count=total,
            request_variance=variance_meta,
            agents=agent_profiles,
        )

        response = DetailedAnalysisResponse(
            data=resources,
            links=links,
            meta=meta,
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get detailed simulation analysis")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get detailed simulation analysis",
        )


@router.get(
    "/simulations/{simulation_id}/analysis/timeline",
    response_class=JSONResponse,
    response_model=TimelineResponse,
)
async def get_simulation_timeline(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    bucket_size: Literal["auto", "minute", "hour"] = Query("auto"),
) -> JSONResponse:
    scoped = require_scope_or_admin(current_user, request, "simulations:read")

    try:
        filters = [
            SimulationRun.id == simulation_id,
            SimulationRun.deleted_at.is_(None),
        ]
        if scoped:
            filters.append(SimulationRun.is_public == True)

        run_result = await db.execute(select(SimulationRun).where(*filters))
        run = run_result.scalar_one_or_none()

        if not run:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationRun {simulation_id} not found",
            )

        timeline = await compute_timeline(simulation_id, db, bucket_size)

        response = TimelineResponse(
            data=TimelineResource(
                id=str(simulation_id),
                attributes=timeline,
            ),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get simulation timeline")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get simulation timeline",
        )
