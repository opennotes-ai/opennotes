from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_user_community_ids,
    verify_community_membership_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.config import settings
from src.database import get_db
from src.events.scoring_events import ScoringEventPublisher
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.monitoring.metrics import nats_events_failed_total
from src.notes import loaders
from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel
from src.notes.scoring import (
    ScorerFactory,
    ScorerProtocol,
    ScoringTier,
    get_tier_config,
    get_tier_for_note_count,
)
from src.notes.scoring_schemas import (
    BatchScoreRequest,
    BatchScoreResponse,
    DataConfidence,
    NextTierInfo,
    NoteScoreResponse,
    PerformanceMetrics,
    ScoreConfidence,
    ScoringRequest,
    ScoringResponse,
    ScoringStatusResponse,
    TierInfo,
    TierThreshold,
    TopNotesResponse,
)
from src.users.models import User

if settings.TESTING:
    from src.scoring_adapter_mock import ScoringAdapter
else:
    try:
        from src.scoring_adapter import ScoringAdapter  # type: ignore[assignment]
    except ImportError:
        from src.scoring_adapter_mock import ScoringAdapter

logger = get_logger(__name__)

router = APIRouter(prefix="/scoring", tags=["scoring"])

scoring_adapter = ScoringAdapter()
scorer_factory = ScorerFactory()


# Tier ordering for iteration
TIER_ORDER = [
    ScoringTier.MINIMAL,
    ScoringTier.LIMITED,
    ScoringTier.BASIC,
    ScoringTier.INTERMEDIATE,
    ScoringTier.ADVANCED,
    ScoringTier.FULL,
]


def get_tier_level(tier: ScoringTier) -> int:
    """Get numeric level (0-5) for a tier."""
    return TIER_ORDER.index(tier)


def get_tier_by_level(level: int) -> ScoringTier | None:
    """Get tier enum by numeric level."""
    if 0 <= level < len(TIER_ORDER):
        return TIER_ORDER[level]
    return None


def get_next_tier(tier: ScoringTier) -> ScoringTier | None:
    """Get the next tier in the hierarchy, or None if at maximum."""
    try:
        current_index = TIER_ORDER.index(tier)
        if current_index + 1 < len(TIER_ORDER):
            return TIER_ORDER[current_index + 1]
    except ValueError:
        pass
    return None


def get_tier_data_confidence(tier: ScoringTier) -> DataConfidence:
    """Map tier to DataConfidence enum."""
    tier_config = get_tier_config(tier)
    if tier_config.confidence_warnings:
        if tier == ScoringTier.MINIMAL:
            return DataConfidence.NONE
        return DataConfidence.LOW
    if tier in (ScoringTier.BASIC,):
        return DataConfidence.MEDIUM
    if tier in (ScoringTier.INTERMEDIATE, ScoringTier.ADVANCED):
        return DataConfidence.HIGH
    return DataConfidence.VERY_HIGH


@router.get("/status", response_model=ScoringStatusResponse)
async def get_scoring_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> ScoringStatusResponse:
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
            "Scoring status retrieved",
            extra={
                "note_count": note_count,
                "active_tier": active_tier_enum.value,
                "confidence": data_confidence,
            },
        )

        return ScoringStatusResponse(
            current_note_count=note_count,
            active_tier=active_tier,
            data_confidence=data_confidence,
            tier_thresholds=tier_thresholds,
            next_tier_upgrade=next_tier_upgrade,
            performance_metrics=performance_metrics,
            warnings=warnings,
            configuration={},
        )

    except Exception as e:
        logger.exception(f"Failed to get scoring status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scoring status",
        ) from e


def convert_ratings_to_floats(ratings: list[Rating]) -> list[float]:
    """
    Convert Rating objects to float values (0.0-1.0) for scoring.

    Uses the centralized to_score_value() method from HelpfulnessLevel enum
    to ensure consistent scoring across the application.
    """
    result = []
    for rating in ratings:
        # Rating.helpfulness_level is Mapped[str], convert to enum for scoring
        helpfulness_enum = HelpfulnessLevel(rating.helpfulness_level)
        result.append(helpfulness_enum.to_score_value())
    return result


async def calculate_note_score(
    note: Note, note_count: int, scorer: ScorerProtocol
) -> NoteScoreResponse:
    """Calculate score for a single note with metadata."""
    active_tier_enum = get_tier_for_note_count(note_count)
    active_tier_level = get_tier_level(active_tier_enum)

    rating_values = convert_ratings_to_floats(note.ratings)
    rating_count = len(rating_values)

    result = scorer.score_note(str(note.id), rating_values)

    if rating_count == 0 or result.metadata.get("no_data"):
        confidence = ScoreConfidence.NO_DATA
    elif result.confidence_level == "provisional":
        confidence = ScoreConfidence.PROVISIONAL
    else:
        confidence = ScoreConfidence.STANDARD

    calculated_at = note.updated_at if note.updated_at else note.created_at

    content = None
    if note.request and note.request.message_archive:
        content = note.request.message_archive.get_content()

    return NoteScoreResponse(
        note_id=note.id,
        score=result.score,
        confidence=confidence,
        algorithm=result.metadata.get("algorithm", "bayesian_average_tier0"),
        rating_count=rating_count,
        tier=active_tier_level,
        tier_name=active_tier_enum.value.capitalize(),
        calculated_at=calculated_at,
        content=content,
    )


@router.get("/notes/{note_id}/score", response_model=NoteScoreResponse)
async def get_note_score(
    note_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> NoteScoreResponse:
    """
    Get individual note score with metadata.

    Users can only view scores for notes in communities they are members of.
    Service accounts can view all scores.

    Returns the calculated score for a specific note along with:
    - Algorithm used for scoring
    - Confidence level based on rating count
    - Current scoring tier information
    - Number of ratings
    - Timestamp of calculation

    Returns:
        - 200: Score calculated successfully
        - 403: User not member of note's community
        - 404: Note not found
        - 500: Server error
    """
    try:
        # Fetch note with ratings and request (explicitly load for content access)
        result = await db.execute(select(Note).options(*loaders.full()).where(Note.id == note_id))
        note = result.scalar_one_or_none()

        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Note with ID {note_id} not found",
            )

        # Verify community membership (service accounts bypass)
        if not is_service_account(current_user) and note.community_server_id:
            await verify_community_membership_by_uuid(
                note.community_server_id, current_user, db, request
            )

        count_result = await db.execute(select(func.count(Note.id)))
        note_count = count_result.scalar() or 0

        community_id = str(note.community_server_id) if note.community_server_id else ""
        scorer = scorer_factory.get_scorer(community_id, note_count)

        score_response = await calculate_note_score(note, note_count, scorer)

        logger.info(
            f"Score retrieved for note {note_id}",
            extra={
                "note_id": note_id,
                "score": score_response.score,
                "confidence": score_response.confidence,
                "rating_count": score_response.rating_count,
            },
        )

        # Publish score update event for Discord bot and other consumers
        # If this fails, the score was still calculated successfully
        try:
            # Get original_message_id from message archive
            original_message_id = None
            if note.request and note.request.message_archive:
                original_message_id = note.request.message_archive.platform_message_id

            await ScoringEventPublisher.publish_note_score_updated(
                note_id=note_id,
                score=score_response.score,
                confidence=score_response.confidence.value,
                algorithm=score_response.algorithm,
                rating_count=score_response.rating_count,
                tier=score_response.tier,
                tier_name=score_response.tier_name,
                original_message_id=original_message_id,
            )
            logger.info(
                "Published score update event",
                extra={
                    "note_id": note_id,
                    "score": score_response.score,
                },
            )
        except Exception as e:
            error_type = type(e).__name__
            nats_events_failed_total.labels(
                event_type="note.score.updated", error_type=error_type
            ).inc()
            logger.error(
                "Failed to publish score update event, but score calculation succeeded",
                extra={
                    "note_id": note_id,
                    "error": str(e),
                    "error_type": error_type,
                },
                exc_info=True,
            )

        return score_response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get score for note {note_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve note score",
        ) from e


@router.post("/notes/batch-scores", response_model=BatchScoreResponse)
@limiter.limit("10/minute;50/hour")
async def get_batch_note_scores(
    batch_request: BatchScoreRequest,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchScoreResponse:
    """
    Get scores for multiple notes in a single request.

    Users can only get scores for notes in communities they are members of.
    Notes from other communities will be treated as "not found" in the response.
    Service accounts can access all notes.

    Efficiently retrieves scores for multiple notes to prevent N+1 query patterns.
    Returns a map of note IDs to their score responses, along with a list of
    note IDs that were not found.

    Args:
        request: BatchScoreRequest containing list of note IDs

    Returns:
        - 200: Scores retrieved successfully (includes partial results)
        - 400: Invalid request (empty list, too many IDs)
        - 500: Server error

    Performance: This endpoint processes all notes in a single database query
    and calculates scores efficiently, reducing overhead compared to individual
    requests for each note.
    """
    try:
        note_ids = batch_request.note_ids

        # Additional validation (schema already limits to 100, but double-check)
        if len(note_ids) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch size exceeds maximum of 100 items",
            )

        logger.info(
            f"Batch score request for {len(note_ids)} notes",
            extra={
                "note_count": len(note_ids),
                "note_ids": note_ids[:10],  # Log first 10 for debugging
            },
        )

        # Get user's accessible communities for filtering
        user_communities: list[UUID] = []
        if not is_service_account(current_user):
            user_communities = await get_user_community_ids(current_user, db)

        # Fetch all requested notes in a single query with ratings and request
        result = await db.execute(
            select(Note).options(*loaders.full()).where(Note.id.in_(note_ids))
        )
        notes = result.scalars().all()

        count_result = await db.execute(select(func.count(Note.id)))
        total_note_count = count_result.scalar() or 0

        scores_map: dict[UUID, NoteScoreResponse] = {}
        found_note_ids = set()

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
            scores_map[note.id] = score_response
            found_note_ids.add(note.id)

        # Determine which notes were not found (or not accessible)
        requested_note_ids = set(note_ids)
        not_found = list(requested_note_ids - found_note_ids)

        logger.info(
            "Batch score request completed",
            extra={
                "total_requested": len(note_ids),
                "total_found": len(scores_map),
                "total_not_found": len(not_found),
            },
        )

        return BatchScoreResponse(
            scores=scores_map,
            not_found=not_found,
            total_requested=len(note_ids),
            total_found=len(scores_map),
        )

    except Exception as e:
        logger.exception(f"Failed to get batch note scores: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve batch note scores",
        ) from e


@router.get("/notes/top", response_model=TopNotesResponse)
async def get_top_notes(  # noqa: PLR0912
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    limit: int = Query(10, ge=1, le=100, description="Maximum number of notes to return"),
    min_confidence: ScoreConfidence | None = Query(
        None, description="Minimum confidence level filter (no_data, provisional, standard)"
    ),
    tier: int | None = Query(None, ge=0, le=5, description="Filter by scoring tier (0-5)"),
    batch_size: int = Query(1000, ge=100, le=5000, description="Batch size for processing notes"),
    community_server_id: UUID | None = Query(None, description="Filter by community server"),
) -> TopNotesResponse:
    """
    Get top-scored notes with optional filtering.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.

    Returns the highest-scored notes in the system with:
    - Score and confidence metadata
    - Tier information
    - Rating counts
    - Optional filtering by confidence level and tier

    Uses batch processing to prevent memory exhaustion with large note counts.

    Query Parameters:
        - limit: Number of results (1-100, default 10)
        - min_confidence: Filter by confidence level
        - tier: Filter by scoring tier (0-5)
        - batch_size: Number of notes to process per batch (100-5000, default 1000)
        - community_server_id: Filter by community server (UUID)

    Returns:
        - 200: Top notes retrieved successfully
        - 403: User not member of specified community
        - 500: Server error
    """
    try:
        # Get user's accessible communities for filtering
        user_communities: list[UUID] = []
        if not is_service_account(current_user):
            if community_server_id:
                # If specific community requested, verify membership
                await verify_community_membership_by_uuid(
                    community_server_id, current_user, db, request
                )
                user_communities = [community_server_id]
            else:
                user_communities = await get_user_community_ids(current_user, db)
                if not user_communities:
                    # User not member of any community, return empty
                    return TopNotesResponse(
                        notes=[],
                        total_count=0,
                        filters_applied={},
                        current_tier=0,
                    )

        # Build base query with community filtering
        base_query = select(Note).options(*loaders.full())
        if not is_service_account(current_user):
            base_query = base_query.where(Note.community_server_id.in_(user_communities))
        elif community_server_id:
            # Service account with community filter
            base_query = base_query.where(Note.community_server_id == community_server_id)

        # Get total note count for tier determination (within accessible communities)
        count_query = select(func.count(Note.id))
        if not is_service_account(current_user):
            count_query = count_query.where(Note.community_server_id.in_(user_communities))
        elif community_server_id:
            count_query = count_query.where(Note.community_server_id == community_server_id)
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

        # Process notes in batches to prevent memory exhaustion
        top_scored_notes: list[tuple[Note, NoteScoreResponse]] = []
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
            "Starting batch processing for top notes",
            extra={
                "total_notes": note_count,
                "batch_size": batch_size,
                "requested_limit": limit,
            },
        )

        while offset < note_count:
            # Fetch batch of notes with ratings
            batch_result = await db.execute(base_query.offset(offset).limit(batch_size))
            batch_notes = batch_result.scalars().all()

            if not batch_notes:
                break

            for note in batch_notes:
                community_id = str(note.community_server_id) if note.community_server_id else ""
                scorer = scorer_factory.get_scorer(community_id, note_count)
                score_response = await calculate_note_score(note, note_count, scorer)

                # Apply filters
                if (
                    min_confidence
                    and confidence_order[score_response.confidence] < min_confidence_level
                ):
                    continue
                if tier is not None and score_response.tier != tier:
                    continue

                # Add to top scored notes
                top_scored_notes.append((note, score_response))

                # Keep only top N + some buffer to reduce memory
                # We keep 5x the limit to ensure we have enough after final sorting
                if len(top_scored_notes) > limit * 5:
                    top_scored_notes.sort(key=lambda x: x[1].score, reverse=True)
                    top_scored_notes = top_scored_notes[: limit * 3]

            processed_count += len(batch_notes)
            offset += batch_size

            logger.debug(
                "Processed batch",
                extra={
                    "offset": offset,
                    "batch_size": len(batch_notes),
                    "processed_count": processed_count,
                    "top_notes_count": len(top_scored_notes),
                },
            )

        # Final sort and limit
        top_scored_notes.sort(key=lambda x: x[1].score, reverse=True)
        total_count = len(top_scored_notes)
        paginated_notes = top_scored_notes[:limit]

        # Extract score responses
        top_scores = [score for _, score in paginated_notes]

        logger.info(
            "Top notes retrieved",
            extra={
                "total_notes": note_count,
                "processed_count": processed_count,
                "filtered_count": total_count,
                "returned_count": len(top_scores),
                "filters": filters_applied,
                "current_tier": active_tier_level,
            },
        )

        return TopNotesResponse(
            notes=top_scores,
            total_count=total_count,
            filters_applied=filters_applied,
            current_tier=active_tier_level,
        )

    except Exception as e:
        logger.exception(f"Failed to get top notes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve top notes",
        ) from e


@router.post(
    "/score",
    response_model=ScoringResponse,
    status_code=status.HTTP_200_OK,
)
async def score_notes(
    request: ScoringRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> ScoringResponse:
    try:
        notes = [note.model_dump() for note in request.notes]
        ratings = [rating.model_dump() for rating in request.ratings]
        enrollment = [enroll.model_dump() for enroll in request.enrollment]

        scored_notes, helpful_scores, aux_info = await scoring_adapter.score_notes(
            notes=notes,
            ratings=ratings,
            enrollment=enrollment,
            status=request.status,
        )

        return ScoringResponse(
            scored_notes=scored_notes,
            helpful_scores=helpful_scores,
            auxiliary_info=aux_info,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input data: {e!s}",
        )
    except Exception as e:
        logger.exception(f"Scoring failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scoring failed: {e!s}",
        )


@router.get("/health")
async def scoring_health() -> dict[str, str]:
    return {"status": "healthy", "service": "scoring"}
