from __future__ import annotations

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

from src.auth.dependencies import get_current_user_or_api_key
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
from src.simulation.models import SimulationOrchestrator, SimulationRun
from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()

VALID_PAUSE_FROM = {"running"}
VALID_RESUME_FROM = {"paused"}
VALID_CANCEL_FROM = {"pending", "running", "paused"}
TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


def _require_admin(user: User) -> None:
    if not (user.is_superuser or user.is_service_account):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )


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
    _require_admin(current_user)

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
    _require_admin(current_user)

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
    _require_admin(current_user)

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
    _require_admin(current_user)

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
    _require_admin(current_user)

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
                f"Cannot resume simulation in '{run.status}' status (must be 'paused')",
            )

        now = pendulum.now("UTC")
        await db.execute(
            update(SimulationRun)
            .where(SimulationRun.id == simulation_id)
            .values(status="running", paused_at=None, updated_at=now)
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
    _require_admin(current_user)

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
