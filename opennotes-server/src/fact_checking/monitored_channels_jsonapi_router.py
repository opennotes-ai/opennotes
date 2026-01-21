"""JSON:API v2 monitored-channels router.

This module implements JSON:API 1.1 compliant endpoints for monitored channels.
It provides:
- GET /monitored-channels: List monitored channels with pagination
- GET /monitored-channels/{id}: Get single monitored channel
- POST /monitored-channels: Create a new monitored channel
- PATCH /monitored-channels/{id}: Update a monitored channel
- DELETE /monitored-channels/{id}: Delete a monitored channel
- Standard JSON:API response envelope structure
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin
from src.auth.dependencies import get_current_user_or_api_key
from src.common.base_schemas import StrictInputSchema
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
    JSONAPIMeta,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.common.jsonapi import (
    create_pagination_links as create_pagination_links_base,
)
from src.config import settings
from src.database import get_db
from src.fact_checking.monitored_channel_models import MonitoredChannel
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


class MonitoredChannelCreateAttributes(StrictInputSchema):
    """Attributes for creating a monitored channel via JSON:API."""

    community_server_id: str = Field(
        ..., max_length=64, description="Discord server/guild ID (platform ID)"
    )
    channel_id: str = Field(..., max_length=64, description="Discord channel ID")
    enabled: bool = Field(True, description="Whether monitoring is active")
    similarity_threshold: float = Field(
        default_factory=lambda: settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0.0-1.0) for matches",
    )
    dataset_tags: list[str] = Field(
        default_factory=lambda: ["snopes"],
        description="Dataset tags to check against",
    )
    previously_seen_autopublish_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Per-channel override for auto-publish threshold"
    )
    previously_seen_autorequest_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Per-channel override for auto-request threshold"
    )
    updated_by: str | None = Field(None, description="Discord user ID of admin creating config")


class MonitoredChannelCreateData(BaseModel):
    """JSON:API data object for monitored channel creation."""

    type: Literal["monitored-channels"] = Field(
        ..., description="Resource type must be 'monitored-channels'"
    )
    attributes: MonitoredChannelCreateAttributes


class MonitoredChannelCreateRequest(BaseModel):
    """JSON:API request body for creating a monitored channel."""

    data: MonitoredChannelCreateData


class MonitoredChannelUpdateAttributes(StrictInputSchema):
    """Attributes for updating a monitored channel via JSON:API."""

    enabled: bool | None = Field(None, description="Whether monitoring is active")
    similarity_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum similarity score (0.0-1.0) for matches"
    )
    dataset_tags: list[str] | None = Field(None, description="Dataset tags to check against")
    previously_seen_autopublish_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Per-channel override for auto-publish threshold"
    )
    previously_seen_autorequest_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Per-channel override for auto-request threshold"
    )
    updated_by: str | None = Field(None, description="Discord user ID of admin updating config")


class MonitoredChannelUpdateData(BaseModel):
    """JSON:API data object for monitored channel update."""

    type: Literal["monitored-channels"] = Field(
        ..., description="Resource type must be 'monitored-channels'"
    )
    id: str = Field(..., description="Monitored channel ID")
    attributes: MonitoredChannelUpdateAttributes


class MonitoredChannelUpdateRequest(BaseModel):
    """JSON:API request body for updating a monitored channel."""

    data: MonitoredChannelUpdateData


class MonitoredChannelAttributes(BaseModel):
    """Monitored channel attributes for JSON:API resource."""

    model_config = ConfigDict(from_attributes=True)

    community_server_id: str
    channel_id: str
    enabled: bool
    similarity_threshold: float
    dataset_tags: list[str]
    previously_seen_autopublish_threshold: float | None = None
    previously_seen_autorequest_threshold: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class MonitoredChannelResource(BaseModel):
    """JSON:API resource object for a monitored channel."""

    type: str = "monitored-channels"
    id: str
    attributes: MonitoredChannelAttributes


class MonitoredChannelListJSONAPIResponse(BaseModel):
    """JSON:API response for a list of monitored channel resources."""

    model_config = ConfigDict(from_attributes=True)

    data: list[MonitoredChannelResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class MonitoredChannelSingleResponse(BaseModel):
    """JSON:API response for a single monitored channel resource."""

    model_config = ConfigDict(from_attributes=True)

    data: MonitoredChannelResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def channel_to_resource(channel: MonitoredChannel) -> MonitoredChannelResource:
    """Convert a MonitoredChannel model to a JSON:API resource object."""
    return MonitoredChannelResource(
        type="monitored-channels",
        id=str(channel.id),
        attributes=MonitoredChannelAttributes(
            community_server_id=channel.community_server_id,
            channel_id=channel.channel_id,
            enabled=channel.enabled,
            similarity_threshold=channel.similarity_threshold,
            dataset_tags=channel.dataset_tags,
            previously_seen_autopublish_threshold=channel.previously_seen_autopublish_threshold,
            previously_seen_autorequest_threshold=channel.previously_seen_autorequest_threshold,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
            updated_by=channel.updated_by,
        ),
    )


def create_pagination_links_from_request(
    request: HTTPRequest,
    page: int,
    size: int,
    total: int,
    openapi_url: str = "/api/v2/openapi.json",
) -> JSONAPILinks:
    """Create JSON:API pagination links from a FastAPI request."""
    base_url = str(request.url).split("?")[0]
    query_params = {k: v for k, v in request.query_params.items() if not k.startswith("page[")}
    links = create_pagination_links_base(
        base_url=base_url,
        page=page,
        size=size,
        total=total,
        query_params=query_params,
    )
    links.describedby = openapi_url
    return links


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
    "/monitored-channels",
    response_class=JSONResponse,
    response_model=MonitoredChannelListJSONAPIResponse,
)
async def list_monitored_channels_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_community_server_id: str | None = Query(None, alias="filter[community_server_id]"),
    filter_enabled: bool | None = Query(None, alias="filter[enabled]"),
) -> JSONResponse:
    """List monitored channels with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server platform ID (required)
    - filter[enabled]: Filter by enabled status

    Returns JSON:API formatted response with data, jsonapi, links, and meta.
    """
    try:
        if not filter_community_server_id:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "filter[community_server_id] is required to list monitored channels",
            )

        await verify_community_admin(filter_community_server_id, current_user, db, request)

        query = select(MonitoredChannel).where(
            MonitoredChannel.community_server_id == filter_community_server_id
        )

        if filter_enabled is not None:
            query = query.where(MonitoredChannel.enabled == filter_enabled)

        total_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        query = query.offset((page_number - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        channels = result.scalars().all()

        channel_resources = [channel_to_resource(ch) for ch in channels]

        response = MonitoredChannelListJSONAPIResponse(
            data=channel_resources,
            links=create_pagination_links_from_request(request, page_number, page_size, total),
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to list monitored channels (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list monitored channels",
        )


@router.get(
    "/monitored-channels/{channel_uuid}",
    response_class=JSONResponse,
    response_model=MonitoredChannelSingleResponse,
)
async def get_monitored_channel_jsonapi(
    channel_uuid: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get a single monitored channel by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(
            select(MonitoredChannel).where(MonitoredChannel.id == channel_uuid)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Monitored channel {channel_uuid} not found",
            )

        await verify_community_admin(channel.community_server_id, current_user, db, request)

        channel_resource = channel_to_resource(channel)

        response = MonitoredChannelSingleResponse(
            data=channel_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get monitored channel (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get monitored channel",
        )


@router.post(
    "/monitored-channels",
    response_class=JSONResponse,
    response_model=MonitoredChannelSingleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitored_channel_jsonapi(
    request: HTTPRequest,
    body: MonitoredChannelCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a new monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        attrs = body.data.attributes

        await verify_community_admin(attrs.community_server_id, current_user, db, request)

        duplicate_result = await db.execute(
            select(MonitoredChannel).where(MonitoredChannel.channel_id == attrs.channel_id)
        )
        if duplicate_result.scalar_one_or_none():
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Channel {attrs.channel_id} is already monitored",
            )

        new_channel = MonitoredChannel(
            community_server_id=attrs.community_server_id,
            channel_id=attrs.channel_id,
            enabled=attrs.enabled,
            similarity_threshold=attrs.similarity_threshold,
            dataset_tags=attrs.dataset_tags,
            previously_seen_autopublish_threshold=attrs.previously_seen_autopublish_threshold,
            previously_seen_autorequest_threshold=attrs.previously_seen_autorequest_threshold,
            updated_by=attrs.updated_by,
        )

        db.add(new_channel)
        await db.commit()
        await db.refresh(new_channel)

        logger.info(
            f"Created monitored channel {new_channel.id} via JSON:API by user {current_user.id}"
        )

        channel_resource = channel_to_resource(new_channel)
        response = MonitoredChannelSingleResponse(
            data=channel_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{new_channel.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException as e:
        await db.rollback()
        return create_error_response(
            e.status_code,
            e.detail if isinstance(e.detail, str) else "Bad Request",
            e.detail if isinstance(e.detail, str) else str(e.detail),
        )

    except Exception as e:
        logger.exception(f"Failed to create monitored channel (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create monitored channel",
        )


@router.patch(
    "/monitored-channels/{channel_uuid}",
    response_class=JSONResponse,
    response_model=MonitoredChannelSingleResponse,
)
async def update_monitored_channel_jsonapi(
    channel_uuid: UUID,
    request: HTTPRequest,
    body: MonitoredChannelUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Update a monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        if body.data.id != str(channel_uuid):
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"ID in URL ({channel_uuid}) does not match ID in request body ({body.data.id})",
            )

        result = await db.execute(
            select(MonitoredChannel).where(MonitoredChannel.id == channel_uuid)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Monitored channel {channel_uuid} not found",
            )

        await verify_community_admin(channel.community_server_id, current_user, db, request)

        attrs = body.data.attributes
        update_data = attrs.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(channel, field, value)

        await db.commit()
        await db.refresh(channel)

        logger.info(
            f"Updated monitored channel {channel_uuid} via JSON:API by user {current_user.id}"
        )

        channel_resource = channel_to_resource(channel)
        response = MonitoredChannelSingleResponse(
            data=channel_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to update monitored channel (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update monitored channel",
        )


@router.delete("/monitored-channels/{channel_uuid}", response_class=JSONResponse)
async def delete_monitored_channel_jsonapi(
    channel_uuid: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Delete a monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Response with 204 No Content status on success
    - No response body on success
    - JSON:API error format for errors

    Returns 204 No Content on success, JSON:API error on failure.
    """
    try:
        result = await db.execute(
            select(MonitoredChannel).where(MonitoredChannel.id == channel_uuid)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Monitored channel {channel_uuid} not found",
            )

        await verify_community_admin(channel.community_server_id, current_user, db, request)

        await db.execute(delete(MonitoredChannel).where(MonitoredChannel.id == channel_uuid))
        await db.commit()

        logger.info(
            f"Deleted monitored channel {channel_uuid} via JSON:API by user {current_user.id}"
        )

        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

    except Exception as e:
        logger.exception(f"Failed to delete monitored channel (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to delete monitored channel",
        )
