from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request as HTTPRequest
from sqlalchemy import and_, desc, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_user_community_ids,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.database import get_db
from src.monitoring import get_logger
from src.notes.models import Note, Rating
from src.notes.schemas import NoteStatus, NoteSummaryStats, ParticipantStats
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


@router.get("/stats/notes", response_model=NoteSummaryStats)
async def get_notes_stats(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    community_server_id: UUID | None = None,
) -> NoteSummaryStats:
    """Get aggregated note statistics.

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.
    """
    try:
        base_filters: list = []

        if date_from:
            base_filters.append(Note.created_at >= date_from)
        if date_to:
            base_filters.append(Note.created_at <= date_to)

        if community_server_id:
            if not is_service_account(current_user):
                await verify_community_membership_by_uuid(
                    community_server_id, current_user, db, request
                )
            base_filters.append(Note.community_server_id == community_server_id)
        elif not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                base_filters.append(Note.community_server_id.in_(user_communities))
            else:
                return NoteSummaryStats(
                    total_notes=0,
                    helpful_notes=0,
                    not_helpful_notes=0,
                    pending_notes=0,
                    average_helpfulness_score=0.0,
                )

        base_where = and_(*base_filters) if base_filters else true()

        total_result = await db.execute(select(func.count(Note.id)).where(base_where))
        total_notes = total_result.scalar() or 0

        helpful_result = await db.execute(
            select(func.count(Note.id)).where(
                and_(base_where, Note.status == NoteStatus.CURRENTLY_RATED_HELPFUL)
            )
        )
        helpful_notes = helpful_result.scalar() or 0

        not_helpful_result = await db.execute(
            select(func.count(Note.id)).where(
                and_(base_where, Note.status == NoteStatus.CURRENTLY_RATED_NOT_HELPFUL)
            )
        )
        not_helpful_notes = not_helpful_result.scalar() or 0

        pending_result = await db.execute(
            select(func.count(Note.id)).where(
                and_(base_where, Note.status == NoteStatus.NEEDS_MORE_RATINGS)
            )
        )
        pending_notes = pending_result.scalar() or 0

        avg_result = await db.execute(select(func.avg(Note.helpfulness_score)).where(base_where))
        avg_score = avg_result.scalar() or 0.0

        return NoteSummaryStats(
            total_notes=total_notes,
            helpful_notes=helpful_notes,
            not_helpful_notes=not_helpful_notes,
            pending_notes=pending_notes,
            average_helpfulness_score=float(avg_score),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get note stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get note statistics",
        )


@router.get("/stats/participant/{participant_id}", response_model=ParticipantStats)
async def get_participant_stats(
    participant_id: str,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    community_server_id: UUID | None = None,
) -> ParticipantStats:
    """Get statistics for a specific participant.

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.
    """
    try:
        note_filters: list = [Note.author_participant_id == participant_id]
        community_filter = None

        if community_server_id:
            if not is_service_account(current_user):
                await verify_community_membership_by_uuid(
                    community_server_id, current_user, db, request
                )
            community_filter = Note.community_server_id == community_server_id
        elif not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                community_filter = Note.community_server_id.in_(user_communities)
            else:
                return ParticipantStats(
                    participant_id=participant_id,
                    notes_created=0,
                    ratings_given=0,
                    average_helpfulness_received=0.0,
                    top_classification=None,
                )

        if community_filter is not None:
            note_filters.append(community_filter)

        notes_where = and_(*note_filters)

        notes_result = await db.execute(select(func.count(Note.id)).where(notes_where))
        notes_created = notes_result.scalar() or 0

        ratings_query = (
            select(func.count(Rating.id))
            .select_from(Rating)
            .join(Note, Rating.note_id == Note.id)
            .where(Rating.rater_participant_id == participant_id)
        )
        if community_filter is not None:
            ratings_query = ratings_query.where(community_filter)
        ratings_result = await db.execute(ratings_query)
        ratings_given = ratings_result.scalar() or 0

        avg_help_result = await db.execute(
            select(func.avg(Note.helpfulness_score)).where(notes_where)
        )
        avg_helpfulness = avg_help_result.scalar() or 0.0

        classification_result = await db.execute(
            select(Note.classification, func.count(Note.classification))
            .where(notes_where)
            .group_by(Note.classification)
            .order_by(desc(func.count(Note.classification)))
            .limit(1)
        )
        top_classification_row = classification_result.first()
        top_classification = top_classification_row[0] if top_classification_row else None

        return ParticipantStats(
            participant_id=participant_id,
            notes_created=notes_created,
            ratings_given=ratings_given,
            average_helpfulness_received=float(avg_helpfulness),
            top_classification=top_classification,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get participant stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get participant statistics",
        )
