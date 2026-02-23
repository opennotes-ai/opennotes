"""JSON:API v2 stats router.

This module implements JSON:API 1.1 compliant endpoints for statistics:
- GET /api/v2/stats/notes - Aggregated note statistics
- GET /api/v2/stats/author/{author_id} - Author statistics (user profile UUID)

Supports filtering:
- filter[community_server_id]: Filter by community server UUID
- filter[date_from]: Filter notes created on or after this datetime
- filter[date_to]: Filter notes created on or before this datetime

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_user_community_ids,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.common.base_schemas import SQLAlchemySchema
from src.common.filters import FilterBuilder, FilterField, FilterOperator
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.monitoring import get_logger
from src.notes.models import Note, Rating
from src.notes.schemas import NoteStatus
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(responses=AUTHENTICATED_RESPONSES)

notes_stats_filter_builder = FilterBuilder(
    FilterField(Note.created_at, operators=[FilterOperator.GTE, FilterOperator.LTE]),
).add_auth_gated_filter(
    FilterField(
        Note.community_server_id,
        alias="community_server_id",
        operators=[FilterOperator.EQ, FilterOperator.IN],
    ),
)

author_stats_filter_builder = FilterBuilder().add_auth_gated_filter(
    FilterField(
        Note.community_server_id,
        alias="community_server_id",
        operators=[FilterOperator.EQ, FilterOperator.IN],
    ),
)


class NoteStatsAttributes(SQLAlchemySchema):
    """Attributes for note statistics resource."""

    total_notes: int
    helpful_notes: int
    not_helpful_notes: int
    pending_notes: int
    average_helpfulness_score: float


class NoteStatsResource(BaseModel):
    """JSON:API resource object for note statistics."""

    type: str = "note-stats"
    id: str = "aggregate"
    attributes: NoteStatsAttributes


class NoteStatsSingleResponse(SQLAlchemySchema):
    """JSON:API response for note statistics."""

    data: NoteStatsResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class ParticipantStatsAttributes(SQLAlchemySchema):
    """Attributes for participant statistics resource."""

    notes_created: int
    ratings_given: int
    average_helpfulness_received: float
    top_classification: str | None = None


class ParticipantStatsResource(BaseModel):
    """JSON:API resource object for participant statistics."""

    type: str = "participant-stats"
    id: str
    attributes: ParticipantStatsAttributes


class ParticipantStatsSingleResponse(SQLAlchemySchema):
    """JSON:API response for participant statistics."""

    data: ParticipantStatsResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


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


@router.get("/stats/notes", response_class=JSONResponse, response_model=NoteStatsSingleResponse)
async def get_notes_stats_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    filter_date_from: datetime | None = Query(None, alias="filter[date_from]"),
    filter_date_to: datetime | None = Query(None, alias="filter[date_to]"),
    filter_community_server_id: UUID | None = Query(None, alias="filter[community_server_id]"),
) -> JSONResponse:
    """Get aggregated note statistics in JSON:API format.

    Returns statistics about notes including total count, helpful/not helpful counts,
    pending count, and average helpfulness score.

    Query Parameters:
    - filter[date_from]: Notes created on or after this datetime
    - filter[date_to]: Notes created on or before this datetime
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.
    """
    try:
        community_server_id_value = filter_community_server_id
        community_server_id_in_value = None
        if filter_community_server_id:
            pass
        elif not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                community_server_id_value = None
                community_server_id_in_value = user_communities
            else:
                response = NoteStatsSingleResponse(
                    data=NoteStatsResource(
                        attributes=NoteStatsAttributes(
                            total_notes=0,
                            helpful_notes=0,
                            not_helpful_notes=0,
                            pending_notes=0,
                            average_helpfulness_score=0.0,
                        )
                    ),
                    links=JSONAPILinks(self_=str(request.url)),
                )
                return JSONResponse(
                    content=response.model_dump(by_alias=True, mode="json"),
                    media_type=JSONAPI_CONTENT_TYPE,
                )

        filters = await notes_stats_filter_builder.build_async(
            auth_checks={
                "community_server_id": lambda csid: verify_community_membership_by_uuid(
                    csid, current_user, db, request
                ),
            }
            if not is_service_account(current_user)
            else None,
            community_server_id=community_server_id_value,
            community_server_id__in=community_server_id_in_value,
            created_at__gte=filter_date_from,
            created_at__lte=filter_date_to,
        )

        filters.append(Note.deleted_at.is_(None))
        base_where = and_(*filters)

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

        response = NoteStatsSingleResponse(
            data=NoteStatsResource(
                attributes=NoteStatsAttributes(
                    total_notes=total_notes,
                    helpful_notes=helpful_notes,
                    not_helpful_notes=not_helpful_notes,
                    pending_notes=pending_notes,
                    average_helpfulness_score=float(avg_score),
                )
            ),
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get note stats (JSON:API): {e}")
        return create_error_response(
            500,
            "Internal Server Error",
            "Failed to get note statistics",
        )


@router.get(
    "/stats/author/{author_id}",
    response_class=JSONResponse,
    response_model=ParticipantStatsSingleResponse,
)
async def get_author_stats_jsonapi(
    author_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    filter_community_server_id: UUID | None = Query(None, alias="filter[community_server_id]"),
) -> JSONResponse:
    """Get statistics for a specific author in JSON:API format.

    Returns statistics about an author including notes created, ratings given,
    average helpfulness received, and top classification.

    Path Parameters:
    - author_id: The author's user profile UUID

    Query Parameters:
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.
    """
    try:
        community_server_id_value = filter_community_server_id
        community_server_id_in_value = None
        if filter_community_server_id:
            pass
        elif not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)
            if user_communities:
                community_server_id_value = None
                community_server_id_in_value = user_communities
            else:
                response = ParticipantStatsSingleResponse(
                    data=ParticipantStatsResource(
                        id=str(author_id),
                        attributes=ParticipantStatsAttributes(
                            notes_created=0,
                            ratings_given=0,
                            average_helpfulness_received=0.0,
                            top_classification=None,
                        ),
                    ),
                    links=JSONAPILinks(self_=str(request.url)),
                )
                return JSONResponse(
                    content=response.model_dump(by_alias=True, mode="json"),
                    media_type=JSONAPI_CONTENT_TYPE,
                )

        community_filters = await author_stats_filter_builder.build_async(
            auth_checks={
                "community_server_id": lambda csid: verify_community_membership_by_uuid(
                    csid, current_user, db, request
                ),
            }
            if not is_service_account(current_user)
            else None,
            community_server_id=community_server_id_value,
            community_server_id__in=community_server_id_in_value,
        )

        note_filters: list[Any] = [Note.author_id == author_id, Note.deleted_at.is_(None)]
        note_filters.extend(community_filters)
        notes_where = and_(*note_filters)

        notes_result = await db.execute(select(func.count(Note.id)).where(notes_where))
        notes_created = notes_result.scalar() or 0

        ratings_query = (
            select(func.count(Rating.id))
            .select_from(Rating)
            .join(Note, Rating.note_id == Note.id)
            .where(Rating.rater_id == author_id, Note.deleted_at.is_(None))
        )
        if community_filters:
            ratings_query = ratings_query.where(and_(*community_filters))
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

        response = ParticipantStatsSingleResponse(
            data=ParticipantStatsResource(
                id=str(author_id),
                attributes=ParticipantStatsAttributes(
                    notes_created=notes_created,
                    ratings_given=ratings_given,
                    average_helpfulness_received=float(avg_helpfulness),
                    top_classification=top_classification,
                ),
            ),
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get participant stats (JSON:API): {e}")
        return create_error_response(
            500,
            "Internal Server Error",
            "Failed to get participant statistics",
        )
