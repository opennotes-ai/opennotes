"""JSON:API v2 notes router.

This module implements a JSON:API 1.0 compliant endpoint for notes.
It provides:
- Standard JSON:API response envelope structure
- Advanced filtering with operators (neq, gte, lte, not_in)
- Pagination support
- Write operations (POST, PATCH, DELETE)
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/

Filter operators supported (via fastapi-filter style syntax):
- filter[status]: Exact match on status
- filter[status__neq]: Status not equal to value
- filter[created_at__gte]: Created at >= datetime
- filter[created_at__lte]: Created at <= datetime
- filter[rated_by_participant_id__not_in]: Exclude notes rated by these users
- filter[rated_by_participant_id]: Include only notes rated by this user
"""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, exists, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    _get_profile_id_from_user,
    get_user_community_ids,
    verify_community_admin_by_uuid,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.ownership_dependencies import verify_note_ownership
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
from src.events.publisher import event_publisher
from src.monitoring import get_logger
from src.notes import loaders
from src.notes.message_archive_models import MessageArchive
from src.notes.models import Note, Rating, Request
from src.notes.schemas import (
    NoteClassification,
    NoteJSONAPIAttributes,
    NoteListResponse,
    NoteResource,
    NoteSingleResponse,
    NoteStatus,
)
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


class NoteCreateAttributes(StrictInputSchema):
    """Attributes for creating a note via JSON:API."""

    summary: str = Field(..., min_length=1, description="Note summary text")
    classification: NoteClassification = Field(..., description="Note classification")
    community_server_id: UUID = Field(..., description="Community server ID")
    author_participant_id: str = Field(..., description="Author's participant ID")
    channel_id: str | None = Field(None, description="Discord channel ID")
    request_id: str | None = Field(None, description="Request ID this note responds to")


class NoteCreateData(BaseModel):
    """JSON:API data object for note creation."""

    type: Literal["notes"] = Field(..., description="Resource type must be 'notes'")
    attributes: NoteCreateAttributes


class NoteCreateRequest(BaseModel):
    """JSON:API request body for creating a note."""

    data: NoteCreateData


class NoteUpdateAttributes(StrictInputSchema):
    """Attributes for updating a note via JSON:API."""

    summary: str | None = Field(None, description="Updated note summary")
    classification: NoteClassification | None = Field(None, description="Updated classification")


class NoteUpdateData(BaseModel):
    """JSON:API data object for note update."""

    type: Literal["notes"] = Field(..., description="Resource type must be 'notes'")
    id: str = Field(..., description="Note ID being updated")
    attributes: NoteUpdateAttributes


class NoteUpdateRequest(BaseModel):
    """JSON:API request body for updating a note."""

    data: NoteUpdateData


def note_to_resource(note: Note) -> NoteResource:
    """Convert a Note model to a JSON:API resource object."""
    platform_message_id = None
    if note.request and note.request.message_archive:
        platform_message_id = note.request.message_archive.platform_message_id

    return NoteResource(
        type="notes",
        id=str(note.id),
        attributes=NoteJSONAPIAttributes(
            author_participant_id=note.author_participant_id,
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


def create_pagination_links_from_request(
    request: HTTPRequest,
    page: int,
    size: int,
    total: int,
    openapi_url: str = "/api/v2/openapi.json",
) -> JSONAPILinks:
    """Create JSON:API pagination links from a FastAPI request.

    Wrapper around the common create_pagination_links that extracts
    base URL and query params from the request object. Includes JSON:API 1.1
    describedby link for API documentation.

    Args:
        request: FastAPI request object
        page: Current page number
        size: Page size
        total: Total items
        openapi_url: URL to OpenAPI schema documentation (default: /api/v2/openapi.json)
    """
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


def _build_attribute_filters(
    filter_status: NoteStatus | None,
    filter_status_neq: NoteStatus | None,
    filter_classification: NoteClassification | None,
    filter_author_id: str | None,
    filter_request_id: str | None,
    filter_created_at_gte: datetime | None,
    filter_created_at_lte: datetime | None,
    filter_rated_by_not_in: list[str] | None,
    filter_rated_by: str | None = None,
) -> list:
    """Build a list of filter conditions for note attributes.

    Supports the following filter operators:
    - Equality: filter[field]=value
    - Not equal: filter[field__neq]=value
    - Greater than or equal: filter[field__gte]=value
    - Less than or equal: filter[field__lte]=value
    - Not in (exclusion): filter[rated_by_participant_id__not_in]=user1,user2
    - In (inclusion): filter[rated_by_participant_id]=user1 (notes rated by user)
    """
    filters = []

    if filter_status is not None:
        filters.append(Note.status == filter_status)

    if filter_status_neq is not None:
        filters.append(Note.status != filter_status_neq)

    if filter_classification is not None:
        filters.append(Note.classification == filter_classification)

    if filter_author_id is not None:
        filters.append(Note.author_participant_id == filter_author_id)

    if filter_request_id is not None:
        filters.append(Note.request_id == filter_request_id)

    if filter_created_at_gte is not None:
        filters.append(Note.created_at >= filter_created_at_gte)

    if filter_created_at_lte is not None:
        filters.append(Note.created_at <= filter_created_at_lte)

    if filter_rated_by_not_in:
        rating_subquery = select(Rating.note_id).where(
            Rating.rater_participant_id.in_(filter_rated_by_not_in)
        )
        filters.append(not_(exists(rating_subquery.where(Rating.note_id == Note.id))))

    if filter_rated_by:
        filters.append(
            Note.id.in_(
                select(Rating.note_id).where(Rating.rater_participant_id == filter_rated_by)
            )
        )

    return filters


@router.get("/notes", response_class=JSONResponse, response_model=NoteListResponse)
async def list_notes_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_status: NoteStatus | None = Query(None, alias="filter[status]"),
    filter_status_neq: NoteStatus | None = Query(None, alias="filter[status__neq]"),
    filter_classification: NoteClassification | None = Query(None, alias="filter[classification]"),
    filter_community_server_id: UUID | None = Query(None, alias="filter[community_server_id]"),
    filter_author_id: str | None = Query(None, alias="filter[author_participant_id]"),
    filter_request_id: str | None = Query(None, alias="filter[request_id]"),
    filter_created_at_gte: datetime | None = Query(None, alias="filter[created_at__gte]"),
    filter_created_at_lte: datetime | None = Query(None, alias="filter[created_at__lte]"),
    filter_rated_by_not_in: str | None = Query(
        None, alias="filter[rated_by_participant_id__not_in]"
    ),
    filter_rated_by: str | None = Query(None, alias="filter[rated_by_participant_id]"),
    filter_platform_message_id: str | None = Query(None, alias="filter[platform_message_id]"),
) -> JSONResponse:
    """List notes with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters (equality):
    - filter[status]: Filter by note status (exact match)
    - filter[classification]: Filter by classification
    - filter[community_server_id]: Filter by community server UUID
    - filter[author_participant_id]: Filter by author
    - filter[request_id]: Filter by request ID
    - filter[platform_message_id]: Filter by platform message ID (Discord snowflake)

    Filter Parameters (operators):
    - filter[status__neq]: Exclude notes with this status
    - filter[created_at__gte]: Notes created on or after this datetime
    - filter[created_at__lte]: Notes created on or before this datetime
    - filter[rated_by_participant_id__not_in]: Exclude notes rated by these users
      (comma-separated list of participant IDs)
    - filter[rated_by_participant_id]: Include only notes rated by this user

    Returns JSON:API formatted response with data, jsonapi, links, and meta.
    """
    try:
        query = select(Note).options(*loaders.full())

        rated_by_list = (
            [x.strip() for x in filter_rated_by_not_in.split(",") if x.strip()]
            if filter_rated_by_not_in
            else None
        )

        filters = _build_attribute_filters(
            filter_status=filter_status,
            filter_status_neq=filter_status_neq,
            filter_classification=filter_classification,
            filter_author_id=filter_author_id,
            filter_request_id=filter_request_id,
            filter_created_at_gte=filter_created_at_gte,
            filter_created_at_lte=filter_created_at_lte,
            filter_rated_by_not_in=rated_by_list,
            filter_rated_by=filter_rated_by,
        )

        if filter_community_server_id:
            if not is_service_account(current_user):
                await verify_community_membership_by_uuid(
                    filter_community_server_id, current_user, db, request
                )
            filters.append(Note.community_server_id == filter_community_server_id)
        elif not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                filters.append(Note.community_server_id.in_(user_communities))
            else:
                response = NoteListResponse(
                    data=[],
                    links=create_pagination_links_from_request(request, page_number, page_size, 0),
                    meta=JSONAPIMeta(count=0),
                )
                return JSONResponse(
                    content=response.model_dump(by_alias=True, mode="json"),
                    media_type=JSONAPI_CONTENT_TYPE,
                )

        if filter_platform_message_id:
            query = query.join(Request, Note.request_id == Request.request_id).join(
                MessageArchive, Request.message_archive_id == MessageArchive.id
            )
            filters.append(MessageArchive.platform_message_id == filter_platform_message_id)

        if filters:
            query = query.where(and_(*filters))

        total_query = select(func.count(Note.id))
        if filter_platform_message_id:
            total_query = total_query.join(Request, Note.request_id == Request.request_id).join(
                MessageArchive, Request.message_archive_id == MessageArchive.id
            )
        if filters:
            total_query = total_query.where(and_(*filters))
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        query = query.order_by(desc(Note.created_at))
        query = query.limit(page_size).offset((page_number - 1) * page_size)

        result = await db.execute(query)
        notes = result.scalars().all()

        note_resources = [note_to_resource(note) for note in notes]

        response = NoteListResponse(
            data=note_resources,
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
        logger.exception(f"Failed to list notes (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list notes",
        )


@router.get("/notes/{note_id}", response_class=JSONResponse, response_model=NoteSingleResponse)
async def get_note_jsonapi(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get a single note by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note_id))
        note = result.scalar_one_or_none()

        if not note:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note {note_id} not found",
            )

        if not is_service_account(current_user) and note.community_server_id:
            await verify_community_membership_by_uuid(
                note.community_server_id, current_user, db, request
            )

        note_resource = note_to_resource(note)

        response = NoteSingleResponse(
            data=note_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get note (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get note",
        )


@router.post(
    "/notes",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=NoteSingleResponse,
)
async def create_note_jsonapi(
    request: HTTPRequest,
    body: NoteCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create a new note with JSON:API format.

    JSON:API 1.0 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        attrs = body.data.attributes

        # Check for duplicate notes (same request_id and author)
        if attrs.request_id:
            duplicate_result = await db.execute(
                select(Note).where(
                    (Note.request_id == attrs.request_id)
                    & (Note.author_participant_id == attrs.author_participant_id)
                )
            )
            if duplicate_result.scalar_one_or_none():
                return create_error_response(
                    status.HTTP_409_CONFLICT,
                    "Conflict",
                    f"A note already exists for request {attrs.request_id} by author {attrs.author_participant_id}",
                )

        note_dict = attrs.model_dump(mode="python")

        if note_dict.get("request_id"):
            request_result = await db.execute(
                select(Request).where(Request.request_id == note_dict["request_id"])
            )
            linked_request = request_result.scalar_one_or_none()
            if not linked_request:
                return create_error_response(
                    status.HTTP_404_NOT_FOUND,
                    "Not Found",
                    f"Request {note_dict['request_id']} not found",
                )
            if linked_request.community_server_id != attrs.community_server_id:
                return create_error_response(
                    status.HTTP_400_BAD_REQUEST,
                    "Bad Request",
                    "Note community_server_id must match request's community_server_id",
                )
            linked_request.status = "IN_PROGRESS"

        note = Note(**note_dict)
        db.add(note)
        await db.commit()

        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note.id))
        note = result.scalar_one()

        logger.info(f"Created note {note.id} via JSON:API by user {current_user.id}")

        note_resource = note_to_resource(note)
        response = NoteSingleResponse(
            data=note_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{note.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create note (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create note",
        )


@router.patch("/notes/{note_id}", response_class=JSONResponse, response_model=NoteSingleResponse)
async def update_note_jsonapi(
    note_id: UUID,
    request: HTTPRequest,
    body: NoteUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    note: Annotated[Note, Depends(verify_note_ownership)],
) -> JSONResponse:
    """Update a note with JSON:API format.

    JSON:API 1.0 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        if body.data.id != str(note_id):
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"ID in URL ({note_id}) does not match ID in request body ({body.data.id})",
            )

        update_data = body.data.attributes.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(note, field, value)

        await db.commit()

        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note.id))
        note = result.scalar_one()

        logger.info(f"Updated note {note_id} via JSON:API by user {current_user.id}")

        note_resource = note_to_resource(note)
        response = NoteSingleResponse(
            data=note_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update note (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update note",
        )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_jsonapi(
    note_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    note: Annotated[Note, Depends(verify_note_ownership)],
) -> None:
    """Delete a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 204 No Content status on success
    - Response with JSON:API error format on failure

    Returns None (204 No Content) on success.
    """
    try:
        await db.delete(note)
        await db.commit()

        logger.info(f"Deleted note {note_id} via JSON:API by user {current_user.id}")

        return

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete note (JSON:API): {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete note",
        )


@router.post(
    "/notes/{note_id}/force-publish", response_class=JSONResponse, response_model=NoteSingleResponse
)
async def force_publish_note_jsonapi(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Force-publish a note with JSON:API format (admin only).

    This endpoint allows administrators to manually publish notes that haven't met
    automatic publication thresholds. The note is marked with force_published flags
    for transparency, and the action is logged with admin user ID and timestamp.

    Requires admin authentication (service accounts, Open Notes admins, or community admins).

    Returns JSON:API formatted response with updated note resource.
    """
    try:
        result = await db.execute(select(Note).options(*loaders.admin()).where(Note.id == note_id))
        note = result.scalar_one_or_none()

        if not note:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note {note_id} not found",
            )

        if not note.community_server_id:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                f"Note {note_id} has no associated community server",
            )

        await verify_community_admin_by_uuid(note.community_server_id, current_user, db, request)

        admin_profile_id = await _get_profile_id_from_user(db, current_user)
        if not admin_profile_id:
            return create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "Failed to determine admin profile ID",
            )

        note.force_published = True
        note.force_published_by = admin_profile_id
        note.force_published_at = datetime.now(UTC).replace(tzinfo=None)
        note.status = "CURRENTLY_RATED_HELPFUL"

        if note.request_id:
            request_result = await db.execute(
                select(Request).where(Request.request_id == note.request_id)
            )
            associated_request = request_result.scalar_one_or_none()
            if associated_request:
                associated_request.status = "COMPLETED"
                logger.info(
                    "Updated request status to COMPLETED for force-published note",
                    extra={
                        "request_id": note.request_id,
                        "note_id": note_id,
                    },
                )

        await db.commit()
        await db.refresh(note)

        logger.info(
            f"Force-published note {note_id} via JSON:API by admin {current_user.id} "
            f"(profile {admin_profile_id})",
            extra={
                "note_id": note_id,
                "admin_user_id": current_user.id,
                "admin_profile_id": str(admin_profile_id),
                "community_server_id": str(note.community_server_id),
                "force_published_at": (
                    fpa.isoformat() if (fpa := note.force_published_at) else None
                ),
            },
        )

        original_message_id = None
        channel_id = None
        if note.request and note.request.message_archive:
            original_message_id = note.request.message_archive.platform_message_id
            channel_id = note.request.message_archive.platform_channel_id

        if not channel_id:
            channel_id = note.channel_id

        force_publish_metadata: dict[str, str | bool | None] = {
            "force_published": True,
            "force_published_by": str(admin_profile_id),
            "force_published_at": (fpa.isoformat() if (fpa := note.force_published_at) else None),
        }

        if note.force_published_by_profile:
            force_publish_metadata["admin_username"] = note.force_published_by_profile.display_name

        try:
            await event_publisher.publish_note_score_updated(
                note_id=note.id,
                score=1.0,
                confidence="standard",
                algorithm="admin_override",
                rating_count=len(note.ratings) if note.ratings else 0,
                tier=3,
                tier_name="admin_published",
                original_message_id=original_message_id,
                channel_id=channel_id,
                community_server_id=str(note.community_server_id)
                if note.community_server_id
                else None,
                metadata=force_publish_metadata,
            )
            logger.info(f"Published score update event for force-published note {note_id}")
        except Exception as e:
            logger.error(
                f"Failed to publish score update event for note {note_id}: {e}", exc_info=True
            )

        note_resource = note_to_resource(note)
        response = NoteSingleResponse(
            data=note_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to force-publish note (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to force-publish note",
        )
