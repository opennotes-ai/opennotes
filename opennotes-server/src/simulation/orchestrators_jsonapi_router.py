from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key, require_admin
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
from src.monitoring import get_logger
from src.simulation.models import SimulationOrchestrator
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


class OrchestratorCreateAttributes(StrictInputSchema):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    community_server_id: UUID | None = None
    turn_cadence_seconds: int = Field(..., ge=1)
    max_agents: int = Field(..., ge=1)
    removal_rate: float = Field(..., ge=0.0, le=1.0)
    max_turns_per_agent: int = Field(..., ge=1)
    agent_profile_ids: list[str] = Field(default_factory=list)
    scoring_config: dict[str, Any] | None = None


class OrchestratorCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["simulation-orchestrators"] = Field(
        ..., description="Resource type must be 'simulation-orchestrators'"
    )
    attributes: OrchestratorCreateAttributes


class OrchestratorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: OrchestratorCreateData


class OrchestratorUpdateAttributes(StrictInputSchema):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    community_server_id: UUID | None = None
    turn_cadence_seconds: int | None = Field(None, ge=1)
    max_agents: int | None = Field(None, ge=1)
    removal_rate: float | None = Field(None, ge=0.0, le=1.0)
    max_turns_per_agent: int | None = Field(None, ge=1)
    agent_profile_ids: list[str] | None = None
    scoring_config: dict[str, Any] | None = None


class OrchestratorUpdateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["simulation-orchestrators"] = Field(
        ..., description="Resource type must be 'simulation-orchestrators'"
    )
    id: str = Field(..., description="Orchestrator ID")
    attributes: OrchestratorUpdateAttributes


class OrchestratorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: OrchestratorUpdateData


class OrchestratorAttributes(SQLAlchemySchema):
    name: str
    description: str | None = None
    community_server_id: str | None = None
    turn_cadence_seconds: int
    max_agents: int
    removal_rate: float
    max_turns_per_agent: int
    agent_profile_ids: list[str] | None = None
    scoring_config: dict[str, Any] | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OrchestratorResource(BaseModel):
    type: str = "simulation-orchestrators"
    id: str
    attributes: OrchestratorAttributes


class OrchestratorSingleResponse(SQLAlchemySchema):
    data: OrchestratorResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class OrchestratorListResponse(SQLAlchemySchema):
    data: list[OrchestratorResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


def orchestrator_to_resource(orch: SimulationOrchestrator) -> OrchestratorResource:
    return OrchestratorResource(
        type="simulation-orchestrators",
        id=str(orch.id),
        attributes=OrchestratorAttributes(
            name=orch.name,
            description=orch.description,
            community_server_id=str(orch.community_server_id) if orch.community_server_id else None,
            turn_cadence_seconds=orch.turn_cadence_seconds,
            max_agents=orch.max_agents,
            removal_rate=orch.removal_rate,
            max_turns_per_agent=orch.max_turns_per_agent,
            agent_profile_ids=orch.agent_profile_ids,
            scoring_config=orch.scoring_config,
            is_active=orch.is_active,
            created_at=orch.created_at,
            updated_at=orch.updated_at,
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
    "/simulation-orchestrators",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=OrchestratorSingleResponse,
)
async def create_orchestrator_jsonapi(
    request: HTTPRequest,
    body: OrchestratorCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        attrs = body.data.attributes
        orchestrator = SimulationOrchestrator(
            name=attrs.name,
            description=attrs.description,
            community_server_id=attrs.community_server_id,
            turn_cadence_seconds=attrs.turn_cadence_seconds,
            max_agents=attrs.max_agents,
            removal_rate=attrs.removal_rate,
            max_turns_per_agent=attrs.max_turns_per_agent,
            agent_profile_ids=attrs.agent_profile_ids,
            scoring_config=attrs.scoring_config,
        )

        db.add(orchestrator)
        await db.commit()
        await db.refresh(orchestrator)

        resource = orchestrator_to_resource(orchestrator)
        response = OrchestratorSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{orchestrator.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except IntegrityError:
        await db.rollback()
        return create_error_response(
            status.HTTP_409_CONFLICT,
            "Conflict",
            "An orchestrator with that name already exists",
        )
    except Exception:
        logger.exception("Failed to create orchestrator (JSON:API)")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create orchestrator",
        )


@router.get(
    "/simulation-orchestrators",
    response_class=JSONResponse,
    response_model=OrchestratorListResponse,
)
async def list_orchestrators_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
) -> JSONResponse:
    require_admin(current_user)

    try:
        count_query = select(func.count(SimulationOrchestrator.id)).where(
            SimulationOrchestrator.deleted_at.is_(None)
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page_number - 1) * page_size
        query = (
            select(SimulationOrchestrator)
            .where(SimulationOrchestrator.deleted_at.is_(None))
            .order_by(desc(SimulationOrchestrator.created_at))
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(query)
        orchestrators = result.scalars().all()

        resources = [orchestrator_to_resource(orch) for orch in orchestrators]

        base_url = str(request.url).split("?")[0]
        links = create_pagination_links(
            base_url=base_url,
            page=page_number,
            size=page_size,
            total=total,
        )

        response = OrchestratorListResponse(
            data=resources,
            links=links,
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to list orchestrators (JSON:API)")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list orchestrators",
        )


@router.get(
    "/simulation-orchestrators/{orchestrator_id}",
    response_class=JSONResponse,
    response_model=OrchestratorSingleResponse,
)
async def get_orchestrator_jsonapi(
    orchestrator_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationOrchestrator).where(
                SimulationOrchestrator.id == orchestrator_id,
                SimulationOrchestrator.deleted_at.is_(None),
            )
        )
        orchestrator = result.scalar_one_or_none()

        if not orchestrator:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationOrchestrator {orchestrator_id} not found",
            )

        resource = orchestrator_to_resource(orchestrator)
        response = OrchestratorSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to get orchestrator (JSON:API)")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get orchestrator",
        )


@router.patch(
    "/simulation-orchestrators/{orchestrator_id}",
    response_class=JSONResponse,
    response_model=OrchestratorSingleResponse,
)
async def update_orchestrator_jsonapi(
    orchestrator_id: UUID,
    request: HTTPRequest,
    body: OrchestratorUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        if str(orchestrator_id) != body.data.id:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                "Resource ID in body does not match URL",
            )

        result = await db.execute(
            select(SimulationOrchestrator).where(
                SimulationOrchestrator.id == orchestrator_id,
                SimulationOrchestrator.deleted_at.is_(None),
            )
        )
        orchestrator = result.scalar_one_or_none()

        if not orchestrator:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationOrchestrator {orchestrator_id} not found",
            )

        update_data = body.data.attributes.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(orchestrator, field, value)

        await db.commit()
        await db.refresh(orchestrator)

        resource = orchestrator_to_resource(orchestrator)
        response = OrchestratorSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except IntegrityError:
        await db.rollback()
        return create_error_response(
            status.HTTP_409_CONFLICT,
            "Conflict",
            "An orchestrator with that name already exists",
        )
    except Exception:
        logger.exception("Failed to update orchestrator (JSON:API)")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update orchestrator",
        )


@router.delete(
    "/simulation-orchestrators/{orchestrator_id}",
)
async def delete_orchestrator_jsonapi(
    orchestrator_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> Response:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimulationOrchestrator).where(
                SimulationOrchestrator.id == orchestrator_id,
                SimulationOrchestrator.deleted_at.is_(None),
            )
        )
        orchestrator = result.scalar_one_or_none()

        if not orchestrator:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimulationOrchestrator {orchestrator_id} not found",
            )

        orchestrator.soft_delete()
        await db.commit()

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception:
        logger.exception("Failed to delete orchestrator (JSON:API)")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to delete orchestrator",
        )
