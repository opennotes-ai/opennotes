"""JSON:API v2 previously-seen-messages router.

This module implements JSON:API 1.1 compliant endpoints for previously seen messages.
It provides:
- GET /previously-seen-messages: List previously seen messages with pagination
- GET /previously-seen-messages/{id}: Get single previously seen message
- POST /previously-seen-messages: Create a new previously seen message record
- POST /previously-seen-messages/check: Check if message was previously seen
- Standard JSON:API response envelope structure
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

import uuid
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_membership
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
from src.config import settings
from src.database import get_db
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.monitored_channel_models import MonitoredChannel
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.fact_checking.previously_seen_schemas import PreviouslySeenMessageMatch
from src.fact_checking.threshold_helpers import get_previously_seen_thresholds
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Get or create thread-safe encryption service singleton."""
    return EncryptionService(settings.ENCRYPTION_MASTER_KEY)


@lru_cache
def get_llm_service(
    encryption_service: Annotated[EncryptionService, Depends(get_encryption_service)],
) -> LLMService:
    """Get or create LLM service singleton."""
    client_manager = LLMClientManager(encryption_service)
    return LLMService(client_manager)


def get_embedding_service(
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> EmbeddingService:
    """Get embedding service with LLM service dependency."""
    return EmbeddingService(llm_service)


class PreviouslySeenMessageCreateAttributes(StrictInputSchema):
    """Attributes for creating a previously seen message via JSON:API."""

    community_server_id: str = Field(..., description="Community server UUID")
    original_message_id: str = Field(..., max_length=64, description="Platform-specific message ID")
    published_note_id: str = Field(..., description="Note ID that was published for this message")
    embedding: list[float] | None = Field(
        None, description="Vector embedding for semantic similarity search (1536 dimensions)"
    )
    embedding_provider: str | None = Field(
        None, max_length=50, description="LLM provider used for embedding generation"
    )
    embedding_model: str | None = Field(
        None, max_length=100, description="Model name used for embedding generation"
    )
    extra_metadata: dict[str, str | int | float | bool | None] | None = Field(
        None, description="Additional context metadata"
    )


class PreviouslySeenMessageCreateData(BaseModel):
    """JSON:API data object for previously seen message creation."""

    type: Literal["previously-seen-messages"] = Field(
        ..., description="Resource type must be 'previously-seen-messages'"
    )
    attributes: PreviouslySeenMessageCreateAttributes


class PreviouslySeenMessageCreateRequest(BaseModel):
    """JSON:API request body for creating a previously seen message."""

    data: PreviouslySeenMessageCreateData


class PreviouslySeenCheckAttributes(StrictInputSchema):
    """Attributes for checking previously seen messages via JSON:API."""

    message_text: str = Field(
        ..., min_length=1, max_length=50000, description="Message text to check"
    )
    guild_id: str = Field(..., max_length=64, description="Discord guild ID")
    channel_id: str = Field(..., max_length=64, description="Discord channel ID")


class PreviouslySeenCheckData(BaseModel):
    """JSON:API data object for previously seen message check."""

    type: Literal["previously-seen-check"] = Field(
        ..., description="Resource type must be 'previously-seen-check'"
    )
    attributes: PreviouslySeenCheckAttributes


class PreviouslySeenCheckRequest(BaseModel):
    """JSON:API request body for checking previously seen messages."""

    data: PreviouslySeenCheckData


class PreviouslySeenMessageAttributes(BaseModel):
    """Previously seen message attributes for JSON:API resource."""

    model_config = ConfigDict(from_attributes=True)

    community_server_id: str
    original_message_id: str
    published_note_id: str
    embedding_provider: str | None = None
    embedding_model: str | None = None
    extra_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class PreviouslySeenMessageResource(BaseModel):
    """JSON:API resource object for a previously seen message."""

    type: str = "previously-seen-messages"
    id: str
    attributes: PreviouslySeenMessageAttributes


class PreviouslySeenMessageListResponse(BaseModel):
    """JSON:API response for a list of previously seen message resources."""

    model_config = ConfigDict(from_attributes=True)

    data: list[PreviouslySeenMessageResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class PreviouslySeenMessageSingleResponse(BaseModel):
    """JSON:API response for a single previously seen message resource."""

    model_config = ConfigDict(from_attributes=True)

    data: PreviouslySeenMessageResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class PreviouslySeenMatchResource(BaseModel):
    """JSON:API resource for a match in check results."""

    id: str
    community_server_id: str
    original_message_id: str
    published_note_id: str
    embedding_provider: str | None = None
    embedding_model: str | None = None
    extra_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    similarity_score: float


class PreviouslySeenCheckResultAttributes(BaseModel):
    """Attributes for previously seen check result."""

    should_auto_publish: bool
    should_auto_request: bool
    autopublish_threshold: float
    autorequest_threshold: float
    matches: list[PreviouslySeenMatchResource]
    top_match: PreviouslySeenMatchResource | None = None


class PreviouslySeenCheckResultResource(BaseModel):
    """JSON:API resource object for check results."""

    type: str = "previously-seen-check-result"
    id: str
    attributes: PreviouslySeenCheckResultAttributes


class PreviouslySeenCheckResultResponse(BaseModel):
    """JSON:API response for previously seen check results."""

    model_config = ConfigDict(from_attributes=True)

    data: PreviouslySeenCheckResultResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def message_to_resource(msg: PreviouslySeenMessage) -> PreviouslySeenMessageResource:
    """Convert a PreviouslySeenMessage model to a JSON:API resource object."""
    return PreviouslySeenMessageResource(
        type="previously-seen-messages",
        id=str(msg.id),
        attributes=PreviouslySeenMessageAttributes(
            community_server_id=str(msg.community_server_id),
            original_message_id=msg.original_message_id,
            published_note_id=str(msg.published_note_id),
            embedding_provider=msg.embedding_provider,
            embedding_model=msg.embedding_model,
            extra_metadata=msg.extra_metadata,
            created_at=msg.created_at,
        ),
    )


def match_to_resource(match: PreviouslySeenMessageMatch) -> PreviouslySeenMatchResource:
    """Convert a PreviouslySeenMessageMatch to a JSON:API match resource."""
    return PreviouslySeenMatchResource(
        id=str(match.id),
        community_server_id=str(match.community_server_id),
        original_message_id=match.original_message_id,
        published_note_id=str(match.published_note_id),
        embedding_provider=match.embedding_provider,
        embedding_model=match.embedding_model,
        extra_metadata=match.extra_metadata,
        created_at=match.created_at,
        similarity_score=match.similarity_score,
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
    "/previously-seen-messages",
    response_class=JSONResponse,
    response_model=PreviouslySeenMessageListResponse,
)
async def list_previously_seen_messages_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_community_server_id: str | None = Query(None, alias="filter[community_server_id]"),
) -> JSONResponse:
    """List previously seen messages with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server UUID (required)

    Returns JSON:API formatted response with data, jsonapi, links, and meta.
    """
    try:
        if not filter_community_server_id:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "filter[community_server_id] is required to list previously seen messages",
            )

        try:
            community_uuid = UUID(filter_community_server_id)
        except ValueError:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "filter[community_server_id] must be a valid UUID",
            )

        result = await db.execute(
            select(CommunityServer).where(CommunityServer.id == community_uuid)
        )
        community_server = result.scalar_one_or_none()
        if not community_server:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server {community_uuid} not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership(
                community_server.platform_community_server_id, current_user, db, request
            )

        query = select(PreviouslySeenMessage).where(
            PreviouslySeenMessage.community_server_id == community_uuid
        )

        total_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        query = query.offset((page_number - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        messages = result.scalars().all()

        message_resources = [message_to_resource(msg) for msg in messages]

        response = PreviouslySeenMessageListResponse(
            data=message_resources,
            links=create_pagination_links_from_request(request, page_number, page_size, total),
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to list previously seen messages (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list previously seen messages",
        )


@router.get(
    "/previously-seen-messages/{message_uuid}",
    response_class=JSONResponse,
    response_model=PreviouslySeenMessageSingleResponse,
)
async def get_previously_seen_message_jsonapi(
    message_uuid: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get a single previously seen message by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(
            select(PreviouslySeenMessage).where(PreviouslySeenMessage.id == message_uuid)
        )
        message = result.scalar_one_or_none()

        if not message:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Previously seen message {message_uuid} not found",
            )

        community_result = await db.execute(
            select(CommunityServer).where(CommunityServer.id == message.community_server_id)
        )
        community_server = community_result.scalar_one_or_none()
        if not community_server:
            return create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "Community server for message not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership(
                community_server.platform_community_server_id, current_user, db, request
            )

        message_resource = message_to_resource(message)

        response = PreviouslySeenMessageSingleResponse(
            data=message_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get previously seen message (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get previously seen message",
        )


@router.post(
    "/previously-seen-messages",
    response_class=JSONResponse,
    response_model=PreviouslySeenMessageSingleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_previously_seen_message_jsonapi(
    request: HTTPRequest,
    body: PreviouslySeenMessageCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a new previously seen message with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        attrs = body.data.attributes

        try:
            community_uuid = UUID(attrs.community_server_id)
        except ValueError:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "community_server_id must be a valid UUID",
            )

        try:
            note_uuid = UUID(attrs.published_note_id)
        except ValueError:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "published_note_id must be a valid UUID",
            )

        community_result = await db.execute(
            select(CommunityServer).where(CommunityServer.id == community_uuid)
        )
        community_server = community_result.scalar_one_or_none()
        if not community_server:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server {community_uuid} not found",
            )

        if not is_service_account(current_user):
            await verify_community_membership(
                community_server.platform_community_server_id, current_user, db, request
            )

        new_message = PreviouslySeenMessage(
            community_server_id=community_uuid,
            original_message_id=attrs.original_message_id,
            published_note_id=note_uuid,
            embedding=attrs.embedding,
            embedding_provider=attrs.embedding_provider,
            embedding_model=attrs.embedding_model,
            extra_metadata=attrs.extra_metadata or {},
        )

        db.add(new_message)
        await db.commit()
        await db.refresh(new_message)

        logger.info(
            f"Created previously seen message {new_message.id} via JSON:API by user {current_user.id}"
        )

        message_resource = message_to_resource(new_message)
        response = PreviouslySeenMessageSingleResponse(
            data=message_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{new_message.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to create previously seen message (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create previously seen message",
        )


@router.post(
    "/previously-seen-messages/check",
    response_class=JSONResponse,
    response_model=PreviouslySeenCheckResultResponse,
)
async def check_previously_seen_jsonapi(
    request: HTTPRequest,
    body: PreviouslySeenCheckRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> JSONResponse:
    """Check if a message has been seen before with JSON:API format.

    This endpoint:
    1. Generates an embedding for the message text
    2. Searches for similar previously seen messages
    3. Resolves thresholds (channel override or global config)
    4. Returns action recommendations (auto-publish/auto-request)

    JSON:API 1.1 action endpoint that returns check results.
    """
    try:
        attrs = body.data.attributes

        result = await db.execute(
            select(CommunityServer.id).where(
                CommunityServer.platform_community_server_id == attrs.guild_id
            )
        )
        community_server_uuid = result.scalar_one_or_none()

        if not community_server_uuid:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Community server not found: {attrs.guild_id}",
            )

        if not is_service_account(current_user):
            await verify_community_membership(attrs.guild_id, current_user, db, request)

        monitored_channel_result = await db.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.community_server_id == community_server_uuid,
                MonitoredChannel.channel_id == attrs.channel_id,
            )
        )
        monitored_channel = monitored_channel_result.scalar_one_or_none()

        autopublish_threshold, autorequest_threshold = get_previously_seen_thresholds(
            monitored_channel
        )

        logger.debug(
            "Checking previously seen messages",
            extra={
                "guild_id": attrs.guild_id,
                "channel_id": attrs.channel_id,
                "autopublish_threshold": autopublish_threshold,
                "autorequest_threshold": autorequest_threshold,
                "text_length": len(attrs.message_text),
            },
        )

        embedding = await embedding_service.generate_embedding(
            db=db, text=attrs.message_text, community_server_id=attrs.guild_id
        )

        matches = await embedding_service.search_previously_seen(
            db=db,
            embedding=embedding,
            community_server_id=community_server_uuid,
            similarity_threshold=autorequest_threshold,
            limit=5,
        )

        should_auto_publish = False
        should_auto_request = False
        top_match = None

        if matches:
            top_match = matches[0]
            top_score = top_match.similarity_score

            if top_score >= autopublish_threshold:
                should_auto_publish = True
                logger.info(
                    "Auto-publish recommended for previously seen message",
                    extra={
                        "guild_id": attrs.guild_id,
                        "channel_id": attrs.channel_id,
                        "similarity_score": top_score,
                        "autopublish_threshold": autopublish_threshold,
                        "published_note_id": str(top_match.published_note_id),
                    },
                )
            elif top_score >= autorequest_threshold:
                should_auto_request = True
                logger.info(
                    "Auto-request recommended for similar previously seen message",
                    extra={
                        "guild_id": attrs.guild_id,
                        "channel_id": attrs.channel_id,
                        "similarity_score": top_score,
                        "autorequest_threshold": autorequest_threshold,
                        "published_note_id": str(top_match.published_note_id),
                    },
                )

        match_resources = [match_to_resource(m) for m in matches]
        top_match_resource = match_to_resource(top_match) if top_match else None

        check_result = PreviouslySeenCheckResultResource(
            type="previously-seen-check-result",
            id=str(uuid.uuid4()),
            attributes=PreviouslySeenCheckResultAttributes(
                should_auto_publish=should_auto_publish,
                should_auto_request=should_auto_request,
                autopublish_threshold=autopublish_threshold,
                autorequest_threshold=autorequest_threshold,
                matches=match_resources,
                top_match=top_match_resource,
            ),
        )

        response = PreviouslySeenCheckResultResponse(
            data=check_result,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to check previously seen messages (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to check previously seen messages",
        )
