from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
from src.llm_config.model_id import ModelId
from src.monitoring import get_logger
from src.simulation.models import SimAgent
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


class SimAgentCreateAttributes(StrictInputSchema):
    name: str = Field(..., min_length=1, max_length=255)
    personality: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1, max_length=100)
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str | None = None
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        try:
            ModelId.from_pydantic_ai(v)
        except ValueError:
            raise ValueError(
                f"Invalid model name '{v}'. Use 'provider:model' format "
                f"(e.g. 'openai:gpt-4o-mini', 'google-gla:gemini-2.0-flash')."
            )
        return v


class SimAgentCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sim-agents"] = Field(..., description="Resource type must be 'sim-agents'")
    attributes: SimAgentCreateAttributes


class SimAgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: SimAgentCreateData


class SimAgentUpdateAttributes(StrictInputSchema):
    name: str | None = Field(None, min_length=1, max_length=255)
    personality: str | None = Field(None, min_length=1)
    model_name: str | None = Field(None, min_length=1, max_length=100)
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str | None = None
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ModelId.from_pydantic_ai(v)
        except ValueError:
            raise ValueError(
                f"Invalid model name '{v}'. Use 'provider:model' format "
                f"(e.g. 'openai:gpt-4o-mini', 'google-gla:gemini-2.0-flash')."
            )
        return v


class SimAgentUpdateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sim-agents"] = Field(..., description="Resource type must be 'sim-agents'")
    id: str = Field(..., description="SimAgent ID")
    attributes: SimAgentUpdateAttributes


class SimAgentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: SimAgentUpdateData


class SimAgentAttributes(SQLAlchemySchema):
    name: str
    personality: str
    model_name: dict[str, str]
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("model_name", mode="before")
    @classmethod
    def parse_model_name(cls, v: Any) -> dict[str, str]:
        if isinstance(v, str):
            mid = ModelId.from_pydantic_ai(v)
            return {"provider": mid.provider, "model": mid.model}
        if isinstance(v, dict):
            return v
        msg = f"Expected str or dict for model_name, got {type(v)}"
        raise ValueError(msg)


class SimAgentResource(BaseModel):
    type: str = "sim-agents"
    id: str
    attributes: SimAgentAttributes


class SimAgentSingleResponse(SQLAlchemySchema):
    data: SimAgentResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class SimAgentListResponse(SQLAlchemySchema):
    data: list[SimAgentResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


def sim_agent_to_resource(agent: SimAgent) -> SimAgentResource:
    return SimAgentResource(
        type="sim-agents",
        id=str(agent.id),
        attributes=SimAgentAttributes(
            name=agent.name,
            personality=agent.personality,
            model_name=agent.model_name,
            model_params=agent.model_params,
            tool_config=agent.tool_config,
            memory_compaction_strategy=agent.memory_compaction_strategy,
            memory_compaction_config=agent.memory_compaction_config,
            community_server_id=str(agent.community_server_id)
            if agent.community_server_id
            else None,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
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
    "/sim-agents",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=SimAgentSingleResponse,
)
async def create_sim_agent_jsonapi(
    request: HTTPRequest,
    body: SimAgentCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        attrs = body.data.attributes
        agent = SimAgent(
            name=attrs.name,
            personality=attrs.personality,
            model_name=attrs.model_name,
            model_params=attrs.model_params,
            tool_config=attrs.tool_config,
            memory_compaction_config=attrs.memory_compaction_config,
            community_server_id=attrs.community_server_id,
        )
        if attrs.memory_compaction_strategy is not None:
            agent.memory_compaction_strategy = attrs.memory_compaction_strategy

        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        resource = sim_agent_to_resource(agent)
        response = SimAgentSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{agent.id}"),
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
            "A sim agent with that name already exists",
        )
    except Exception:
        logger.exception("Failed to create sim agent (JSON:API)")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create sim agent",
        )


@router.get(
    "/sim-agents",
    response_class=JSONResponse,
    response_model=SimAgentListResponse,
)
async def list_sim_agents_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
) -> JSONResponse:
    require_admin(current_user)

    try:
        count_query = select(func.count(SimAgent.id)).where(SimAgent.deleted_at.is_(None))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page_number - 1) * page_size
        query = (
            select(SimAgent)
            .where(SimAgent.deleted_at.is_(None))
            .order_by(desc(SimAgent.created_at))
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(query)
        agents = result.scalars().all()

        resources = [sim_agent_to_resource(agent) for agent in agents]

        base_url = str(request.url).split("?")[0]
        links = create_pagination_links(
            base_url=base_url,
            page=page_number,
            size=page_size,
            total=total,
        )

        response = SimAgentListResponse(
            data=resources,
            links=links,
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to list sim agents (JSON:API)")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list sim agents",
        )


@router.get(
    "/sim-agents/{agent_id}",
    response_class=JSONResponse,
    response_model=SimAgentSingleResponse,
)
async def get_sim_agent_jsonapi(
    agent_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimAgent).where(SimAgent.id == agent_id, SimAgent.deleted_at.is_(None))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimAgent {agent_id} not found",
            )

        resource = sim_agent_to_resource(agent)
        response = SimAgentSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception:
        logger.exception("Failed to get sim agent (JSON:API)")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get sim agent",
        )


@router.patch(
    "/sim-agents/{agent_id}",
    response_class=JSONResponse,
    response_model=SimAgentSingleResponse,
)
async def update_sim_agent_jsonapi(
    agent_id: UUID,
    request: HTTPRequest,
    body: SimAgentUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    require_admin(current_user)

    try:
        if str(agent_id) != body.data.id:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                "Resource ID in body does not match URL",
            )

        result = await db.execute(
            select(SimAgent).where(SimAgent.id == agent_id, SimAgent.deleted_at.is_(None))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimAgent {agent_id} not found",
            )

        update_data = body.data.attributes.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agent, field, value)

        await db.commit()
        await db.refresh(agent)

        resource = sim_agent_to_resource(agent)
        response = SimAgentSingleResponse(
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
            "A sim agent with that name already exists",
        )
    except Exception:
        logger.exception("Failed to update sim agent (JSON:API)")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update sim agent",
        )


@router.delete(
    "/sim-agents/{agent_id}",
)
async def delete_sim_agent_jsonapi(
    agent_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> Response:
    require_admin(current_user)

    try:
        result = await db.execute(
            select(SimAgent).where(SimAgent.id == agent_id, SimAgent.deleted_at.is_(None))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"SimAgent {agent_id} not found",
            )

        agent.soft_delete()
        await db.commit()

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception:
        logger.exception("Failed to delete sim agent (JSON:API)")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to delete sim agent",
        )
