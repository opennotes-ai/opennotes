"""Candidate promotion logic for fact-check items.

Promotes verified candidates from fact_checked_item_candidates
to the main fact_check_items table.
"""

import logging
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.fact_checking.models import FactCheckItem

logger = logging.getLogger(__name__)


def _validate_candidate_for_promotion(
    candidate: FactCheckedItemCandidate | None, candidate_id: UUID
) -> str | None:
    """Validate candidate is ready for promotion.

    Accepts candidates with status SCRAPED or PROMOTING. Accepting PROMOTING
    enables retry/idempotency: if a batch job crashes mid-promotion, the next
    run can immediately retry without waiting for a recovery timeout.

    State machine: SCRAPED -> PROMOTING -> PROMOTED (success)
                           -> PROMOTING (retry on failure/crash)

    Returns:
        None if valid, error message string if invalid.
    """
    if not candidate:
        return f"Candidate not found for promotion: {candidate_id}"

    if not candidate.content or candidate.content == "":
        return f"Cannot promote candidate without content: {candidate_id}"

    if not candidate.rating:
        return f"Cannot promote candidate without human-approved rating: {candidate_id}"

    if candidate.status not in (CandidateStatus.SCRAPED.value, CandidateStatus.PROMOTING.value):
        return f"Cannot promote candidate with status {candidate.status}: {candidate_id}"

    return None


async def promote_candidate(session: AsyncSession, candidate_id: UUID) -> bool:
    """Promote a candidate to the fact_check_items table.

    Creates a new FactCheckItem from the candidate data and marks
    the candidate as promoted.

    Requirements for promotion:
    - Candidate must exist
    - Candidate must have content
    - Candidate must have a human-approved rating
    - Candidate status must be 'scraped'

    Note: Rating must be set via human approval (possibly bulk approval)
    before promotion. The predicted_ratings field can be used to suggest
    ratings but doesn't allow automatic promotion.

    Args:
        session: Database session.
        candidate_id: UUID of the candidate to promote.

    Returns:
        True if promotion succeeded, False otherwise.
    """
    result = await session.execute(
        select(FactCheckedItemCandidate).where(FactCheckedItemCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if candidate and candidate.status == CandidateStatus.PROMOTED.value:
        logger.info(f"Candidate already promoted: {candidate_id}")
        return True

    error = _validate_candidate_for_promotion(candidate, candidate_id)
    if error:
        logger.warning(error)
        return False

    if candidate is None:
        raise RuntimeError(f"Candidate {candidate_id} unexpectedly None after validation")

    try:
        fact_check_item = FactCheckItem(
            dataset_name=candidate.dataset_name,
            dataset_tags=candidate.dataset_tags
            if candidate.dataset_tags
            else [candidate.dataset_name],
            title=candidate.title,
            content=candidate.content,
            summary=candidate.summary,
            source_url=candidate.source_url,
            original_id=candidate.original_id,
            published_date=candidate.published_date,
            rating=candidate.rating,
            rating_details=candidate.rating_details,
            extra_metadata=candidate.extracted_data,
        )

        session.add(fact_check_item)

        await session.execute(
            update(FactCheckedItemCandidate)
            .where(FactCheckedItemCandidate.id == candidate_id)
            .values(status=CandidateStatus.PROMOTED.value, updated_at=func.now())
        )

        await session.commit()

        logger.info(f"Promoted candidate {candidate_id} to fact_check_item {fact_check_item.id}")

        try:
            from src.batch_jobs.rechunk_service import (  # noqa: PLC0415
                enqueue_single_fact_check_chunk,
            )

            success = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_item.id,
                community_server_id=None,
            )
            if success:
                logger.info(
                    f"Enqueued chunking task for promoted fact_check_item {fact_check_item.id}"
                )
            else:
                logger.warning(
                    f"Failed to enqueue chunking task for fact_check_item {fact_check_item.id}. "
                    f"Item was promoted but will need manual rechunking."
                )
        except Exception as chunk_error:
            logger.warning(
                f"Failed to enqueue chunking task for fact_check_item {fact_check_item.id}: "
                f"{chunk_error}. Item was promoted but will need manual rechunking."
            )

        return True

    except Exception as e:
        await session.rollback()
        logger.exception(f"Failed to promote candidate {candidate_id}: {e}")
        return False


async def bulk_promote_scraped(session: AsyncSession, batch_size: int = 100) -> int:
    """Promote all scraped candidates with approved ratings to fact_check_items.

    Finds candidates with status='scraped' or 'promoting', content, and human-approved
    rating, then promotes each to the main table. Including 'promoting' status enables
    retry/idempotency: if a batch job crashes mid-promotion, the next run can
    immediately retry without waiting for a recovery timeout.

    Args:
        session: Database session.
        batch_size: Maximum number of candidates to promote.

    Returns:
        Number of successfully promoted candidates.
    """
    result = await session.execute(
        select(FactCheckedItemCandidate.id)
        .where(
            FactCheckedItemCandidate.status.in_(
                [CandidateStatus.SCRAPED.value, CandidateStatus.PROMOTING.value]
            )
        )
        .where(FactCheckedItemCandidate.content.is_not(None))
        .where(FactCheckedItemCandidate.content != "")
        .where(FactCheckedItemCandidate.rating.is_not(None))
        .limit(batch_size)
    )
    candidate_ids = [row[0] for row in result.fetchall()]

    if not candidate_ids:
        logger.info("No scraped candidates to promote")
        return 0

    promoted_count = 0
    for cid in candidate_ids:
        if await promote_candidate(session, cid):
            promoted_count += 1

    logger.info(f"Promoted {promoted_count}/{len(candidate_ids)} candidates")
    return promoted_count
