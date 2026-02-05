"""
FastAPI dependency injection for resource ownership verification.

This module provides dependencies for endpoints that modify or delete resources
(Notes, Ratings, Requests). It verifies that the current user either:
1. Owns the resource (is the author/creator)
2. Is an admin/moderator of the resource's community

These dependencies should be used for PUT/PATCH/DELETE operations on resources.

Usage:
    @router.patch("/notes/{note_id}")
    async def update_note(
        note_id: UUID,
        note: Note = Depends(verify_note_ownership),
    ):
        # note is guaranteed to be owned by current user or user is admin
        ...
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_profile_id_from_user,
    verify_community_admin_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.database import get_db
from src.notes import loaders as note_loaders
from src.notes.models import Note, Rating
from src.notes.models import Request as NoteRequest
from src.users.models import User


def _is_owner_by_profile(resource_profile_id: UUID | None, user_profile_id: UUID | None) -> bool:
    """Check if user owns resource via profile_id match."""
    if resource_profile_id is None or user_profile_id is None:
        return False
    return resource_profile_id == user_profile_id


def _is_owner_by_participant(
    resource_participant_id: str | None, user_discord_id: str | None
) -> bool:
    """Check if user owns resource via legacy participant_id match (Discord ID)."""
    if resource_participant_id is None or user_discord_id is None:
        return False
    return resource_participant_id == user_discord_id


async def verify_note_ownership(
    note_id: UUID,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Note:
    """
    Verify that the current user owns the specified note or is a community admin.

    This dependency fetches the note and verifies ownership by checking:
    1. Service accounts - always granted access
    2. Profile-based ownership (author_id matches user's profile)
    3. Community admin access (user is admin/moderator of note's community)

    Args:
        note_id: UUID of the note to verify ownership for
        current_user: Current authenticated user
        db: Database session
        request: HTTP request (for Discord permission headers)

    Returns:
        Note: The note instance if user is authorized

    Raises:
        HTTPException: 404 if note not found, 403 if user is not authorized
    """
    result = await db.execute(select(Note).options(*note_loaders.full()).where(Note.id == note_id))
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note {note_id} not found",
        )

    # Service accounts always have access
    if is_service_account(current_user):
        return note

    # Get user's profile ID for ownership check
    user_profile_id = await get_profile_id_from_user(db, current_user)

    # Check ownership via author_id (profile-based)
    if _is_owner_by_profile(note.author_id, user_profile_id):
        return note

    # Check if user is community admin (allows admin override)
    try:
        await verify_community_admin_by_uuid(
            community_server_id=note.community_server_id,
            current_user=current_user,
            db=db,
            request=request,
        )
        return note
    except HTTPException:
        pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to modify this note. Only the author or community admins can modify it.",
    )


async def verify_rating_ownership(
    rating_id: UUID,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Rating:
    """
    Verify that the current user owns the specified rating or is a community admin.

    This dependency fetches the rating and verifies ownership by checking:
    1. Service accounts - always granted access
    2. Profile-based ownership (rater_id matches user's profile)
    3. Community admin access (user is admin/moderator of the rating's note's community)

    Args:
        rating_id: UUID of the rating to verify ownership for
        current_user: Current authenticated user
        db: Database session
        request: HTTP request (for Discord permission headers)

    Returns:
        Rating: The rating instance if user is authorized

    Raises:
        HTTPException: 404 if rating not found, 403 if user is not authorized
    """
    result = await db.execute(
        select(Rating).options(*note_loaders.rating_with_note()).where(Rating.id == rating_id)
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rating {rating_id} not found",
        )

    # Service accounts always have access
    if is_service_account(current_user):
        return rating

    # Get user's profile ID for ownership check
    user_profile_id = await get_profile_id_from_user(db, current_user)

    # Check ownership via rater_id
    if _is_owner_by_profile(rating.rater_id, user_profile_id):
        return rating

    # Check if user is community admin (allows admin override)
    # Rating's community is determined by its associated note
    try:
        await verify_community_admin_by_uuid(
            community_server_id=rating.note.community_server_id,
            current_user=current_user,
            db=db,
            request=request,
        )
        return rating
    except HTTPException:
        pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to modify this rating. Only the rater or community admins can modify it.",
    )


async def verify_request_ownership(
    request_id: str,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> NoteRequest:
    """
    Verify that the current user owns the specified note request or is a community admin.

    This dependency fetches the request and verifies ownership by checking:
    1. Service accounts - always granted access
    2. Legacy ownership (requested_by matches user's Discord ID)
    3. Community admin access (user is admin/moderator of the request's community)

    Note: Request model only has legacy `requested_by` field (no profile_id).

    Args:
        request_id: String request_id of the request to verify ownership for
        current_user: Current authenticated user
        db: Database session
        request: HTTP request (for Discord permission headers)

    Returns:
        NoteRequest: The request instance if user is authorized

    Raises:
        HTTPException: 404 if request not found, 403 if user is not authorized
    """
    result = await db.execute(
        select(NoteRequest)
        .options(*note_loaders.request_with_archive())
        .where(NoteRequest.request_id == request_id)
    )
    note_request = result.scalar_one_or_none()

    if not note_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )

    # Service accounts always have access
    if is_service_account(current_user):
        return note_request

    # Check ownership via requested_by (legacy - Discord ID)
    # Request model only has legacy field, no profile_id
    if _is_owner_by_participant(note_request.requested_by, current_user.discord_id):
        return note_request

    # Check if user is community admin (allows admin override)
    if note_request.community_server_id:
        try:
            await verify_community_admin_by_uuid(
                community_server_id=note_request.community_server_id,
                current_user=current_user,
                db=db,
                request=request,
            )
            return note_request
        except HTTPException:
            pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to modify this request. Only the requester or community admins can modify it.",
    )
