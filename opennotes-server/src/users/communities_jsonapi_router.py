"""JSON:API v2 community-servers router.

This module implements a JSON:API 1.1 compliant endpoint for community servers.
It provides:
- Standard JSON:API response envelope structure
- Community server lookup by platform and platform_id
- Community server retrieval by ID
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import get_community_server_by_platform_id
from src.auth.dependencies import get_current_user_or_api_key
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.database import get_db
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(tags=["community-servers-jsonapi"])


class CommunityServerAttributes(BaseModel):
    """Community server attributes for JSON:API resource."""

    model_config = ConfigDict(from_attributes=True)

    platform: str
    platform_id: str
    name: str
    description: str | None = None
    is_active: bool = True
    is_public: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommunityServerResource(BaseModel):
    """JSON:API resource object for a community server."""

    type: Literal["community-servers"] = "community-servers"
    id: str
    attributes: CommunityServerAttributes


class CommunityServerSingleResponse(BaseModel):
    """JSON:API response for a single community server resource."""

    model_config = ConfigDict(from_attributes=True)

    data: CommunityServerResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def community_server_to_resource(server: CommunityServer) -> CommunityServerResource:
    """Convert a CommunityServer model to a JSON:API resource object."""
    return CommunityServerResource(
        type="community-servers",
        id=str(server.id),
        attributes=CommunityServerAttributes(
            platform=server.platform,
            platform_id=server.platform_id,
            name=server.name,
            description=server.description,
            is_active=server.is_active,
            is_public=server.is_public,
            created_at=server.created_at,
            updated_at=server.updated_at,
        ),
    )


def create_error_response(
    status_code: int,
    title: str,
    detail: str | None = None,
) -> JSONResponse:
    """Create a JSON:API formatted error response as a JSONResponse."""
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
    "/community-servers/lookup",
    response_class=JSONResponse,
    response_model=CommunityServerSingleResponse,
)
async def lookup_community_server_jsonapi(
    request: HTTPRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    platform: str = Query("discord", description="Platform type"),
    platform_id: str = Query(..., description="Platform-specific ID (e.g., Discord guild ID)"),
) -> JSONResponse:
    """Look up a community server by platform and platform ID with JSON:API format.

    Returns the internal UUID for a community server based on its platform-specific identifier.
    Auto-creates the community server if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: "discord")
        platform_id: Platform-specific ID (e.g., Discord guild ID)

    Returns:
        JSON:API formatted response with community server details

    Raises:
        404: If community server not found and user is not a service account
    """
    try:
        logger.info(
            "Looking up community server (JSON:API)",
            extra={
                "user_id": current_user.id,
                "platform": platform,
                "platform_id": platform_id,
            },
        )

        auto_create = current_user.is_service_account

        community_server = await get_community_server_by_platform_id(
            db=db,
            community_server_id=platform_id,
            platform=platform,
            auto_create=auto_create,
        )

        if not community_server:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server not found: {platform}:{platform_id}",
            )

        server_resource = community_server_to_resource(community_server)

        response = CommunityServerSingleResponse(
            data=server_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to lookup community server (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to lookup community server",
        )


@router.get(
    "/community-servers/{server_id}",
    response_class=JSONResponse,
    response_model=CommunityServerSingleResponse,
)
async def get_community_server_jsonapi(
    server_id: UUID,
    request: HTTPRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Get a community server by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(select(CommunityServer).where(CommunityServer.id == server_id))
        community_server = result.scalar_one_or_none()

        if not community_server:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server {server_id} not found",
            )

        server_resource = community_server_to_resource(community_server)

        response = CommunityServerSingleResponse(
            data=server_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get community server (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get community server",
        )
