"""JSON:API v2 note-publisher router.

This module implements JSON:API 1.1 compliant endpoints for note publisher configs and posts.
It provides:
- GET /note-publisher-configs: List configs with pagination
- GET /note-publisher-configs/{id}: Get single config
- POST /note-publisher-configs: Create a new config
- PATCH /note-publisher-configs/{id}: Update a config
- DELETE /note-publisher-configs/{id}: Delete a config
- GET /note-publisher-posts: List posts with pagination
- GET /note-publisher-posts/{id}: Get single post
- POST /note-publisher-posts: Create a new post record
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    verify_community_membership,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
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
from src.database import get_db
from src.llm_config.models import CommunityServer
from src.monitoring import get_logger
from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


class NotePublisherConfigCreateAttributes(StrictInputSchema):
    """Attributes for creating a note publisher config via JSON:API."""

    community_server_id: str = Field(
        ..., max_length=64, description="Discord server/guild ID (platform ID)"
    )
    channel_id: str | None = Field(
        None, max_length=64, description="Discord channel ID (None for server-wide)"
    )
    enabled: bool = Field(True, description="Whether auto-publishing is enabled")
    threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Score threshold for auto-publishing (0.0-1.0)"
    )
    updated_by: str | None = Field(None, max_length=64, description="Discord user ID of admin")


class NotePublisherConfigCreateData(BaseModel):
    """JSON:API data object for config creation."""

    type: Literal["note-publisher-configs"] = Field(
        ..., description="Resource type must be 'note-publisher-configs'"
    )
    attributes: NotePublisherConfigCreateAttributes


class NotePublisherConfigCreateRequest(BaseModel):
    """JSON:API request body for creating a config."""

    data: NotePublisherConfigCreateData


class NotePublisherConfigUpdateAttributes(StrictInputSchema):
    """Attributes for updating a note publisher config via JSON:API."""

    enabled: bool | None = Field(None, description="Whether auto-publishing is enabled")
    threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Score threshold for auto-publishing (0.0-1.0)"
    )
    updated_by: str | None = Field(None, max_length=64, description="Discord user ID of admin")


class NotePublisherConfigUpdateData(BaseModel):
    """JSON:API data object for config update."""

    type: Literal["note-publisher-configs"] = Field(
        ..., description="Resource type must be 'note-publisher-configs'"
    )
    id: str = Field(..., description="Config ID")
    attributes: NotePublisherConfigUpdateAttributes


class NotePublisherConfigUpdateRequest(BaseModel):
    """JSON:API request body for updating a config."""

    data: NotePublisherConfigUpdateData


class NotePublisherConfigAttributes(BaseModel):
    """Note publisher config attributes for JSON:API resource."""

    model_config = ConfigDict(from_attributes=True)

    community_server_id: str
    channel_id: str | None = None
    enabled: bool
    threshold: float | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class NotePublisherConfigResource(BaseModel):
    """JSON:API resource object for a note publisher config."""

    type: str = "note-publisher-configs"
    id: str
    attributes: NotePublisherConfigAttributes


class NotePublisherConfigListResponse(BaseModel):
    """JSON:API response for a list of config resources."""

    model_config = ConfigDict(from_attributes=True)

    data: list[NotePublisherConfigResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class NotePublisherConfigSingleResponse(BaseModel):
    """JSON:API response for a single config resource."""

    model_config = ConfigDict(from_attributes=True)

    data: NotePublisherConfigResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class NotePublisherPostCreateAttributes(StrictInputSchema):
    """Attributes for creating a note publisher post via JSON:API."""

    note_id: str = Field(..., description="UUID of the published note")
    original_message_id: str = Field(..., max_length=64, description="Original Discord message ID")
    auto_post_message_id: str | None = Field(
        None, max_length=64, description="Auto-posted Discord message ID"
    )
    channel_id: str = Field(..., max_length=64, description="Discord channel ID")
    community_server_id: str = Field(
        ..., max_length=64, description="Discord server/guild ID (platform ID)"
    )
    score_at_post: float = Field(..., description="Score at time of posting")
    confidence_at_post: str = Field(..., max_length=32, description="Confidence level at posting")
    success: bool = Field(..., description="Whether the post was successful")
    error_message: str | None = Field(None, description="Error message if post failed")


class NotePublisherPostCreateData(BaseModel):
    """JSON:API data object for post creation."""

    type: Literal["note-publisher-posts"] = Field(
        ..., description="Resource type must be 'note-publisher-posts'"
    )
    attributes: NotePublisherPostCreateAttributes


class NotePublisherPostCreateRequest(BaseModel):
    """JSON:API request body for creating a post record."""

    data: NotePublisherPostCreateData


class NotePublisherPostAttributes(BaseModel):
    """Note publisher post attributes for JSON:API resource."""

    model_config = ConfigDict(from_attributes=True)

    note_id: str
    original_message_id: str
    auto_post_message_id: str | None = None
    channel_id: str
    community_server_id: str
    score_at_post: float
    confidence_at_post: str
    posted_at: datetime | None = None
    success: bool
    error_message: str | None = None


class NotePublisherPostResource(BaseModel):
    """JSON:API resource object for a note publisher post."""

    type: str = "note-publisher-posts"
    id: str
    attributes: NotePublisherPostAttributes


class NotePublisherPostListResponse(BaseModel):
    """JSON:API response for a list of post resources."""

    model_config = ConfigDict(from_attributes=True)

    data: list[NotePublisherPostResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class NotePublisherPostSingleResponse(BaseModel):
    """JSON:API response for a single post resource."""

    model_config = ConfigDict(from_attributes=True)

    data: NotePublisherPostResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def config_to_resource(config: NotePublisherConfig) -> NotePublisherConfigResource:
    """Convert a NotePublisherConfig model to a JSON:API resource object."""
    # Get platform ID from the related community_server
    platform_id = (
        config.community_server.platform_community_server_id
        if config.community_server
        else str(config.community_server_id)
    )
    return NotePublisherConfigResource(
        type="note-publisher-configs",
        id=str(config.id),
        attributes=NotePublisherConfigAttributes(
            community_server_id=platform_id,
            channel_id=config.channel_id,
            enabled=config.enabled,
            threshold=config.threshold,
            updated_at=config.updated_at,
            updated_by=config.updated_by,
        ),
    )


def post_to_resource(post: NotePublisherPost) -> NotePublisherPostResource:
    """Convert a NotePublisherPost model to a JSON:API resource object."""
    # Get platform ID from the related community_server
    platform_id = (
        post.community_server.platform_community_server_id
        if post.community_server
        else str(post.community_server_id)
    )
    return NotePublisherPostResource(
        type="note-publisher-posts",
        id=str(post.id),
        attributes=NotePublisherPostAttributes(
            note_id=str(post.note_id),
            original_message_id=post.original_message_id,
            auto_post_message_id=post.auto_post_message_id,
            channel_id=post.channel_id,
            community_server_id=platform_id,
            score_at_post=post.score_at_post,
            confidence_at_post=post.confidence_at_post,
            posted_at=post.posted_at,
            success=post.success,
            error_message=post.error_message,
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
    "/note-publisher-configs",
    response_class=JSONResponse,
    response_model=NotePublisherConfigListResponse,
)
async def list_note_publisher_configs_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_community_server_id: str | None = Query(None, alias="filter[community_server_id]"),
    filter_enabled: bool | None = Query(None, alias="filter[enabled]"),
) -> JSONResponse:
    """List note publisher configs with JSON:API format.

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
                "filter[community_server_id] is required to list note publisher configs",
            )

        if not is_service_account(current_user):
            await verify_community_membership(filter_community_server_id, current_user, db, request)

        # Look up community server UUID from platform ID
        cs_result = await db.execute(
            select(CommunityServer.id).where(
                CommunityServer.platform_community_server_id == filter_community_server_id
            )
        )
        community_server_uuid = cs_result.scalar_one_or_none()

        if not community_server_uuid:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server not found: {filter_community_server_id}",
            )

        query = select(NotePublisherConfig).where(
            NotePublisherConfig.community_server_id == community_server_uuid
        )

        if filter_enabled is not None:
            query = query.where(NotePublisherConfig.enabled == filter_enabled)

        total_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        query = query.offset((page_number - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        configs = result.scalars().all()

        config_resources = [config_to_resource(cfg) for cfg in configs]

        response = NotePublisherConfigListResponse(
            data=config_resources,
            links=create_pagination_links_from_request(request, page_number, page_size, total),
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to list note publisher configs (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list note publisher configs",
        )


@router.get(
    "/note-publisher-configs/{config_uuid}",
    response_class=JSONResponse,
    response_model=NotePublisherConfigSingleResponse,
)
async def get_note_publisher_config_jsonapi(
    config_uuid: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get a single note publisher config by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(
            select(NotePublisherConfig).where(NotePublisherConfig.id == config_uuid)
        )
        config = result.scalar_one_or_none()

        if not config:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note publisher config {config_uuid} not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership_by_uuid(
                config.community_server_id, current_user, db, request
            )

        config_resource = config_to_resource(config)

        response = NotePublisherConfigSingleResponse(
            data=config_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get note publisher config (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get note publisher config",
        )


@router.post(
    "/note-publisher-configs",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=NotePublisherConfigSingleResponse,
)
async def create_note_publisher_config_jsonapi(
    request: HTTPRequest,
    body: NotePublisherConfigCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a new note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        attrs = body.data.attributes

        if not is_service_account(current_user):
            await verify_community_membership(attrs.community_server_id, current_user, db, request)

        # Look up community server UUID from platform ID
        cs_result = await db.execute(
            select(CommunityServer.id).where(
                CommunityServer.platform_community_server_id == attrs.community_server_id
            )
        )
        community_server_uuid = cs_result.scalar_one_or_none()

        if not community_server_uuid:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server not found: {attrs.community_server_id}",
            )

        duplicate_result = await db.execute(
            select(NotePublisherConfig).where(
                NotePublisherConfig.community_server_id == community_server_uuid,
                NotePublisherConfig.channel_id == attrs.channel_id,
            )
        )
        if duplicate_result.scalar_one_or_none():
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Config already exists for community_server_id={attrs.community_server_id}, channel_id={attrs.channel_id}",
            )

        new_config = NotePublisherConfig(
            community_server_id=community_server_uuid,
            channel_id=attrs.channel_id,
            enabled=attrs.enabled,
            threshold=attrs.threshold,
            updated_by=attrs.updated_by,
        )

        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)

        logger.info(
            f"Created note publisher config {new_config.id} via JSON:API by user {current_user.id}"
        )

        config_resource = config_to_resource(new_config)
        response = NotePublisherConfigSingleResponse(
            data=config_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{new_config.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to create note publisher config (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create note publisher config",
        )


@router.patch(
    "/note-publisher-configs/{config_uuid}",
    response_class=JSONResponse,
    response_model=NotePublisherConfigSingleResponse,
)
async def update_note_publisher_config_jsonapi(
    config_uuid: UUID,
    request: HTTPRequest,
    body: NotePublisherConfigUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Update a note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        if body.data.id != str(config_uuid):
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"ID in URL ({config_uuid}) does not match ID in request body ({body.data.id})",
            )

        result = await db.execute(
            select(NotePublisherConfig).where(NotePublisherConfig.id == config_uuid)
        )
        config = result.scalar_one_or_none()

        if not config:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note publisher config {config_uuid} not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership_by_uuid(
                config.community_server_id, current_user, db, request
            )

        attrs = body.data.attributes
        update_data = attrs.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

        await db.commit()
        await db.refresh(config)

        logger.info(
            f"Updated note publisher config {config_uuid} via JSON:API by user {current_user.id}"
        )

        config_resource = config_to_resource(config)
        response = NotePublisherConfigSingleResponse(
            data=config_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to update note publisher config (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update note publisher config",
        )


@router.delete("/note-publisher-configs/{config_uuid}", response_class=JSONResponse)
async def delete_note_publisher_config_jsonapi(
    config_uuid: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Delete a note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Response with 204 No Content status on success
    - No response body on success
    - JSON:API error format for errors

    Returns 204 No Content on success, JSON:API error on failure.
    """
    try:
        result = await db.execute(
            select(NotePublisherConfig).where(NotePublisherConfig.id == config_uuid)
        )
        config = result.scalar_one_or_none()

        if not config:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note publisher config {config_uuid} not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership_by_uuid(
                config.community_server_id, current_user, db, request
            )

        await db.execute(delete(NotePublisherConfig).where(NotePublisherConfig.id == config_uuid))
        await db.commit()

        logger.info(
            f"Deleted note publisher config {config_uuid} via JSON:API by user {current_user.id}"
        )

        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

    except Exception as e:
        logger.exception(f"Failed to delete note publisher config (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to delete note publisher config",
        )


@router.get(
    "/note-publisher-posts",
    response_class=JSONResponse,
    response_model=NotePublisherPostListResponse,
)
async def list_note_publisher_posts_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_community_server_id: str | None = Query(None, alias="filter[community_server_id]"),
    filter_channel_id: str | None = Query(None, alias="filter[channel_id]"),
    filter_success: bool | None = Query(None, alias="filter[success]"),
) -> JSONResponse:
    """List note publisher posts with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server platform ID (required)
    - filter[channel_id]: Filter by Discord channel ID
    - filter[success]: Filter by success status

    Returns JSON:API formatted response with data, jsonapi, links, and meta.
    """
    try:
        if not filter_community_server_id:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "filter[community_server_id] is required to list note publisher posts",
            )

        if not is_service_account(current_user):
            await verify_community_membership(filter_community_server_id, current_user, db, request)

        # Look up community server UUID from platform ID
        cs_result = await db.execute(
            select(CommunityServer.id).where(
                CommunityServer.platform_community_server_id == filter_community_server_id
            )
        )
        community_server_uuid = cs_result.scalar_one_or_none()

        if not community_server_uuid:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server not found: {filter_community_server_id}",
            )

        query = select(NotePublisherPost).where(
            NotePublisherPost.community_server_id == community_server_uuid
        )

        if filter_channel_id is not None:
            query = query.where(NotePublisherPost.channel_id == filter_channel_id)

        if filter_success is not None:
            query = query.where(NotePublisherPost.success == filter_success)

        query = query.order_by(NotePublisherPost.posted_at.desc())

        total_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        query = query.offset((page_number - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        posts = result.scalars().all()

        post_resources = [post_to_resource(p) for p in posts]

        response = NotePublisherPostListResponse(
            data=post_resources,
            links=create_pagination_links_from_request(request, page_number, page_size, total),
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to list note publisher posts (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list note publisher posts",
        )


@router.get(
    "/note-publisher-posts/{post_uuid}",
    response_class=JSONResponse,
    response_model=NotePublisherPostSingleResponse,
)
async def get_note_publisher_post_jsonapi(
    post_uuid: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get a single note publisher post by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(
            select(NotePublisherPost).where(NotePublisherPost.id == post_uuid)
        )
        post = result.scalar_one_or_none()

        if not post:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note publisher post {post_uuid} not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership_by_uuid(
                post.community_server_id, current_user, db, request
            )

        post_resource = post_to_resource(post)

        response = NotePublisherPostSingleResponse(
            data=post_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get note publisher post (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get note publisher post",
        )


@router.post(
    "/note-publisher-posts",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=NotePublisherPostSingleResponse,
)
async def create_note_publisher_post_jsonapi(
    request: HTTPRequest,
    body: NotePublisherPostCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a new note publisher post record with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        attrs = body.data.attributes

        if not is_service_account(current_user):
            await verify_community_membership(attrs.community_server_id, current_user, db, request)

        # Look up community server UUID from platform ID
        cs_result = await db.execute(
            select(CommunityServer.id).where(
                CommunityServer.platform_community_server_id == attrs.community_server_id
            )
        )
        community_server_uuid = cs_result.scalar_one_or_none()

        if not community_server_uuid:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server not found: {attrs.community_server_id}",
            )

        duplicate_result = await db.execute(
            select(NotePublisherPost).where(
                NotePublisherPost.original_message_id == attrs.original_message_id
            )
        )
        if duplicate_result.scalar_one_or_none():
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Post record already exists for original_message_id={attrs.original_message_id}",
            )

        new_post = NotePublisherPost(
            note_id=UUID(attrs.note_id),
            original_message_id=attrs.original_message_id,
            auto_post_message_id=attrs.auto_post_message_id
            if attrs.auto_post_message_id
            else (attrs.original_message_id if attrs.success else None),
            channel_id=attrs.channel_id,
            community_server_id=community_server_uuid,
            score_at_post=attrs.score_at_post,
            confidence_at_post=attrs.confidence_at_post,
            success=attrs.success,
            error_message=attrs.error_message,
        )

        db.add(new_post)
        await db.commit()
        await db.refresh(new_post)

        logger.info(
            f"Created note publisher post {new_post.id} via JSON:API by user {current_user.id}"
        )

        post_resource = post_to_resource(new_post)
        response = NotePublisherPostSingleResponse(
            data=post_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{new_post.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException as e:
        logger.info(f"Authorization check failed for note publisher post creation: {e.detail}")
        await db.rollback()
        raise

    except IntegrityError as e:
        logger.error(f"Integrity error creating note publisher post: {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_409_CONFLICT,
            "Conflict",
            "Post record conflicts with existing data",
        )

    except Exception as e:
        logger.exception(f"Failed to create note publisher post (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create note publisher post",
        )
