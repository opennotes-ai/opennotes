"""JSON:API v2 requests router.

This module implements a JSON:API 1.1 compliant endpoint for requests.
It provides:
- Standard JSON:API response envelope structure
- Filtering support with operators
- Pagination support
- Write operations (POST, PATCH)
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from uuid import UUID

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_community_server_by_platform_id,
    get_user_community_ids,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.ownership_dependencies import verify_request_ownership
from src.auth.permissions import is_service_account
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.common.filters import FilterBuilder, FilterField, FilterOperator
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
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.notes import loaders
from src.notes.message_archive_models import MessageArchive
from src.notes.message_archive_service import MessageArchiveService
from src.notes.models import Note, Request
from src.notes.schemas import (
    NoteJSONAPIAttributes,
    NoteResource,
    NoteSingleResponse,
    RequestStatus,
)
from src.users.models import User

if TYPE_CHECKING:
    from src.services.ai_note_writer import AINoteWriter

logger = get_logger(__name__)

router = APIRouter()


def get_ai_note_writer(http_request: HTTPRequest) -> "AINoteWriter":
    """Dependency to get AINoteWriter service from app state."""
    from src.services.ai_note_writer import AINoteWriter  # noqa: PLC0415

    ai_note_writer = getattr(http_request.app.state, "ai_note_writer", None)
    if ai_note_writer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI note writing service is not available",
        )
    return cast(AINoteWriter, ai_note_writer)


def note_to_resource(note: Note) -> NoteResource:
    """Convert a Note model to a JSON:API resource object."""
    platform_message_id = None
    if note.request and note.request.message_archive:
        platform_message_id = note.request.message_archive.platform_message_id

    return NoteResource(
        type="notes",
        id=str(note.id),
        attributes=NoteJSONAPIAttributes(
            author_id=str(note.author_id),
            channel_id=note.channel_id,
            summary=note.summary,
            classification=note.classification,
            helpfulness_score=note.helpfulness_score,
            status=note.status,
            ai_generated=note.ai_generated,
            ai_provider=note.ai_provider,
            force_published=note.force_published,
            force_published_at=note.force_published_at,
            created_at=note.created_at,
            updated_at=note.updated_at,
            request_id=note.request_id,
            platform_message_id=platform_message_id,
            ratings_count=len(note.ratings) if note.ratings else 0,
            community_server_id=str(note.community_server_id) if note.community_server_id else None,
        ),
    )


class RequestCreateAttributes(StrictInputSchema):
    """Attributes for creating a request via JSON:API."""

    request_id: str = Field(..., min_length=1, description="Unique request identifier")
    requested_by: str = Field(..., description="Requester's participant ID")
    community_server_id: str = Field(
        ..., description="Community server ID (Discord guild ID, subreddit, etc.)"
    )
    original_message_content: str | None = Field(None, description="Original message content")
    platform_message_id: str | None = Field(None, description="Platform message ID")
    platform_channel_id: str | None = Field(None, description="Platform channel ID")
    platform_author_id: str | None = Field(None, description="Platform author ID")
    platform_timestamp: datetime | None = Field(None, description="Platform message timestamp")
    metadata: dict[str, Any] | None = Field(None, description="Request metadata")
    similarity_score: float | None = Field(
        None, description="Match similarity score", ge=0.0, le=1.0
    )
    dataset_name: str | None = Field(None, description="Source dataset name", max_length=100)
    dataset_item_id: str | None = Field(None, description="Fact-check item ID", max_length=36)


class RequestCreateData(BaseModel):
    """JSON:API data object for request creation."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["requests"] = Field(..., description="Resource type must be 'requests'")
    attributes: RequestCreateAttributes


class RequestCreateRequest(BaseModel):
    """JSON:API request body for creating a request."""

    model_config = ConfigDict(extra="forbid")

    data: RequestCreateData


class RequestUpdateAttributes(StrictInputSchema):
    """Attributes for updating a request via JSON:API."""

    status: RequestStatus | None = Field(None, description="Updated request status")
    note_id: UUID | None = Field(None, description="Associated note ID")


class RequestUpdateData(BaseModel):
    """JSON:API data object for request update."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["requests"] = Field(..., description="Resource type must be 'requests'")
    id: str = Field(..., description="Request ID being updated")
    attributes: RequestUpdateAttributes


class RequestUpdateRequest(BaseModel):
    """JSON:API request body for updating a request."""

    model_config = ConfigDict(extra="forbid")

    data: RequestUpdateData


class RequestAttributes(SQLAlchemySchema):
    """Request attributes for JSON:API resource."""

    request_id: str
    requested_by: str
    status: str = "PENDING"
    note_id: str | None = None
    community_server_id: str | None = None
    requested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    content: str | None = None
    platform_message_id: str | None = None
    metadata: dict[str, Any] | None = None
    similarity_score: float | None = None
    dataset_name: str | None = None
    dataset_item_id: str | None = None


class RequestResource(BaseModel):
    """JSON:API resource object for a request."""

    type: str = "requests"
    id: str
    attributes: RequestAttributes


class RequestListJSONAPIResponse(SQLAlchemySchema):
    """JSON:API response for a list of request resources."""

    data: list[RequestResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class RequestSingleResponse(SQLAlchemySchema):
    """JSON:API response for a single request resource."""

    data: RequestResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def request_to_resource(req: Request) -> RequestResource:
    """Convert a Request model to a JSON:API resource object."""
    return RequestResource(
        type="requests",
        id=str(req.id),
        attributes=RequestAttributes(
            request_id=req.request_id,
            requested_by=req.requested_by,
            status=req.status,
            note_id=str(req.note_id) if req.note_id else None,
            community_server_id=str(req.community_server_id) if req.community_server_id else None,
            requested_at=req.requested_at,
            created_at=req.created_at,
            updated_at=req.updated_at,
            content=req.content,
            platform_message_id=req.message_archive.platform_message_id
            if req.message_archive
            else None,
            metadata=req.request_metadata,
            similarity_score=req.similarity_score,
            dataset_name=req.dataset_name,
            dataset_item_id=req.dataset_item_id,
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


def _normalize_datetime(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to naive UTC for database comparison.

    The requests.requested_at column is stored as TIMESTAMP WITHOUT TIME ZONE.
    We need to convert timezone-aware datetimes to naive datetimes for comparison.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(pendulum.UTC).replace(tzinfo=None)
    return dt


request_filter_builder = FilterBuilder(
    FilterField(Request.status, operators=[FilterOperator.EQ]),
    FilterField(Request.requested_by, operators=[FilterOperator.EQ]),
    FilterField(
        Request.requested_at,
        operators=[FilterOperator.GTE, FilterOperator.LTE],
        transform=_normalize_datetime,
    ),
    FilterField(
        Request.community_server_id,
        alias="community_server_id",
        operators=[FilterOperator.EQ, FilterOperator.IN],
    ),
)


@router.get("/requests", response_class=JSONResponse, response_model=RequestListJSONAPIResponse)
async def list_requests_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_status: RequestStatus | None = Query(None, alias="filter[status]"),
    filter_community_server_id: UUID | None = Query(None, alias="filter[community_server_id]"),
    filter_requested_by: str | None = Query(None, alias="filter[requested_by]"),
    filter_requested_at_gte: datetime | None = Query(None, alias="filter[requested_at__gte]"),
    filter_requested_at_lte: datetime | None = Query(None, alias="filter[requested_at__lte]"),
) -> JSONResponse:
    """List requests with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by request status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
    - filter[community_server_id]: Filter by community server UUID
    - filter[requested_by]: Filter by requester participant ID
    - filter[requested_at__gte]: Requests created on or after this datetime
    - filter[requested_at__lte]: Requests created on or before this datetime

    Returns JSON:API formatted response with data, jsonapi, links, and meta.
    """
    try:
        query = select(Request).options(*loaders.request_with_archive())

        community_server_id_value = filter_community_server_id
        community_server_id_in_value = None
        if filter_community_server_id:
            if not is_service_account(current_user):
                await verify_community_membership_by_uuid(
                    filter_community_server_id, current_user, db, request
                )
        elif not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                community_server_id_value = None
                community_server_id_in_value = user_communities
            else:
                response = RequestListJSONAPIResponse(
                    data=[],
                    links=create_pagination_links_from_request(request, page_number, page_size, 0),
                    meta=JSONAPIMeta(count=0),
                )
                return JSONResponse(
                    content=response.model_dump(by_alias=True, mode="json"),
                    media_type=JSONAPI_CONTENT_TYPE,
                )

        filters = request_filter_builder.build(
            status=filter_status,
            requested_by=filter_requested_by,
            requested_at__gte=filter_requested_at_gte,
            requested_at__lte=filter_requested_at_lte,
            community_server_id=community_server_id_value,
            community_server_id__in=community_server_id_in_value,
        )

        if filters:
            query = query.where(and_(*filters))

        total_query = select(func.count(Request.id))
        if filters:
            total_query = total_query.where(and_(*filters))
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        query = query.order_by(desc(Request.requested_at))
        query = query.limit(page_size).offset((page_number - 1) * page_size)

        result = await db.execute(query)
        requests = result.scalars().all()

        request_resources = [request_to_resource(req) for req in requests]

        response = RequestListJSONAPIResponse(
            data=request_resources,
            links=create_pagination_links_from_request(request, page_number, page_size, total),
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list requests (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list requests",
        )


@router.get(
    "/requests/{request_id}", response_class=JSONResponse, response_model=RequestSingleResponse
)
async def get_request_jsonapi(
    request_id: str,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get a single request by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(
            select(Request)
            .options(*loaders.request_with_archive())
            .where(Request.request_id == request_id)
        )
        note_request = result.scalar_one_or_none()

        if not note_request:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Request {request_id} not found",
            )

        if not is_service_account(current_user) and note_request.community_server_id:
            await verify_community_membership_by_uuid(
                note_request.community_server_id, current_user, db, request
            )

        request_resource = request_to_resource(note_request)

        response = RequestSingleResponse(
            data=request_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get request (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get request",
        )


async def _create_message_archive(
    db: AsyncSession,
    request_data: RequestCreateAttributes,
) -> MessageArchive:
    """Create message archive from request data."""
    if not request_data.original_message_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content is required for text messages",
        )

    message_archive = await MessageArchiveService.create_from_text(
        db=db,
        content=request_data.original_message_content,
        platform_message_id=request_data.platform_message_id,
        platform_channel_id=request_data.platform_channel_id,
        platform_author_id=request_data.platform_author_id,
        platform_timestamp=request_data.platform_timestamp,
    )
    logger.info(
        f"Created text message archive {message_archive.id} for request {request_data.request_id}"
    )
    return message_archive


@router.post(
    "/requests",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=RequestSingleResponse,
)
async def create_request_jsonapi(
    request: HTTPRequest,
    body: RequestCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a new request with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        attrs = body.data.attributes

        duplicate_result = await db.execute(
            select(Request).where(Request.request_id == attrs.request_id)
        )
        if duplicate_result.scalar_one_or_none():
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"Request {attrs.request_id} already exists",
            )

        community_server = await get_community_server_by_platform_id(
            db=db,
            community_server_id=attrs.community_server_id,
            platform="discord",
            auto_create=True,
        )
        if not community_server:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                f"Failed to resolve community server for ID: {attrs.community_server_id}",
            )

        message_archive = await _create_message_archive(db, attrs)

        request_dict = {
            "request_id": attrs.request_id,
            "requested_by": attrs.requested_by,
            "community_server_id": community_server.id,
            "message_archive_id": message_archive.id,
        }

        if attrs.metadata:
            request_dict["request_metadata"] = attrs.metadata  # pyright: ignore[reportArgumentType]
        if attrs.similarity_score is not None:
            request_dict["similarity_score"] = attrs.similarity_score
        if attrs.dataset_name is not None:
            request_dict["dataset_name"] = attrs.dataset_name
        if attrs.dataset_item_id is not None:
            request_dict["dataset_item_id"] = attrs.dataset_item_id

        note_request = Request(**request_dict)
        db.add(note_request)
        await db.commit()

        result = await db.execute(
            select(Request)
            .options(*loaders.request_with_archive())
            .where(Request.id == note_request.id)
        )
        note_request = result.scalar_one()

        logger.info(
            f"Created request {note_request.request_id} via JSON:API by user {current_user.id}"
        )

        request_resource = request_to_resource(note_request)
        response = RequestSingleResponse(
            data=request_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{note_request.request_id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create request (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create request",
        )


@router.patch(
    "/requests/{request_id}", response_class=JSONResponse, response_model=RequestSingleResponse
)
async def update_request_jsonapi(
    request_id: str,
    request: HTTPRequest,
    body: RequestUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    note_request: Annotated[Request, Depends(verify_request_ownership)],
) -> JSONResponse:
    """Update a request with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        if body.data.id != request_id:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"ID in URL ({request_id}) does not match ID in request body ({body.data.id})",
            )

        update_data = body.data.attributes.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(note_request, field, value)

        await db.commit()

        result = await db.execute(
            select(Request)
            .options(*loaders.request_with_archive())
            .where(Request.id == note_request.id)
        )
        note_request = result.scalar_one()

        logger.info(f"Updated request {request_id} via JSON:API by user {current_user.id}")

        request_resource = request_to_resource(note_request)
        response = RequestSingleResponse(
            data=request_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update request (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update request",
        )


@router.post(
    "/requests/{request_id}/ai-notes",
    response_class=JSONResponse,
    response_model=NoteSingleResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute;20/hour")
async def generate_ai_note_jsonapi(  # noqa: PLR0911
    request_id: str,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    ai_note_writer: Annotated["AINoteWriter", Depends(get_ai_note_writer)],
) -> JSONResponse:
    """Generate an AI-powered note for a specific request in JSON:API format.

    This endpoint triggers on-demand AI note generation for requests that have
    associated fact-check data. The AI will analyze the original message and
    the matched fact-check information to generate a helpful community note.

    Requirements:
    - Request must exist and have fact-check metadata (dataset_item_id, similarity_score, dataset_name)
    - AI note writing must be enabled for the community server
    - Rate limits: 5 per minute, 20 per hour

    Returns JSON:API formatted response with the generated note resource.
    """
    try:
        logger.info(
            f"Generating AI note for request {request_id} (JSON:API)",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )

        note = await ai_note_writer.generate_note_for_request(db, request_id)

        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note.id))
        note_with_relations = result.scalar_one()

        logger.info(
            f"Successfully generated AI note {note.id} for request {request_id} (JSON:API)",
            extra={
                "note_id": note.id,
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )

        note_resource = note_to_resource(note_with_relations)
        response = NoteSingleResponse(
            data=note_resource,
            links=JSONAPILinks(self_=f"/api/v2/notes/{note.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except ValueError as e:
        logger.warning(
            f"Validation error generating AI note (JSON:API): {e}",
            extra={
                "request_id": request_id,
                "error": str(e),
            },
        )
        return create_error_response(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            str(e),
        )
    except HTTPException:
        raise
    except AuthenticationError as e:
        logger.error(
            f"OpenAI authentication failed for request {request_id} (JSON:API): {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        return create_error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service Unavailable",
            "AI note generation service is misconfigured",
        )
    except RateLimitError as e:
        logger.warning(
            f"OpenAI rate limit exceeded for request {request_id} (JSON:API): {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        return create_error_response(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too Many Requests",
            "AI service rate limit exceeded. Please try again later.",
        )
    except APIConnectionError as e:
        logger.error(
            f"OpenAI connection failed for request {request_id} (JSON:API): {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        return create_error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service Unavailable",
            "AI note generation service is temporarily unavailable",
        )
    except APIError as e:
        logger.error(
            f"OpenAI API error for request {request_id} (JSON:API): {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        return create_error_response(
            status.HTTP_502_BAD_GATEWAY,
            "Bad Gateway",
            f"AI service error: {str(e)[:100]}",
        )
    except Exception as e:
        logger.exception(
            f"Failed to generate AI note for request {request_id} (JSON:API): {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to generate AI note",
        )
