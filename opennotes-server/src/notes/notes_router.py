from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from sqlalchemy import and_, desc, func, select
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
from src.database import get_db
from src.events.publisher import event_publisher
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.notes import loaders
from src.notes.models import Note, Rating, Request
from src.notes.schemas import (
    NoteClassification,
    NoteCreate,
    NoteListResponse,
    NoteResponse,
    NoteStatus,
    NoteUpdate,
)
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


# Note CRUD endpoints
@router.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute;100/hour;500/day")
async def create_note(
    note_data: NoteCreate,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> NoteResponse:
    """Create a new community note"""
    try:
        # Check for duplicate notes (same request_id and author)
        if note_data.request_id:
            duplicate_result = await db.execute(
                select(Note).where(
                    (Note.request_id == note_data.request_id)
                    & (Note.author_participant_id == note_data.author_participant_id)
                )
            )
            if duplicate_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A note already exists for request {note_data.request_id} by author {note_data.author_participant_id}",
                )

        note_dict = note_data.model_dump(mode="python")

        # Validate community_server_id matches the linked request (if request_id provided)
        if note_dict.get("request_id"):
            request_result = await db.execute(
                select(Request).where(Request.request_id == note_dict["request_id"])
            )
            linked_request = request_result.scalar_one_or_none()
            if not linked_request:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {note_dict['request_id']} not found",
                )
            if linked_request.community_server_id != note_data.community_server_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Note community_server_id must match request's community_server_id",
                )
            linked_request.status = "IN_PROGRESS"
            logger.info(
                "Updated request status to IN_PROGRESS for note creation",
                extra={
                    "request_id": linked_request.request_id,
                    "note_author": note_data.author_participant_id,
                },
            )

        # Create new note
        note = Note(**note_dict)
        db.add(note)
        await db.commit()

        # Reload note with relationships explicitly loaded for response
        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note.id))
        note = result.scalar_one()

        logger.info(f"Created note {note.id} by user {current_user.id}")

        # Use model_validate for automatic conversion
        return NoteResponse.model_validate(note)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create note: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create note",
        )


@router.get("/notes", response_model=NoteListResponse)
async def list_notes(  # noqa: PLR0912
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    author_id: str | None = None,
    request_id: str | None = None,
    status_filter: NoteStatus | None = None,
    classification: NoteClassification | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    community_server_id: UUID | None = None,
    rated_by_participant_id: str | None = None,
    exclude_status: list[NoteStatus] | None = Query(default=None),
) -> NoteListResponse:
    """List notes with filters and pagination.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.
    """
    try:
        # Build query with relationships loaded for response
        query = select(Note).options(*loaders.full())

        # Apply filters
        filters = []
        if author_id:
            filters.append(Note.author_participant_id == author_id)
        if request_id:
            filters.append(Note.request_id == request_id)
        if status_filter:
            filters.append(Note.status == status_filter)
        if classification:
            filters.append(Note.classification == classification)
        if date_from:
            filters.append(Note.created_at >= date_from)
        if date_to:
            filters.append(Note.created_at <= date_to)
        if rated_by_participant_id:
            filters.append(
                Note.id.in_(
                    select(Rating.note_id).where(
                        Rating.rater_participant_id == rated_by_participant_id
                    )
                )
            )
        if exclude_status:
            filters.append(Note.status.not_in(exclude_status))

        # Community authorization filtering
        if community_server_id:
            # If specific community requested, verify membership first
            if not is_service_account(current_user):
                await verify_community_membership_by_uuid(
                    community_server_id, current_user, db, request
                )
            filters.append(Note.community_server_id == community_server_id)
        elif not is_service_account(current_user):
            # No specific community, filter to user's communities
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                filters.append(Note.community_server_id.in_(user_communities))
            else:
                # User is not a member of any community, return empty result
                return NoteListResponse(notes=[], total=0, page=page, size=size)

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        total_query = select(func.count(Note.id))
        if filters:
            total_query = total_query.where(and_(*filters))
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.order_by(desc(Note.created_at))
        query = query.limit(size).offset((page - 1) * size)

        # Execute query
        result = await db.execute(query)
        notes = result.scalars().all()

        # Build response with relationships loaded via selectinload
        note_responses = [NoteResponse.model_validate(note) for note in notes]

        return NoteListResponse(notes=note_responses, total=total, page=page, size=size)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list notes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list notes",
        )


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> NoteResponse:
    """Get a specific note by ID.

    Users can only view notes from communities they are members of.
    Service accounts can view all notes.
    """
    try:
        # Load note with ratings and request for detail view
        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note_id))
        note = result.scalar_one_or_none()

        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Note {note_id} not found",
            )

        # Verify community membership (service accounts bypass)
        if not is_service_account(current_user) and note.community_server_id:
            await verify_community_membership_by_uuid(
                note.community_server_id, current_user, db, request
            )

        return NoteResponse.model_validate(note)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get note: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get note",
        )


@router.patch("/notes/{note_id}", response_model=NoteResponse, deprecated=True)
async def update_note(
    note_id: UUID,
    note_update: NoteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    note: Annotated[Note, Depends(verify_note_ownership)],
) -> NoteResponse:
    """Update a note.

    Deprecated: Use JSON:API endpoint PATCH /jsonapi/notes/{note_id} instead.

    Users can only update notes they authored or if they are a community admin.
    Service accounts can update any note.
    """
    try:
        update_data = note_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(note, field, value)

        await db.commit()

        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note.id))
        note = result.scalar_one()

        logger.info(f"Updated note {note_id} by user {current_user.id}")

        return NoteResponse.model_validate(note)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update note: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update note",
        )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    note: Annotated[Note, Depends(verify_note_ownership)],
) -> None:
    """Delete a note.

    Users can only delete notes they authored or if they are a community admin.
    Service accounts can delete any note.
    """
    try:
        await db.delete(note)
        await db.commit()

        logger.info(f"Deleted note {note_id} by user {current_user.id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete note: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete note",
        )


@router.post("/notes/{note_id}/force-publish", response_model=NoteResponse)
async def force_publish_note(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> NoteResponse:
    """
    Force-publish a note (admin only).

    This endpoint allows administrators to manually publish notes that haven't met
    automatic publication thresholds. The note is marked with force_published flags
    for transparency, and the action is logged with admin user ID and timestamp.

    Requires admin authentication (service accounts, Open Notes admins, or community admins).
    """
    try:
        # Load note with community_server_id
        result = await db.execute(select(Note).where(Note.id == note_id))
        note = result.scalar_one_or_none()

        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Note {note_id} not found",
            )

        if not note.community_server_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Note {note_id} has no associated community server",
            )

        # Verify admin permissions for the community
        await verify_community_admin_by_uuid(note.community_server_id, current_user, db, request)

        # Get admin's profile ID for force_published_by field
        admin_profile_id = await _get_profile_id_from_user(db, current_user)
        if not admin_profile_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to determine admin profile ID",
            )

        # Mark note as force-published
        note.force_published = True
        note.force_published_by = admin_profile_id
        note.force_published_at = datetime.now(UTC).replace(tzinfo=None)
        note.status = "CURRENTLY_RATED_HELPFUL"

        # Update associated request status to completed (atomic with note update)
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

        # Reload with all relationships for response
        result = await db.execute(select(Note).options(*loaders.admin()).where(Note.id == note.id))
        note = result.scalar_one()

        logger.info(
            f"Force-published note {note_id} by admin {current_user.id} (profile {admin_profile_id})",
            extra={
                "note_id": note_id,
                "admin_user_id": current_user.id,
                "admin_profile_id": str(admin_profile_id),
                "community_server_id": str(note.community_server_id),
                "force_published_at": note.force_published_at.isoformat()
                if note.force_published_at
                else None,
            },
        )

        # Publish score update event to trigger Discord posting
        # Get original message info from Request → MessageArchive
        # IMPORTANT: Always use the original request's channel, not note.channel_id
        # which might be set to a different channel (e.g., where force-publish was executed)
        original_message_id = None
        channel_id = None
        if note.request and note.request.message_archive:
            original_message_id = note.request.message_archive.platform_message_id
            channel_id = note.request.message_archive.platform_channel_id

        # Fall back to note.channel_id only if message archive doesn't exist
        if not channel_id:
            channel_id = note.channel_id

        logger.info(
            f"Preparing to publish score update event for force-published note {note_id}",
            extra={
                "note_id": note_id,
                "original_message_id": original_message_id,
                "channel_id": channel_id,
                "community_server_id": str(note.community_server_id)
                if note.community_server_id
                else None,
                "has_request": note.request is not None,
                "has_message_archive": note.request.message_archive is not None
                if note.request
                else False,
            },
        )

        # Build force-publish metadata
        force_publish_metadata = {
            "force_published": True,
            "force_published_by": str(admin_profile_id),
            "force_published_at": note.force_published_at.isoformat()
            if note.force_published_at
            else None,
        }

        # Get admin display name for display
        if note.force_published_by_profile:
            force_publish_metadata["admin_username"] = note.force_published_by_profile.display_name

        try:
            # For force-published notes, use admin-override scoring values
            # since we're bypassing normal scoring thresholds
            await event_publisher.publish_note_score_updated(
                note_id=note.id,
                score=1.0,  # Admin-approved, max score
                confidence="standard",  # Admin certainty
                algorithm="admin_override",
                rating_count=len(note.ratings) if note.ratings else 0,
                tier=3,  # Highest tier
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
            # Don't fail the request if event publishing fails
            logger.error(
                f"Failed to publish score update event for note {note_id}: {e}", exc_info=True
            )

        return NoteResponse.model_validate(note)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to force-publish note: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to force-publish note",
        )
