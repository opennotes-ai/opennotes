from datetime import datetime
from time import perf_counter
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    RateLimitError,
)
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
from src.database import get_db
from src.events.publisher import event_publisher
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.notes import loaders
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.message_archive_service import MessageArchiveService
from src.notes.models import Note, Request
from src.notes.schemas import (
    NoteResponse,
    RequestCreate,
    RequestListResponse,
    RequestResponse,
    RequestStatus,
    RequestUpdate,
)
from src.services.ai_note_writer import AINoteWriter
from src.services.vision_service import VisionService
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


def get_ai_note_writer(http_request: HTTPRequest) -> AINoteWriter:
    """Dependency to get AINoteWriter service from app state."""
    ai_note_writer = getattr(http_request.app.state, "ai_note_writer", None)
    if ai_note_writer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI note writing service is not available",
        )
    return cast(AINoteWriter, ai_note_writer)


def get_vision_service(http_request: HTTPRequest) -> VisionService | None:
    """Dependency to get VisionService from app state (optional)."""
    return getattr(http_request.app.state, "vision_service", None)


async def _create_message_archive(
    db: AsyncSession,
    request_data: RequestCreate,
    vision_service: VisionService | None,
) -> MessageArchive:
    """Create message archive from request data, handling various attachment types."""

    if request_data.attachment_url and request_data.attachment_type == "image":
        message_archive = MessageArchive(
            content_type=ContentType.IMAGE,
            content_url=request_data.attachment_url,
            content_text=request_data.original_message_content or None,
            platform_message_id=request_data.platform_message_id,
            platform_channel_id=request_data.platform_channel_id,
            platform_author_id=request_data.platform_author_id,
            platform_timestamp=request_data.platform_timestamp,
        )
        db.add(message_archive)
        await db.flush()
        vision_note = (
            " (vision description will be generated asynchronously)"
            if vision_service
            else " (no vision service)"
        )
        logger.info(
            f"Created image attachment message archive {message_archive.id} for request {request_data.request_id}{vision_note}",
            extra={"image_url": request_data.attachment_url[:100]},
        )
        return message_archive

    if request_data.attachment_url and request_data.attachment_type == "video":
        message_archive = MessageArchive(
            content_type=ContentType.VIDEO,
            content_url=request_data.attachment_url,
            content_text=request_data.original_message_content or None,
            platform_message_id=request_data.platform_message_id,
            platform_channel_id=request_data.platform_channel_id,
            platform_author_id=request_data.platform_author_id,
            platform_timestamp=request_data.platform_timestamp,
        )
        db.add(message_archive)
        await db.flush()
        logger.info(
            f"Created video message archive {message_archive.id} for request {request_data.request_id}",
            extra={"video_url": request_data.attachment_url[:100]},
        )
        return message_archive

    if request_data.embedded_image_url:
        message_archive = MessageArchive(
            content_type=ContentType.IMAGE,
            content_url=request_data.embedded_image_url,
            content_text=request_data.original_message_content or None,
            platform_message_id=request_data.platform_message_id,
            platform_channel_id=request_data.platform_channel_id,
            platform_author_id=request_data.platform_author_id,
            platform_timestamp=request_data.platform_timestamp,
        )
        db.add(message_archive)
        await db.flush()
        vision_note = (
            " (vision description will be generated asynchronously)"
            if vision_service
            else " (no vision service)"
        )
        logger.info(
            f"Created embedded image message archive {message_archive.id} for request {request_data.request_id}{vision_note}",
            extra={"image_url": request_data.embedded_image_url[:100]},
        )
        return message_archive

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


@router.post("/requests", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(  # noqa: PLR0912 - Complex validation and processing logic for request creation
    request_data: RequestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    vision_service: Annotated["VisionService | None", Depends(get_vision_service)],
) -> RequestResponse:
    """Create a new note request"""
    start_time = perf_counter()
    timings = {}

    try:
        # Check for duplicate request
        t0 = perf_counter()
        existing_request = await db.execute(
            select(Request).where(Request.request_id == request_data.request_id)
        )
        if existing_request.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Request {request_data.request_id} already exists",
            )
        timings["duplicate_check"] = perf_counter() - t0

        # Look up or create CommunityServer from platform ID (Discord guild ID)
        t0 = perf_counter()
        community_server = await get_community_server_by_platform_id(
            db=db,
            community_server_id=request_data.community_server_id,
            platform="discord",
            auto_create=True,
        )
        if not community_server:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to resolve community server for ID: {request_data.community_server_id}",
            )
        timings["community_server_lookup"] = perf_counter() - t0

        # Create MessageArchive - handle attachments (images/videos) or text content
        t0 = perf_counter()
        message_archive = await _create_message_archive(db, request_data, vision_service)
        message_archive_id = message_archive.id
        timings["message_archive_creation"] = perf_counter() - t0

        # Create request without platform metadata fields (they're in MessageArchive now)
        t0 = perf_counter()
        request_dict = request_data.model_dump(
            mode="python",
            exclude={
                "platform_message_id",
                "platform_channel_id",
                "platform_author_id",
                "platform_timestamp",
                "original_message_content",  # Don't store in Request anymore
                "community_server_id",  # Will be replaced with UUID below
                "attachment_url",  # Stored in MessageArchive
                "attachment_type",  # Stored in MessageArchive
                "attachment_metadata",  # Stored in MessageArchive (not used yet)
                "embedded_image_url",  # Stored in MessageArchive
            },
        )
        request_dict["message_archive_id"] = message_archive_id
        request_dict["community_server_id"] = community_server.id  # Store UUID, not platform ID

        # Map Pydantic 'metadata' field to SQLAlchemy 'request_metadata' field
        # Also extract fact-check metadata to individual columns for AI note writing trigger
        if "metadata" in request_dict:
            metadata = request_dict["metadata"]
            request_dict["request_metadata"] = metadata

            # Extract fact-check fields for AI note writing
            if metadata and isinstance(metadata, dict):
                if "dataset_item_id" in metadata:
                    request_dict["dataset_item_id"] = metadata["dataset_item_id"]
                if "similarity_score" in metadata:
                    request_dict["similarity_score"] = metadata["similarity_score"]
                if "dataset_name" in metadata:
                    request_dict["dataset_name"] = metadata["dataset_name"]

            request_dict.pop("metadata")

        request = Request(**request_dict)
        db.add(request)
        await db.commit()

        # Reload request with message_archive relationship loaded
        result = await db.execute(
            select(Request).options(*loaders.request_with_archive()).where(Request.id == request.id)
        )
        request = result.scalar_one()
        timings["request_creation"] = perf_counter() - t0

        logger.info(f"Created request {request.request_id} by user {current_user.id}")

        # Publish events
        t0 = perf_counter()
        try:
            # Get platform_message_id from message archive
            platform_message_id = (
                request.message_archive.platform_message_id if request.message_archive else None
            )

            if platform_message_id is None:
                logger.error(
                    f"Cannot publish request events: no platform_message_id available for {request.request_id}"
                )
            else:
                # Note: status and priority are already string values due to use_enum_values=True
                priority_str: str = (
                    request.priority
                    if request.priority is None or isinstance(request.priority, str)
                    else request.priority.value
                ) or "medium"

                await event_publisher.publish_note_request_created(
                    request_id=request.request_id,
                    platform_message_id=platform_message_id,
                    requested_by=request.requested_by,
                    status=request.status
                    if isinstance(request.status, str)
                    else request.status.value,
                    priority=priority_str,
                    similarity_score=request.similarity_score,
                    dataset_name=request.dataset_name,
                    dataset_item_id=request.dataset_item_id,
                    metadata={
                        "user_id": current_user.id,
                        "reason": request.reason,
                    },
                )
                logger.info(f"Published note request created event for {request.request_id}")

                # If this is an auto-created request with fact-check match, publish special event for AI note writing
                if (
                    request.dataset_item_id
                    and request.similarity_score
                    and request.dataset_name
                    and request.content
                ):
                    await event_publisher.publish_request_auto_created(
                        request_id=request.request_id,
                        platform_message_id=platform_message_id,
                        fact_check_item_id=request.dataset_item_id,
                        community_server_id=str(request.community_server_id),
                        content=request.content,
                        similarity_score=request.similarity_score,
                        dataset_name=request.dataset_name,
                        metadata={
                            "user_id": current_user.id,
                            "reason": request.reason,
                        },
                    )
                    logger.info(
                        f"Published request auto-created event for AI note writing: {request.request_id}"
                    )
        except Exception as e:
            logger.error(f"Failed to publish request events: {e}")

        timings["event_publishing"] = perf_counter() - t0

        # Publish vision service event for asynchronous processing if we have images
        if (
            request_data.attachment_url and request_data.attachment_type == "image"
        ) or request_data.embedded_image_url:
            image_url = (
                request_data.attachment_url
                if request_data.attachment_url
                else request_data.embedded_image_url
            )
            if image_url:
                try:
                    await event_publisher.publish_vision_description_requested(
                        message_archive_id=str(message_archive_id),
                        image_url=image_url,
                        community_server_id=request_data.community_server_id,
                        request_id=request.request_id,
                    )
                    logger.info(
                        f"Published vision description requested event for message archive {message_archive_id}",
                        extra={"request_id": request.request_id, "image_url": image_url[:100]},
                    )
                except Exception as e:
                    logger.error(f"Failed to publish vision description event: {e}")

        total_time = perf_counter() - start_time
        logger.info(
            f"Request creation performance metrics for {request.request_id}",
            extra={
                "request_id": request.request_id,
                "total_time_ms": f"{total_time * 1000:.2f}",
                "duplicate_check_ms": f"{timings.get('duplicate_check', 0) * 1000:.2f}",
                "community_server_lookup_ms": f"{timings.get('community_server_lookup', 0) * 1000:.2f}",
                "message_archive_creation_ms": f"{timings.get('message_archive_creation', 0) * 1000:.2f}",
                "request_creation_ms": f"{timings.get('request_creation', 0) * 1000:.2f}",
                "event_publishing_ms": f"{timings.get('event_publishing', 0) * 1000:.2f}",
            },
        )

        # Use model_construct to bypass validators
        return RequestResponse.model_construct(
            id=request.id,
            request_id=request.request_id,
            requested_by=request.requested_by,
            requested_at=request.requested_at,
            status=request.status,
            note_id=str(request.note_id) if request.note_id is not None else None,
            community_server_id=request.community_server_id,
            created_at=request.created_at,
            updated_at=request.updated_at,
            content=request.content,
            platform_message_id=request.message_archive.platform_message_id
            if request.message_archive
            else None,
            request_metadata=request.request_metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create request: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create request",
        )


@router.get("/requests", response_model=RequestListResponse)
async def list_requests(  # noqa: PLR0912
    http_request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: RequestStatus | None = None,
    requested_by: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    community_server_id: UUID | None = None,
) -> RequestListResponse:
    """List requests with filters and pagination.

    Users can only see requests from communities they are members of.
    Service accounts can see all requests.
    """
    try:
        # Build query with message_archive loaded for content property
        query = select(Request).options(*loaders.request_with_archive())

        # Apply filters
        filters = []
        if status_filter:
            filters.append(Request.status == status_filter)
        if requested_by:
            filters.append(Request.requested_by == requested_by)
        if date_from:
            filters.append(Request.requested_at >= date_from)
        if date_to:
            filters.append(Request.requested_at <= date_to)

        # Community authorization filtering
        if community_server_id:
            # If specific community requested, verify membership first
            if not is_service_account(current_user):
                await verify_community_membership_by_uuid(
                    community_server_id, current_user, db, http_request
                )
            filters.append(Request.community_server_id == community_server_id)
        elif not is_service_account(current_user):
            # No specific community, filter to user's communities
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                filters.append(Request.community_server_id.in_(user_communities))
            else:
                # User is not a member of any community, return empty result
                return RequestListResponse(requests=[], total=0, page=page, size=size)

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        total_query = select(func.count(Request.id))
        if filters:
            total_query = total_query.where(and_(*filters))
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.order_by(desc(Request.requested_at))
        query = query.limit(size).offset((page - 1) * size)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Build responses with content field populated
        request_responses = []
        for req in requests:
            # Use model_construct to bypass validators
            response = RequestResponse.model_construct(
                id=req.id,
                request_id=req.request_id,
                requested_by=req.requested_by,
                requested_at=req.requested_at,
                status=req.status,
                note_id=str(req.note_id) if req.note_id is not None else None,
                community_server_id=req.community_server_id,
                created_at=req.created_at,
                updated_at=req.updated_at,
                content=req.content,
                platform_message_id=req.message_archive.platform_message_id
                if req.message_archive
                else None,
                request_metadata=req.request_metadata,
            )
            request_responses.append(response)

        return RequestListResponse(
            requests=request_responses,
            total=total,
            page=page,
            size=size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list requests",
        )


@router.get("/requests/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: str,
    http_request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> RequestResponse:
    """Get a specific request.

    Users can only view requests from communities they are members of.
    Service accounts can view all requests.
    """
    try:
        result = await db.execute(
            select(Request)
            .options(*loaders.request_with_archive())
            .where(Request.request_id == request_id)
        )
        note_request = result.scalar_one_or_none()

        if not note_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_id} not found",
            )

        # Verify community membership (service accounts bypass)
        if not is_service_account(current_user) and note_request.community_server_id:
            await verify_community_membership_by_uuid(
                note_request.community_server_id, current_user, db, http_request
            )

        # Use model_construct to bypass validators
        return RequestResponse.model_construct(
            id=note_request.id,
            request_id=note_request.request_id,
            requested_by=note_request.requested_by,
            requested_at=note_request.requested_at,
            status=note_request.status,
            note_id=str(note_request.note_id) if note_request.note_id is not None else None,
            community_server_id=note_request.community_server_id,
            created_at=note_request.created_at,
            updated_at=note_request.updated_at,
            content=note_request.content,
            platform_message_id=note_request.message_archive.platform_message_id
            if note_request.message_archive
            else None,
            request_metadata=note_request.request_metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get request",
        )


@router.patch("/requests/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: str,
    request_update: RequestUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    note_request: Annotated[Request, Depends(verify_request_ownership)],
) -> RequestResponse:
    """Update a request status.

    Users can only update requests they created or if they are a community admin.
    Service accounts can update any request.
    """
    try:
        update_data = request_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(note_request, field, value)

        await db.commit()

        result = await db.execute(
            select(Request)
            .options(*loaders.request_with_archive())
            .where(Request.id == note_request.id)
        )
        note_request = result.scalar_one()

        logger.info(f"Updated request {request_id} by user {current_user.id}")

        return RequestResponse.model_construct(
            id=note_request.id,
            request_id=note_request.request_id,
            requested_by=note_request.requested_by,
            requested_at=note_request.requested_at,
            status=note_request.status,
            note_id=str(note_request.note_id) if note_request.note_id is not None else None,
            community_server_id=note_request.community_server_id,
            created_at=note_request.created_at,
            updated_at=note_request.updated_at,
            content=note_request.content,
            platform_message_id=note_request.message_archive.platform_message_id
            if note_request.message_archive
            else None,
            request_metadata=note_request.request_metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update request: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update request",
        )


@router.post(
    "/requests/{request_id}/generate-ai-note",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute;20/hour")
async def generate_ai_note(
    request_id: str,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    ai_note_writer: Annotated["AINoteWriter", Depends(get_ai_note_writer)],
) -> NoteResponse:
    """
    Generate an AI-powered note for a specific request.

    This endpoint triggers on-demand AI note generation for requests that have
    associated fact-check data. The AI will analyze the original message and
    the matched fact-check information to generate a helpful community note.

    Requirements:
    - Request must exist and have fact-check metadata (dataset_item_id, similarity_score, dataset_name)
    - AI note writing must be enabled for the community server
    - Rate limits: 5 per minute, 20 per hour

    Returns:
        NoteResponse: The generated AI note
    """
    try:
        logger.info(
            f"Generating AI note for request {request_id}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )

        # Generate note using AI Note Writer service
        note = await ai_note_writer.generate_note_for_request(db, request_id)

        # Reload note with relationships for response
        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note.id))
        note_with_relations = result.scalar_one()

        logger.info(
            f"Successfully generated AI note {note.id} for request {request_id}",
            extra={
                "note_id": note.id,
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )

        return NoteResponse.model_validate(note_with_relations)

    except ValueError as e:
        # Handle validation errors (missing data, disabled service, etc.)
        logger.warning(
            f"Validation error generating AI note: {e}",
            extra={
                "request_id": request_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except AuthenticationError as e:
        logger.error(
            f"OpenAI authentication failed for request {request_id}: {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI note generation service is misconfigured",
        )
    except RateLimitError as e:
        logger.warning(
            f"OpenAI rate limit exceeded for request {request_id}: {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI service rate limit exceeded. Please try again later.",
        )
    except APIConnectionError as e:
        logger.error(
            f"OpenAI connection failed for request {request_id}: {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI note generation service is temporarily unavailable",
        )
    except APIError as e:
        logger.error(
            f"OpenAI API error for request {request_id}: {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service error: {str(e)[:100]}",
        )
    except Exception as e:
        logger.exception(
            f"Failed to generate AI note for request {request_id}: {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate AI note",
        )
