"""JSON:API v2 scoring router.

This module implements JSON:API 1.1 compliant endpoints for scoring operations.
It provides:
- GET /scoring/status - System scoring status (singleton resource)
- GET /scoring/notes/{note_id}/score - Get score for one note
- POST /scoring/notes/batch-scores - Get scores for multiple notes
- GET /scoring/notes/top - Get top-scored notes

Reference: https://jsonapi.org/format/
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_user_community_ids,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.common.base_schemas import StrictInputSchema
from src.common.filters import FilterBuilder, FilterField, FilterOperator
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.config import settings
from src.database import get_db
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.notes.loaders import full
from src.notes.models import Note
from src.notes.scoring import (
    ScorerFactory,
    get_tier_config,
    get_tier_for_note_count,
)
from src.notes.scoring_schemas import (
    DataConfidence,
    EnrollmentData,
    NextTierInfo,
    NoteData,
    PerformanceMetrics,
    RatingData,
    ScoreConfidence,
    TierInfo,
    TierThreshold,
)
from src.notes.scoring_utils import (
    TIER_ORDER,
    calculate_note_score,
    get_next_tier,
    get_tier_data_confidence,
    get_tier_level,
)
from src.users.models import User

if settings.TESTING:
    from src.scoring_adapter_mock import ScoringAdapter
else:
    try:
        from src.scoring_adapter import ScoringAdapter  # type: ignore[assignment]
    except ImportError:
        from src.scoring_adapter_mock import ScoringAdapter

scoring_adapter = ScoringAdapter()

logger = get_logger(__name__)

router = APIRouter()
scorer_factory = ScorerFactory()

top_notes_filter_builder = FilterBuilder().add_auth_gated_filter(
    FilterField(
        Note.community_server_id,
        alias="community_server_id",
        operators=[FilterOperator.EQ, FilterOperator.IN],
    ),
)


class BatchScoreRequestAttributes(StrictInputSchema):
    """Attributes for batch score request via JSON:API."""

    note_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of note IDs to retrieve scores for",
    )


class BatchScoreRequestData(BaseModel):
    """JSON:API data object for batch score request."""

    type: Literal["batch-score-requests"] = Field(
        ..., description="Resource type must be 'batch-score-requests'"
    )
    attributes: BatchScoreRequestAttributes


class BatchScoreRequest(BaseModel):
    """JSON:API request body for batch scores."""

    data: BatchScoreRequestData


class NoteScoreAttributes(BaseModel):
    """Attributes for note score resource."""

    model_config = ConfigDict(from_attributes=True)

    score: float = Field(..., description="Normalized score value (0.0-1.0)")
    confidence: str = Field(
        ...,
        description="Confidence level: no_data, provisional, or standard",
    )
    algorithm: str = Field(..., description="Scoring algorithm used")
    rating_count: int = Field(..., description="Number of ratings contributing to the score")
    tier: int = Field(..., description="Current scoring tier level (0-5)")
    tier_name: str = Field(..., description="Human-readable tier name")
    calculated_at: datetime | None = Field(None, description="Timestamp when score was calculated")
    content: str | None = Field(None, description="Message content from archive")


class NoteScoreResource(BaseModel):
    """JSON:API resource object for a note score."""

    type: str = "note-scores"
    id: str
    attributes: NoteScoreAttributes


class NoteScoreListResponse(BaseModel):
    """JSON:API response for a list of note score resources."""

    model_config = ConfigDict(from_attributes=True)

    data: list[NoteScoreResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: dict[str, Any] | None = None


class NoteScoreSingleResponse(BaseModel):
    """JSON:API response for a single note score resource."""

    model_config = ConfigDict(from_attributes=True)

    data: NoteScoreResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class ScoringStatusAttributes(BaseModel):
    """Attributes for scoring status resource."""

    model_config = ConfigDict(from_attributes=True)

    current_note_count: int = Field(..., description="Current total number of notes in the system")
    active_tier: TierInfo = Field(..., description="Currently active scoring tier")
    data_confidence: str = Field(..., description="Confidence level in scoring results")
    tier_thresholds: dict[str, TierThreshold] = Field(
        ..., description="Threshold information for all tiers"
    )
    next_tier_upgrade: NextTierInfo | None = Field(
        None, description="Information about the next tier upgrade"
    )
    performance_metrics: PerformanceMetrics = Field(
        ..., description="Performance metrics for the scoring system"
    )
    warnings: list[str] = Field(default_factory=list, description="Any warnings about data quality")
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Current scoring configuration"
    )


class ScoringStatusResource(BaseModel):
    """JSON:API resource object for scoring status."""

    type: str = "scoring-status"
    id: str = "current"
    attributes: ScoringStatusAttributes


class ScoringStatusJSONAPIResponse(BaseModel):
    """JSON:API response for scoring status."""

    model_config = ConfigDict(from_attributes=True)

    data: ScoringStatusResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class ScoringRunRequestAttributes(StrictInputSchema):
    """Attributes for scoring run request via JSON:API."""

    notes: list[NoteData] = Field(..., description="List of community notes to score")
    ratings: list[RatingData] = Field(..., description="List of ratings for the notes")
    enrollment: list[EnrollmentData] = Field(..., description="List of user enrollment data")
    status: list[dict[str, Any]] | None = Field(
        default=None, description="Optional note status history"
    )


class ScoringRunRequestData(BaseModel):
    """JSON:API data object for scoring run request."""

    type: Literal["scoring-requests"] = Field(
        ..., description="Resource type must be 'scoring-requests'"
    )
    attributes: ScoringRunRequestAttributes


class ScoringRunRequest(BaseModel):
    """JSON:API request body for scoring run."""

    data: ScoringRunRequestData


class ScoringResultAttributes(BaseModel):
    """Attributes for scoring result resource."""

    model_config = ConfigDict(from_attributes=True)

    scored_notes: list[dict[str, Any]] = Field(
        ..., description="Scored notes output from the algorithm"
    )
    helpful_scores: list[dict[str, Any]] = Field(..., description="Helpful scores for raters")
    auxiliary_info: list[dict[str, Any]] = Field(
        ..., description="Auxiliary information from scoring"
    )


class ScoringResultResource(BaseModel):
    """JSON:API resource object for scoring result."""

    type: str = "scoring-results"
    id: str = Field(..., description="Unique identifier for this scoring run")
    attributes: ScoringResultAttributes


class ScoringResultResponse(BaseModel):
    """JSON:API response for scoring result."""

    model_config = ConfigDict(from_attributes=True)

    data: ScoringResultResource
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


def note_score_to_resource(note_id: UUID, score_response: Any) -> NoteScoreResource:
    """Convert a NoteScoreResponse to a JSON:API resource object."""
    confidence_value = (
        score_response.confidence.value
        if hasattr(score_response.confidence, "value")
        else score_response.confidence
    )
    return NoteScoreResource(
        type="note-scores",
        id=str(note_id),
        attributes=NoteScoreAttributes(
            score=score_response.score,
            confidence=confidence_value,
            algorithm=score_response.algorithm,
            rating_count=score_response.rating_count,
            tier=score_response.tier,
            tier_name=score_response.tier_name,
            calculated_at=score_response.calculated_at,
            content=score_response.content,
        ),
    )


@router.get(
    "/scoring/status", response_class=JSONResponse, response_model=ScoringStatusJSONAPIResponse
)
async def get_scoring_status_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get system scoring status in JSON:API format.

    Returns a singleton resource with current scoring system status including:
    - Current note count
    - Active scoring tier
    - Data confidence level
    - Tier thresholds
    - Next tier upgrade information
    - Performance metrics
    - Warnings
    """
    try:
        result = await db.execute(select(func.count(Note.id)))
        note_count = result.scalar() or 0

        active_tier_enum = get_tier_for_note_count(note_count)
        active_tier_config = get_tier_config(active_tier_enum)
        next_tier_enum = get_next_tier(active_tier_enum)

        active_tier = TierInfo(
            level=get_tier_level(active_tier_enum),
            name=active_tier_enum.value.capitalize(),
            scorer_components=active_tier_config.scorers,
        )

        tier_thresholds = {}
        for tier_enum in TIER_ORDER:
            tier_config = get_tier_config(tier_enum)
            tier_thresholds[tier_enum.value] = TierThreshold(
                min=tier_config.min_notes,
                max=tier_config.max_notes,
                current=tier_enum == active_tier_enum,
            )

        next_tier_upgrade = None
        if next_tier_enum:
            next_tier_config = get_tier_config(next_tier_enum)
            notes_needed = next_tier_config.min_notes
            notes_to_upgrade = notes_needed - note_count
            next_tier_upgrade = NextTierInfo(
                tier=next_tier_enum.value.capitalize(),
                notes_needed=notes_needed,
                notes_to_upgrade=notes_to_upgrade,
            )

        performance_metrics = PerformanceMetrics(
            avg_scoring_time_ms=0.0,
            last_scoring_time_ms=None,
            scorer_success_rate=1.0,
            total_scoring_operations=0,
            failed_scoring_operations=0,
        )

        data_confidence = get_tier_data_confidence(active_tier_enum)
        warnings = []
        if data_confidence in (DataConfidence.NONE, DataConfidence.LOW):
            warnings.append(
                f"Limited data confidence: Only {note_count} notes available. "
                f"Scoring quality improves significantly with more data."
            )
        if note_count < 200:
            warnings.append(
                "Bootstrap phase: Using Bayesian Average scorer. "
                "Matrix factorization requires at least 200 notes for better accuracy."
            )

        logger.info(
            "Scoring status retrieved (JSON:API)",
            extra={
                "note_count": note_count,
                "active_tier": active_tier_enum.value,
                "confidence": data_confidence,
            },
        )

        status_attrs = ScoringStatusAttributes(
            current_note_count=note_count,
            active_tier=active_tier,
            data_confidence=data_confidence.value,
            tier_thresholds=tier_thresholds,
            next_tier_upgrade=next_tier_upgrade,
            performance_metrics=performance_metrics,
            warnings=warnings,
            configuration={},
        )

        response = ScoringStatusJSONAPIResponse(
            data=ScoringStatusResource(
                type="scoring-status",
                id="current",
                attributes=status_attrs,
            ),
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get scoring status (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to retrieve scoring status",
        )


@router.get(
    "/scoring/notes/{note_id}/score",
    response_class=JSONResponse,
    response_model=NoteScoreSingleResponse,
)
async def get_note_score_jsonapi(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get individual note score in JSON:API format.

    Users can only view scores for notes in communities they are members of.
    Service accounts can view all scores.

    Returns the calculated score for a specific note along with:
    - Algorithm used for scoring
    - Confidence level based on rating count
    - Current scoring tier information
    - Number of ratings
    - Timestamp of calculation
    """
    try:
        result = await db.execute(select(Note).options(*full()).where(Note.id == note_id))
        note = result.scalar_one_or_none()

        if not note:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Note with ID {note_id} not found",
            )

        if not is_service_account(current_user) and note.community_server_id:
            try:
                await verify_community_membership_by_uuid(
                    note.community_server_id, current_user, db, request
                )
            except HTTPException as e:
                return create_error_response(
                    e.status_code,
                    "Forbidden",
                    e.detail,
                )

        count_result = await db.execute(select(func.count(Note.id)))
        note_count = count_result.scalar() or 0

        community_id = str(note.community_server_id) if note.community_server_id else ""
        scorer = scorer_factory.get_scorer(community_id, note_count)
        score_response = await calculate_note_score(note, note_count, scorer)

        logger.info(
            f"Score retrieved for note {note_id} (JSON:API)",
            extra={
                "note_id": note_id,
                "score": score_response.score,
                "confidence": score_response.confidence,
                "rating_count": score_response.rating_count,
            },
        )

        note_resource = note_score_to_resource(note_id, score_response)

        response = NoteScoreSingleResponse(
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
        logger.exception(f"Failed to get score for note {note_id} (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to retrieve note score",
        )


@router.post(
    "/scoring/notes/batch-scores", response_class=JSONResponse, response_model=NoteScoreListResponse
)
@limiter.limit("10/minute;50/hour")
async def get_batch_scores_jsonapi(
    body: BatchScoreRequest,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Get scores for multiple notes in JSON:API format.

    JSON:API request body must contain:
    - data.type: "batch-score-requests"
    - data.attributes.note_ids: list of note UUIDs

    Users can only get scores for notes in communities they are members of.
    Notes from other communities will be treated as "not found" in the response.
    Service accounts can access all notes.

    Returns a list of note score resources with meta information about
    total requested vs found counts.
    """
    try:
        note_ids = body.data.attributes.note_ids

        if len(note_ids) > 100:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "Batch size exceeds maximum of 100 items",
            )

        logger.info(
            f"Batch score request (JSON:API) for {len(note_ids)} notes",
            extra={
                "note_count": len(note_ids),
                "note_ids": [str(nid) for nid in note_ids[:10]],
            },
        )

        user_communities: list[UUID] = []
        if not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)

        result = await db.execute(select(Note).options(*full()).where(Note.id.in_(note_ids)))
        notes = result.scalars().all()

        count_result = await db.execute(select(func.count(Note.id)))
        total_note_count = count_result.scalar() or 0

        score_resources: list[NoteScoreResource] = []
        found_note_ids: set[UUID] = set()

        for note in notes:
            if (
                not is_service_account(current_user)
                and note.community_server_id
                and note.community_server_id not in user_communities
            ):
                continue

            community_id = str(note.community_server_id) if note.community_server_id else ""
            scorer = scorer_factory.get_scorer(community_id, total_note_count)
            score_response = await calculate_note_score(note, total_note_count, scorer)
            score_resources.append(note_score_to_resource(note.id, score_response))
            found_note_ids.add(note.id)

        requested_note_ids = set(note_ids)
        not_found = [str(nid) for nid in (requested_note_ids - found_note_ids)]

        logger.info(
            "Batch score request completed (JSON:API)",
            extra={
                "total_requested": len(note_ids),
                "total_found": len(score_resources),
                "total_not_found": len(not_found),
            },
        )

        response = NoteScoreListResponse(
            data=score_resources,
            links=JSONAPILinks(self_=str(request.url)),
            meta={
                "total_requested": len(note_ids),
                "total_found": len(score_resources),
                "not_found": not_found,
            },
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get batch note scores (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to retrieve batch note scores",
        )


@router.get("/scoring/notes/top", response_class=JSONResponse, response_model=NoteScoreListResponse)
async def get_top_notes_jsonapi(  # noqa: PLR0912
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    limit: int = Query(10, ge=1, le=100, description="Maximum number of notes to return"),
    min_confidence: ScoreConfidence | None = Query(
        None, description="Minimum confidence level filter"
    ),
    tier: int | None = Query(None, ge=0, le=5, description="Filter by scoring tier"),
    batch_size: int = Query(1000, ge=100, le=5000, description="Batch size for processing"),
    community_server_id: UUID | None = Query(None, description="Filter by community server"),
) -> JSONResponse:
    """Get top-scored notes in JSON:API format.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.

    Returns the highest-scored notes with:
    - Score and confidence metadata
    - Tier information
    - Rating counts
    - Optional filtering by confidence level and tier

    Query Parameters:
    - limit: Number of results (1-100, default 10)
    - min_confidence: Filter by confidence level (no_data, provisional, standard)
    - tier: Filter by scoring tier (0-5)
    - batch_size: Processing batch size (100-5000, default 1000)
    - community_server_id: Filter by community server UUID
    """
    try:
        community_server_id_value = community_server_id
        community_server_id_in_value = None
        if not is_service_account(current_user) and not community_server_id:
            user_communities = await get_user_community_ids(current_user, db)
            if not user_communities:
                response = NoteScoreListResponse(
                    data=[],
                    links=JSONAPILinks(self_=str(request.url)),
                    meta={
                        "total_count": 0,
                        "current_tier": 0,
                        "filters_applied": {},
                    },
                )
                return JSONResponse(
                    content=response.model_dump(by_alias=True, mode="json"),
                    media_type=JSONAPI_CONTENT_TYPE,
                )
            community_server_id_value = None
            community_server_id_in_value = user_communities

        try:
            filters = await top_notes_filter_builder.build_async(
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
        except HTTPException as e:
            return create_error_response(
                e.status_code,
                "Forbidden",
                e.detail,
            )

        base_query = select(Note).options(*full())
        if filters:
            base_query = base_query.where(and_(*filters))

        count_query = select(func.count(Note.id))
        if filters:
            count_query = count_query.where(and_(*filters))
        count_result = await db.execute(count_query)
        note_count = count_result.scalar() or 0

        active_tier_enum = get_tier_for_note_count(note_count)
        active_tier_level = get_tier_level(active_tier_enum)

        confidence_order = {
            ScoreConfidence.NO_DATA: 0,
            ScoreConfidence.PROVISIONAL: 1,
            ScoreConfidence.STANDARD: 2,
        }
        min_confidence_level = confidence_order.get(min_confidence, 0) if min_confidence else 0

        top_scored_notes: list[tuple[Note, Any]] = []
        offset = 0
        processed_count = 0
        filters_applied: dict[str, Any] = {}

        if min_confidence:
            filters_applied["min_confidence"] = min_confidence.value
        if tier is not None:
            filters_applied["tier"] = tier
        if community_server_id:
            filters_applied["community_server_id"] = str(community_server_id)

        logger.info(
            "Starting batch processing for top notes (JSON:API)",
            extra={
                "total_notes": note_count,
                "batch_size": batch_size,
                "requested_limit": limit,
            },
        )

        while offset < note_count:
            batch_result = await db.execute(base_query.offset(offset).limit(batch_size))
            batch_notes = batch_result.scalars().all()

            if not batch_notes:
                break

            for note in batch_notes:
                community_id = str(note.community_server_id) if note.community_server_id else ""
                scorer = scorer_factory.get_scorer(community_id, note_count)
                score_response = await calculate_note_score(note, note_count, scorer)

                if (
                    min_confidence
                    and confidence_order[score_response.confidence] < min_confidence_level
                ):
                    continue
                if tier is not None and score_response.tier != tier:
                    continue

                top_scored_notes.append((note, score_response))

                if len(top_scored_notes) > limit * 5:
                    top_scored_notes.sort(key=lambda x: x[1].score, reverse=True)
                    top_scored_notes = top_scored_notes[: limit * 3]

            processed_count += len(batch_notes)
            offset += batch_size

        top_scored_notes.sort(key=lambda x: x[1].score, reverse=True)
        total_count = len(top_scored_notes)
        paginated_notes = top_scored_notes[:limit]

        score_resources = [
            note_score_to_resource(note.id, score) for note, score in paginated_notes
        ]

        logger.info(
            "Top notes retrieved (JSON:API)",
            extra={
                "total_notes": note_count,
                "processed_count": processed_count,
                "filtered_count": total_count,
                "returned_count": len(score_resources),
                "filters": filters_applied,
                "current_tier": active_tier_level,
            },
        )

        response = NoteScoreListResponse(
            data=score_resources,
            links=JSONAPILinks(self_=str(request.url)),
            meta={
                "total_count": total_count,
                "current_tier": active_tier_level,
                "filters_applied": filters_applied,
            },
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get top notes (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to retrieve top notes",
        )


@router.post("/scoring/score", response_class=JSONResponse, response_model=ScoringResultResponse)
async def score_notes_jsonapi(
    body: ScoringRunRequest,
    request: HTTPRequest,
    _current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Score notes using the external scoring adapter in JSON:API format.

    This endpoint runs the Community Notes scoring algorithm on the provided
    notes, ratings, and enrollment data.

    JSON:API request body must contain:
    - data.type: "scoring-requests"
    - data.attributes.notes: List of notes to score
    - data.attributes.ratings: List of ratings for the notes
    - data.attributes.enrollment: List of user enrollment data
    - data.attributes.status: Optional note status history

    Returns JSON:API formatted response with scored_notes, helpful_scores,
    and auxiliary_info.
    """
    try:
        attrs = body.data.attributes
        notes = [note.model_dump() for note in attrs.notes]
        ratings = [rating.model_dump() for rating in attrs.ratings]
        enrollment = [enroll.model_dump() for enroll in attrs.enrollment]

        scored_notes, helpful_scores, aux_info = await scoring_adapter.score_notes(
            notes=notes,
            ratings=ratings,
            enrollment=enrollment,
            status=attrs.status,
        )

        scoring_run_id = str(uuid.uuid4())

        response = ScoringResultResponse(
            data=ScoringResultResource(
                type="scoring-results",
                id=scoring_run_id,
                attributes=ScoringResultAttributes(
                    scored_notes=scored_notes,
                    helpful_scores=helpful_scores,
                    auxiliary_info=aux_info,
                ),
            ),
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except ValueError as e:
        logger.warning(f"Invalid scoring request: {e}")
        return create_error_response(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            f"Invalid input data: {e!s}",
        )
    except Exception as e:
        logger.exception(f"Scoring failed (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            f"Scoring failed: {e!s}",
        )


@router.get("/scoring/health")
async def scoring_health_jsonapi() -> dict[str, str]:
    """Health check for the scoring service.

    Returns a simple health status for the scoring service.
    This endpoint does not require authentication.
    """
    return {"status": "healthy", "service": "scoring"}
