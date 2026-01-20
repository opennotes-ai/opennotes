"""Service layer for fact-check candidate operations.

Provides business logic for listing, filtering, rating, and bulk approving
fact-check candidates.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, cast, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.promotion import promote_candidate

logger = logging.getLogger(__name__)


def extract_high_confidence_rating(
    predicted_ratings: dict[str, float | int] | None,
    threshold: float = 1.0,
) -> str | None:
    """Extract rating from predicted_ratings where value >= threshold.

    Handles both integer and float values since JSON may deserialize
    whole numbers as integers (1) rather than floats (1.0).

    Args:
        predicted_ratings: Dictionary mapping rating keys to probability values.
        threshold: Minimum value for a rating to be considered high-confidence.

    Returns:
        First rating key where value >= threshold, or None if no match.

    Examples:
        >>> extract_high_confidence_rating({"false": 1.0}, 1.0)
        'false'
        >>> extract_high_confidence_rating({"false": 1}, 1.0)  # int value
        'false'
        >>> extract_high_confidence_rating({"false": 0.85}, 1.0)
        None
        >>> extract_high_confidence_rating(None, 1.0)
        None
    """
    if not predicted_ratings:
        return None

    for rating_key, probability in predicted_ratings.items():
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

    Args:
        session: Database session.
        candidate_id: ID of the candidate to update.
        rating: The rating to set.
        rating_details: Optional original rating value if normalized.
        auto_promote: Whether to attempt promotion after setting rating.

    Returns:
        Tuple of (updated_candidate, was_promoted).
    """
    candidate = await get_candidate_by_id(session, candidate_id)

    if not candidate:
        logger.warning(f"Candidate not found for rating: {candidate_id}")
        return None, False

    await session.execute(
        update(FactCheckedItemCandidate)
        .where(FactCheckedItemCandidate.id == candidate_id)
        .values(
            rating=rating,
            rating_details=rating_details,
            updated_at=func.now(),
        )
    )
    await session.commit()

    await session.refresh(candidate)

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
) -> tuple[int, int | None]:
    """Bulk set ratings from predicted_ratings where prediction >= threshold.

    Finds candidates matching filters that:
    - Have no rating set
    - Have a predicted_ratings entry with value >= threshold

    For each matching candidate, sets rating to the first key with value >= threshold.

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

    query = select(FactCheckedItemCandidate).where(and_(*filters))

    result = await session.execute(query)
    candidates = result.scalars().all()

    updated_count = 0
    promoted_count = 0 if auto_promote else None

    for candidate in candidates:
        rating = extract_high_confidence_rating(candidate.predicted_ratings, threshold)
        if rating is None:
            continue

        await session.execute(
            update(FactCheckedItemCandidate)
            .where(FactCheckedItemCandidate.id == candidate.id)
            .values(rating=rating, updated_at=func.now())
        )
        updated_count += 1

        if auto_promote and promoted_count is not None:
            await session.commit()
            promoted = await promote_candidate(session, candidate.id)
            if promoted:
                promoted_count += 1

    if not auto_promote or updated_count == 0:
        await session.commit()

    logger.info(
        f"Bulk approved {updated_count} candidates from predictions "
        f"(threshold={threshold}, auto_promote={auto_promote}, promoted={promoted_count})"
    )

    return updated_count, promoted_count
