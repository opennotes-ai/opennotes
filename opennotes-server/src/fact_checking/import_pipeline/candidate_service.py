"""Service layer for fact-check candidate operations.

Provides business logic for listing, filtering, rating, and bulk approving
fact-check candidates.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, cast, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.promotion import promote_candidate

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def extract_high_confidence_rating(
    predicted_ratings: dict[str, float | int] | None,
    threshold: float = 1.0,
) -> str | None:
    """Extract highest-probability rating from predicted_ratings where value >= threshold.

    Handles both integer and float values since JSON may deserialize
    whole numbers as integers (1) rather than floats (1.0).

    When multiple ratings meet the threshold, returns the one with the highest
    probability. This ensures deterministic behavior regardless of dict ordering.

    Args:
        predicted_ratings: Dictionary mapping rating keys to probability values.
        threshold: Minimum value for a rating to be considered high-confidence.

    Returns:
        Rating key with highest probability >= threshold, or None if no match.

    Examples:
        >>> extract_high_confidence_rating({"false": 1.0}, 1.0)
        'false'
        >>> extract_high_confidence_rating({"false": 1}, 1.0)  # int value
        'false'
        >>> extract_high_confidence_rating({"false": 0.85}, 1.0)
        None
        >>> extract_high_confidence_rating(None, 1.0)
        None
        >>> extract_high_confidence_rating({"a": 0.9, "b": 0.95}, 0.85)  # returns highest
        'b'
    """
    if not predicted_ratings:
        return None

    sorted_ratings = sorted(
        predicted_ratings.items(),
        key=lambda x: float(x[1]),
        reverse=True,
    )

    for rating_key, probability in sorted_ratings:
        if float(probability) >= threshold:
            return rating_key

    return None


async def list_candidates(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    dataset_name: str | None = None,
    dataset_tags: list[str] | None = None,
    rating_filter: str | None = None,
    has_content: bool | None = None,
    published_date_from: datetime | None = None,
    published_date_to: datetime | None = None,
) -> tuple[list[FactCheckedItemCandidate], int]:
    """List candidates with filters and pagination.

    Args:
        session: Database session.
        page: Page number (1-indexed).
        page_size: Number of items per page.
        status: Filter by candidate status (exact match).
        dataset_name: Filter by dataset name (exact match).
        dataset_tags: Filter by dataset tags (array overlap).
        rating_filter: Filter by rating: "null", "not_null", or exact value.
        has_content: Filter by whether content exists.
        published_date_from: Filter by published_date >= this value.
        published_date_to: Filter by published_date <= this value.

    Returns:
        Tuple of (candidates, total_count).
    """
    filters = _build_filters(
        status=status,
        dataset_name=dataset_name,
        dataset_tags=dataset_tags,
        rating_filter=rating_filter,
        has_content=has_content,
        published_date_from=published_date_from,
        published_date_to=published_date_to,
    )

    query = select(FactCheckedItemCandidate)
    count_query = select(func.count(FactCheckedItemCandidate.id))

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    query = query.order_by(FactCheckedItemCandidate.created_at.desc())
    query = query.limit(page_size).offset((page - 1) * page_size)

    result = await session.execute(query)
    candidates = list(result.scalars().all())

    return candidates, total


def _build_filters(
    status: str | None = None,
    dataset_name: str | None = None,
    dataset_tags: list[str] | None = None,
    rating_filter: str | None = None,
    has_content: bool | None = None,
    published_date_from: datetime | None = None,
    published_date_to: datetime | None = None,
) -> list:
    """Build SQLAlchemy filter conditions for candidate queries."""
    filters = []

    if status is not None:
        filters.append(FactCheckedItemCandidate.status == status)

    if dataset_name is not None:
        filters.append(FactCheckedItemCandidate.dataset_name == dataset_name)

    if dataset_tags:
        filters.append(
            FactCheckedItemCandidate.dataset_tags.op("&&")(cast(dataset_tags, ARRAY(Text)))
        )

    if rating_filter is not None:
        if rating_filter == "null":
            filters.append(FactCheckedItemCandidate.rating.is_(None))
        elif rating_filter == "not_null":
            filters.append(FactCheckedItemCandidate.rating.is_not(None))
        else:
            filters.append(FactCheckedItemCandidate.rating == rating_filter)

    if has_content is not None:
        if has_content:
            filters.append(FactCheckedItemCandidate.content.is_not(None))
            filters.append(FactCheckedItemCandidate.content != "")
        else:
            filters.append(
                (FactCheckedItemCandidate.content.is_(None))
                | (FactCheckedItemCandidate.content == "")
            )

    if published_date_from is not None:
        filters.append(FactCheckedItemCandidate.published_date >= published_date_from)

    if published_date_to is not None:
        filters.append(FactCheckedItemCandidate.published_date <= published_date_to)

    return filters


async def get_candidate_by_id(
    session: AsyncSession,
    candidate_id: UUID,
) -> FactCheckedItemCandidate | None:
    """Fetch a candidate by ID."""
    result = await session.execute(
        select(FactCheckedItemCandidate).where(FactCheckedItemCandidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


async def set_candidate_rating(
    session: AsyncSession,
    candidate_id: UUID,
    rating: str,
    rating_details: str | None = None,
    auto_promote: bool = False,
) -> tuple[FactCheckedItemCandidate | None, bool]:
    """Set rating on a candidate and optionally promote.

    Uses atomic UPDATE...RETURNING to avoid TOCTOU race conditions.
    The candidate is updated and returned in a single database operation.

    Args:
        session: Database session.
        candidate_id: ID of the candidate to update.
        rating: The rating to set.
        rating_details: Optional original rating value if normalized.
        auto_promote: Whether to attempt promotion after setting rating.

    Returns:
        Tuple of (updated_candidate, was_promoted).
    """
    stmt = (
        update(FactCheckedItemCandidate)
        .where(FactCheckedItemCandidate.id == candidate_id)
        .values(
            rating=rating,
            rating_details=rating_details,
            updated_at=func.now(),
        )
        .returning(FactCheckedItemCandidate)
    )

    result = await session.execute(stmt)
    candidate = result.scalar_one_or_none()

    if not candidate:
        logger.warning(f"Candidate not found for rating: {candidate_id}")
        return None, False

    await session.commit()

    promoted = False
    if auto_promote:
        promoted = await promote_candidate(session, candidate_id)
        if promoted:
            await session.refresh(candidate)

    logger.info(
        f"Set rating on candidate {candidate_id}: rating={rating}, "
        f"rating_details={rating_details}, promoted={promoted}"
    )

    return candidate, promoted


async def _iter_candidates_for_bulk_approval(
    session: AsyncSession,
    filters: list,
    batch_size: int = BATCH_SIZE,
) -> AsyncIterator[list[FactCheckedItemCandidate]]:
    """Iterate candidates in batches using FOR UPDATE SKIP LOCKED to prevent TOCTOU.

    Uses explicit pagination instead of .all() to avoid loading all candidates
    into memory at once. Each batch is locked with FOR UPDATE SKIP LOCKED to
    prevent concurrent modification.

    Args:
        session: Database session.
        filters: SQLAlchemy filter conditions.
        batch_size: Number of candidates per batch.

    Yields:
        Batches of locked candidates.
    """
    offset = 0
    while True:
        query = (
            select(FactCheckedItemCandidate)
            .where(and_(*filters))
            .order_by(FactCheckedItemCandidate.id)
            .limit(batch_size)
            .offset(offset)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(query)
        batch = list(result.scalars().all())

        if not batch:
            break

        yield batch
        offset += batch_size


async def bulk_approve_from_predictions(
    session: AsyncSession,
    threshold: float = 1.0,
    auto_promote: bool = False,
    status: str | None = None,
    dataset_name: str | None = None,
    dataset_tags: list[str] | None = None,
    has_content: bool | None = None,
    published_date_from: datetime | None = None,
    published_date_to: datetime | None = None,
    limit: int = 200,
) -> tuple[int, int | None]:
    """Bulk set ratings from predicted_ratings where prediction >= threshold.

    Finds candidates matching filters that:
    - Have no rating set
    - Have a predicted_ratings entry with value >= threshold

    For each matching candidate, sets rating to the highest-probability key
    that meets the threshold. Uses batching with FOR UPDATE SKIP LOCKED to
    prevent TOCTOU races and avoid memory issues with large datasets.

    Args:
        session: Database session.
        threshold: Minimum prediction value to approve.
        auto_promote: Whether to promote approved candidates.
        status: Filter by candidate status.
        dataset_name: Filter by dataset name.
        dataset_tags: Filter by dataset tags (array overlap).
        has_content: Filter by whether content exists.
        published_date_from: Filter by published_date >= this value.
        published_date_to: Filter by published_date <= this value.
        limit: Maximum number of candidates to approve (default 200).

    Returns:
        Tuple of (updated_count, promoted_count). promoted_count is None if auto_promote=False.
    """
    filters = _build_filters(
        status=status,
        dataset_name=dataset_name,
        dataset_tags=dataset_tags,
        rating_filter="null",
        has_content=has_content,
        published_date_from=published_date_from,
        published_date_to=published_date_to,
    )

    filters.append(FactCheckedItemCandidate.predicted_ratings.is_not(None))

    updated_count = 0
    promoted_count = 0 if auto_promote else None
    remaining = limit

    async for batch in _iter_candidates_for_bulk_approval(session, filters):
        batch_updates: list[tuple[UUID, str]] = []
        candidates_to_promote: list[UUID] = []

        for candidate in batch:
            if remaining <= 0:
                break

            rating = extract_high_confidence_rating(candidate.predicted_ratings, threshold)
            if rating is None:
                continue

            batch_updates.append((candidate.id, rating))
            if auto_promote:
                candidates_to_promote.append(candidate.id)
            remaining -= 1

        for candidate_id, rating in batch_updates:
            await session.execute(
                update(FactCheckedItemCandidate)
                .where(FactCheckedItemCandidate.id == candidate_id)
                .where(FactCheckedItemCandidate.rating.is_(None))
                .values(rating=rating, updated_at=func.now())
            )
            updated_count += 1

        await session.commit()

        if auto_promote and promoted_count is not None:
            for candidate_id in candidates_to_promote:
                promoted = await promote_candidate(session, candidate_id)
                if promoted:
                    promoted_count += 1

        if remaining <= 0:
            break

    logger.info(
        f"Bulk approved {updated_count} candidates from predictions "
        f"(threshold={threshold}, auto_promote={auto_promote}, promoted={promoted_count}, limit={limit})"
    )

    return updated_count, promoted_count
