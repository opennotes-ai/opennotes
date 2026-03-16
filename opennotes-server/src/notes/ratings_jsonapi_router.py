"""JSON:API v2 ratings router.

This module implements JSON:API 1.0 compliant endpoints for ratings.
It provides:
- POST /ratings: Create or upsert a rating
- GET /notes/{id}/ratings: List ratings for a note
- Standard JSON:API response envelope structure
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_membership_by_uuid
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.ownership_dependencies import verify_rating_ownership
from src.auth.permissions import is_service_account
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
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
from src.notes import loaders
from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel
from src.simulation.workflows.scoring_workflow import dispatch_community_scoring
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(responses=AUTHENTICATED_RESPONSES)


class RatingCreateAttributes(StrictInputSchema):
    """Attributes for creating a rating via JSON:API."""

    note_id: UUID = Field(..., description="Note ID to rate")
    rater_id: UUID = Field(..., description="Rater's user profile ID")
    helpfulness_level: HelpfulnessLevel = Field(..., description="Rating level")


class RatingCreateData(BaseModel):
    """JSON:API data object for rating creation."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ratings"] = Field(..., description="Resource type must be 'ratings'")
    attributes: RatingCreateAttributes


class RatingCreateRequest(BaseModel):
    """JSON:API request body for creating a rating."""

    model_config = ConfigDict(extra="forbid")

    data: RatingCreateData


class RatingAttributes(SQLAlchemySchema):
    """Rating attributes for JSON:API resource."""

    note_id: str
    rater_id: str
    helpfulness_level: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RatingResource(BaseModel):
    """JSON:API resource object for a rating."""

    type: str = "ratings"
    id: str
    attributes: RatingAttributes


class RatingSingleResponse(SQLAlchemySchema):
    """JSON:API response for a single rating resource."""

    data: RatingResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class RatingListResponse(SQLAlchemySchema):
    """JSON:API response for a list of rating resources."""

    data: list[RatingResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class RatingUpdateAttributes(StrictInputSchema):
    """Attributes for updating a rating via JSON:API."""

    helpfulness_level: HelpfulnessLevel = Field(..., description="Rating level")


class RatingUpdateData(BaseModel):
    """JSON:API data object for rating update."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ratings"] = Field(..., description="Resource type must be 'ratings'")
    id: str = Field(..., description="Rating ID")
    attributes: RatingUpdateAttributes


class RatingUpdateRequest(BaseModel):
    """JSON:API request body for updating a rating."""

    model_config = ConfigDict(extra="forbid")

    data: RatingUpdateData


class RatingStatsAttributes(BaseModel):
    """Attributes for rating statistics."""

    total: int = Field(..., description="Total number of ratings")
    helpful: int = Field(..., description="Number of HELPFUL ratings")
    somewhat_helpful: int = Field(..., description="Number of SOMEWHAT_HELPFUL ratings")
    not_helpful: int = Field(..., description="Number of NOT_HELPFUL ratings")
    average_score: float = Field(..., description="Average score (1-3 scale)")


class RatingStatsResource(BaseModel):
    """JSON:API resource object for rating statistics."""

    type: str = "rating-stats"
    id: str
    attributes: RatingStatsAttributes


class RatingStatsSingleResponse(SQLAlchemySchema):
    """JSON:API response for rating statistics."""

    data: RatingStatsResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def rating_to_resource(rating: Rating) -> RatingResource:
    """Convert a Rating model to a JSON:API resource object."""
    return RatingResource(
        type="ratings",
        id=str(rating.id),
        attributes=RatingAttributes(
            note_id=str(rating.note_id),
            rater_id=str(rating.rater_id),
            helpfulness_level=rating.helpfulness_level,
            created_at=rating.created_at,
            updated_at=rating.updated_at,
        ),
    )


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


@router.post(
    "/ratings",
    response_class=JSONResponse,
    status_code=status.HTTP_201_CREATED,
    response_model=RatingSingleResponse,
)
async def create_rating_jsonapi(
    request: HTTPRequest,
    body: RatingCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Create or upsert a rating with JSON:API format.

    JSON:API 1.0 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status for new rating
    - Response body with 'data' object containing created/updated resource

    If a rating already exists for the same note + rater, it will be updated (upsert).
    """
    try:
        attrs = body.data.attributes

        note_result = await db.execute(
            select(Note)
            .options(*loaders.full())
            .where(Note.id == attrs.note_id, Note.deleted_at.is_(None))
        )
        note = note_result.scalar_one_or_none()
        if not note:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note {attrs.note_id} not found",
            )

        rating_dict = attrs.model_dump(mode="python")

        stmt = (
            insert(Rating)
            .values(**rating_dict)
            .on_conflict_do_update(
                index_elements=["note_id", "rater_id"],
                set_={
                    "helpfulness_level": rating_dict["helpfulness_level"],
                    "updated_at": func.now(),
                },
            )
            .returning(Rating)
        )

        result = await db.execute(stmt)
        await db.flush()
        rating = result.scalar_one()

        await db.refresh(note, ["ratings"])

        await db.commit()
        await db.refresh(rating)

        current_score = (note.helpfulness_score or 0) / 100.0
        rating_count = len(note.ratings)

        scoring_requested = False
        if note.community_server_id:
            try:
                await dispatch_community_scoring(note.community_server_id)
                scoring_requested = True
            except Exception as e:
                logger.warning(
                    "Failed to dispatch DBOS rescore workflow",
                    extra={
                        "note_id": str(attrs.note_id),
                        "error": str(e),
                    },
                )
        else:
            logger.warning(
                "Skipping scoring dispatch: note has no community_server_id",
                extra={
                    "note_id": str(attrs.note_id),
                },
            )

        logger.info(
            "Created/updated rating via JSON:API",
            extra={
                "note_id": str(attrs.note_id),
                "user_id": str(current_user.id),
                "current_score": current_score,
                "rating_count": rating_count,
                "scoring_requested": scoring_requested,
            },
        )

        rating_resource = rating_to_resource(rating)
        response = RatingSingleResponse(
            data=rating_resource,
            links=JSONAPILinks(self_=f"{str(request.url).rstrip('/')}/{rating.id}"),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create rating (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create rating",
        )


@router.get(
    "/notes/{note_id}/ratings", response_class=JSONResponse, response_model=RatingListResponse
)
async def list_note_ratings_jsonapi(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """List all ratings for a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 200 OK status
    - 'data' array containing rating resource objects
    - Each resource has 'type', 'id', and 'attributes'

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        note_result = await db.execute(
            select(Note).where(Note.id == note_id, Note.deleted_at.is_(None))
        )
        note = note_result.scalar_one_or_none()

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

        result = await db.execute(
            select(Rating).where(Rating.note_id == note_id).order_by(desc(Rating.created_at))
        )
        ratings = result.scalars().all()

        rating_resources = [rating_to_resource(rating) for rating in ratings]

        response = RatingListResponse(
            data=rating_resources,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list ratings (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list ratings",
        )


@router.put(
    "/ratings/{rating_id}", response_class=JSONResponse, response_model=RatingSingleResponse
)
async def update_rating_jsonapi(
    rating_id: UUID,
    request: HTTPRequest,
    body: RatingUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Update an existing rating with JSON:API format.

    JSON:API 1.0 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - Response with 200 OK status for updated resource
    - Response body with 'data' object containing updated resource

    Users can only update ratings they submitted or if they are a community admin.
    Service accounts can update any rating.
    """
    try:
        rating = await verify_rating_ownership(rating_id, current_user, db, request)
    except HTTPException as e:
        return create_error_response(
            e.status_code,
            "Not Found" if e.status_code == 404 else "Forbidden",
            e.detail,
        )

    try:
        attrs = body.data.attributes

        rating.helpfulness_level = attrs.helpfulness_level
        await db.commit()
        await db.refresh(rating)

        note_result = await db.execute(select(Note).where(Note.id == rating.note_id))
        note = note_result.scalar_one_or_none()

        scoring_requested = False
        if note and note.community_server_id:
            try:
                await dispatch_community_scoring(note.community_server_id)
                scoring_requested = True
            except Exception as e:
                logger.warning(
                    "Failed to dispatch DBOS rescore workflow after rating update",
                    extra={
                        "rating_id": str(rating_id),
                        "note_id": str(rating.note_id),
                        "error": str(e),
                    },
                )
        elif note:
            logger.warning(
                "Skipping scoring dispatch: note has no community_server_id",
                extra={
                    "note_id": str(note.id),
                    "rating_id": str(rating_id),
                },
            )

        logger.info(
            "Updated rating via JSON:API",
            extra={
                "rating_id": str(rating_id),
                "user_id": str(current_user.id),
                "new_helpfulness_level": attrs.helpfulness_level,
                "scoring_requested": scoring_requested,
            },
        )

        rating_resource = rating_to_resource(rating)
        response = RatingSingleResponse(
            data=rating_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update rating (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update rating",
        )


@router.get(
    "/notes/{note_id}/ratings/stats",
    response_class=JSONResponse,
    response_model=RatingStatsSingleResponse,
)
async def get_rating_stats_jsonapi(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get rating statistics for a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 200 OK status
    - 'data' object containing singleton/aggregate resource
    - Resource has 'type', 'id', and 'attributes'

    Users can only view rating stats for notes in communities they are members of.
    Service accounts can view all rating stats.
    """
    try:
        note_result = await db.execute(
            select(Note).where(Note.id == note_id, Note.deleted_at.is_(None))
        )
        note = note_result.scalar_one_or_none()

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

        result = await db.execute(select(Rating).where(Rating.note_id == note_id))
        ratings = result.scalars().all()

        if not ratings:
            stats_attrs = RatingStatsAttributes(
                total=0,
                helpful=0,
                somewhat_helpful=0,
                not_helpful=0,
                average_score=0.0,
            )
        else:
            helpful = sum(1 for r in ratings if r.helpfulness_level == HelpfulnessLevel.HELPFUL)
            somewhat = sum(
                1 for r in ratings if r.helpfulness_level == HelpfulnessLevel.SOMEWHAT_HELPFUL
            )
            not_helpful = sum(
                1 for r in ratings if r.helpfulness_level == HelpfulnessLevel.NOT_HELPFUL
            )

            total_score = sum(
                HelpfulnessLevel(r.helpfulness_level).to_display_value() for r in ratings
            )
            average_score = total_score / len(ratings) if ratings else 0

            stats_attrs = RatingStatsAttributes(
                total=len(ratings),
                helpful=helpful,
                somewhat_helpful=somewhat,
                not_helpful=not_helpful,
                average_score=average_score,
            )

        stats_resource = RatingStatsResource(
            type="rating-stats",
            id=str(note_id),
            attributes=stats_attrs,
        )

        response = RatingStatsSingleResponse(
            data=stats_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get rating stats (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get rating statistics",
        )
