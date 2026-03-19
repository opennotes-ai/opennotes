from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key, require_scope_or_admin
from src.common.jsonapi import JSONAPI_CONTENT_TYPE
from src.common.jsonapi import create_error_response as create_error_response_model
from src.database import get_db
from src.monitoring import get_logger
from src.simulation.models import SimAgent, SimAgentInstance, SimChannelMessage
from src.simulation.schemas import (
    SimChannelMessageAttributes,
    SimChannelMessageListMeta,
    SimChannelMessageListResponse,
    SimChannelMessageResource,
)
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


def _create_error_response(
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


@router.get(
    "/simulations/{simulation_id}/channel-messages",
    response_class=JSONResponse,
    response_model=SimChannelMessageListResponse,
)
async def list_channel_messages(
    simulation_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    before: UUID | None = Query(None),
) -> JSONResponse:
    require_scope_or_admin(current_user, request, "simulations:read")

    try:
        filters = [SimChannelMessage.simulation_run_id == simulation_id]
        if before is not None:
            filters.append(SimChannelMessage.id < before)

        query = (
            select(SimChannelMessage, SimAgent.name, SimAgent.id)
            .join(SimAgentInstance, SimChannelMessage.agent_instance_id == SimAgentInstance.id)
            .join(SimAgent, SimAgentInstance.agent_profile_id == SimAgent.id)
            .where(*filters)
            .order_by(SimChannelMessage.id.desc())
            .limit(page_size)
        )
        result = await db.execute(query)
        rows = result.all()

        rows = list(reversed(rows))

        resources = [
            SimChannelMessageResource(
                id=str(msg.id),
                attributes=SimChannelMessageAttributes(
                    message_text=msg.message_text,
                    agent_name=agent_name,
                    agent_profile_id=str(agent_id),
                    created_at=msg.created_at,
                ),
            )
            for msg, agent_name, agent_id in rows
        ]

        has_more = len(rows) == page_size

        response = SimChannelMessageListResponse(
            data=resources,
            meta=SimChannelMessageListMeta(count=len(resources), has_more=has_more),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )
    except Exception:
        logger.exception("Failed to list channel messages")
        return _create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list channel messages",
        )
