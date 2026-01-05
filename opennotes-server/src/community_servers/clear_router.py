"""
Bulk clear endpoints for community server admins.

This module provides endpoints for clearing stale data:
- Clear note requests (all or older than X days)
- Clear unpublished notes (all or older than X days)

Reference: task-952
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin_by_uuid
from src.auth.dependencies import get_current_user_or_api_key
from src.database import get_db
from src.notes.models import Note
from src.notes.models import Request as NoteRequest
from src.users.models import User
from src.users.profile_models import CommunityMember

router = APIRouter(prefix="/community-servers", tags=["community-clear"])
logger = logging.getLogger(__name__)


class ClearResponse(BaseModel):
    """Response for clear operations."""

    deleted_count: int
    message: str


class ClearPreviewResponse(BaseModel):
    """Response for clear preview (dry run) operations."""

    would_delete_count: int
    message: str


def parse_mode(mode: str) -> tuple[Literal["all", "days"], int | None]:
    """
    Parse the mode parameter.

    Args:
        mode: Either "all" or a number of days (e.g., "30")

    Returns:
        Tuple of (mode_type, days) where days is None for "all"

    Raises:
        HTTPException: If mode is invalid
    """
    if mode.lower() == "all":
        return ("all", None)

    try:
        days = int(mode)
        if days <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Days must be a positive integer",
            )
        return ("days", days)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mode must be 'all' or a positive integer (number of days)",
        )


@router.delete("/{community_server_id}/clear-requests", response_model=ClearResponse)
async def clear_requests(
    community_server_id: UUID,
    mode: Annotated[str, Query(description="'all' or number of days (e.g., '30')")],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
    membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> ClearResponse:
    """
    Clear note requests for a community server.

    Deletes requests based on the mode:
    - "all": Delete all requests
    - "<days>": Delete requests older than specified days

    Requires admin privileges for the community server.

    Args:
        community_server_id: Community server UUID
        mode: Either "all" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearResponse with deleted count and message
    """
    mode_type, days = parse_mode(mode)

    # Build base condition
    conditions = [NoteRequest.community_server_id == community_server_id]

    # Add time condition if mode is days
    if mode_type == "days" and days is not None:
        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        conditions.append(NoteRequest.requested_at < cutoff_date)

    # Delete matching requests
    stmt = delete(NoteRequest).where(and_(*conditions)).returning(NoteRequest.id)
    result = await db.execute(stmt)
    deleted_ids = result.scalars().all()
    deleted_count = len(deleted_ids)

    await db.commit()

    logger.info(
        f"User {current_user.id} cleared {deleted_count} requests "
        f"from community {community_server_id} (mode={mode})"
    )

    if mode_type == "all":
        message = f"Deleted all {deleted_count} requests"
    else:
        message = f"Deleted {deleted_count} requests older than {days} days"

    return ClearResponse(deleted_count=deleted_count, message=message)


@router.get("/{community_server_id}/clear-requests/preview", response_model=ClearPreviewResponse)
async def preview_clear_requests(
    community_server_id: UUID,
    mode: Annotated[str, Query(description="'all' or number of days (e.g., '30')")],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
    membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> ClearPreviewResponse:
    """
    Preview clear requests operation (dry run).

    Returns the count of requests that would be deleted without actually deleting them.

    Args:
        community_server_id: Community server UUID
        mode: Either "all" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearPreviewResponse with count of items that would be deleted
    """
    mode_type, days = parse_mode(mode)

    # Build base condition
    conditions = [NoteRequest.community_server_id == community_server_id]

    # Add time condition if mode is days
    if mode_type == "days" and days is not None:
        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        conditions.append(NoteRequest.requested_at < cutoff_date)

    # Count matching requests
    stmt = select(func.count()).select_from(NoteRequest).where(and_(*conditions))
    result = await db.execute(stmt)
    count = result.scalar() or 0

    if mode_type == "all":
        message = f"Would delete all {count} requests"
    else:
        message = f"Would delete {count} requests older than {days} days"

    return ClearPreviewResponse(would_delete_count=count, message=message)


@router.delete("/{community_server_id}/clear-notes", response_model=ClearResponse)
async def clear_notes(
    community_server_id: UUID,
    mode: Annotated[str, Query(description="'all' or number of days (e.g., '30')")],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
    membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> ClearResponse:
    """
    Clear unpublished notes for a community server.

    Only deletes notes that are:
    - Status is "NEEDS_MORE_RATINGS" (unpublished)
    - NOT force-published (force_published=False)

    Published notes (CURRENTLY_RATED_HELPFUL, CURRENTLY_RATED_NOT_HELPFUL)
    and force-published notes are preserved.

    Deletes based on the mode:
    - "all": Delete all unpublished notes
    - "<days>": Delete unpublished notes older than specified days

    Requires admin privileges for the community server.

    Args:
        community_server_id: Community server UUID
        mode: Either "all" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearResponse with deleted count and message
    """
    mode_type, days = parse_mode(mode)

    # Build conditions for unpublished notes only
    conditions = [
        Note.community_server_id == community_server_id,
        Note.status == "NEEDS_MORE_RATINGS",
        Note.force_published == False,
    ]

    # Add time condition if mode is days
    if mode_type == "days" and days is not None:
        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        conditions.append(Note.created_at < cutoff_date)

    # Delete matching notes
    stmt = delete(Note).where(and_(*conditions)).returning(Note.id)
    result = await db.execute(stmt)
    deleted_ids = result.scalars().all()
    deleted_count = len(deleted_ids)

    await db.commit()

    logger.info(
        f"User {current_user.id} cleared {deleted_count} unpublished notes "
        f"from community {community_server_id} (mode={mode})"
    )

    if mode_type == "all":
        message = f"Deleted all {deleted_count} unpublished notes"
    else:
        message = f"Deleted {deleted_count} unpublished notes older than {days} days"

    return ClearResponse(deleted_count=deleted_count, message=message)


@router.get("/{community_server_id}/clear-notes/preview", response_model=ClearPreviewResponse)
async def preview_clear_notes(
    community_server_id: UUID,
    mode: Annotated[str, Query(description="'all' or number of days (e.g., '30')")],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
    membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> ClearPreviewResponse:
    """
    Preview clear notes operation (dry run).

    Returns the count of unpublished notes that would be deleted without
    actually deleting them.

    Args:
        community_server_id: Community server UUID
        mode: Either "all" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearPreviewResponse with count of items that would be deleted
    """
    mode_type, days = parse_mode(mode)

    # Build conditions for unpublished notes only
    conditions = [
        Note.community_server_id == community_server_id,
        Note.status == "NEEDS_MORE_RATINGS",
        Note.force_published == False,
    ]

    # Add time condition if mode is days
    if mode_type == "days" and days is not None:
        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        conditions.append(Note.created_at < cutoff_date)

    # Count matching notes
    stmt = select(func.count()).select_from(Note).where(and_(*conditions))
    result = await db.execute(stmt)
    count = result.scalar() or 0

    if mode_type == "all":
        message = f"Would delete all {count} unpublished notes"
    else:
        message = f"Would delete {count} unpublished notes older than {days} days"

    return ClearPreviewResponse(would_delete_count=count, message=message)
