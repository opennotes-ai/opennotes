"""TaskIQ task for scraping candidate article content.

Uses Trafilatura for robust web content extraction with:
- Automatic fallback mechanisms
- HTML to clean text extraction
- Language detection
- Comment filtering
"""

import logging
from uuid import UUID

import trafilatura
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_service import (
    extract_high_confidence_rating,
)
from src.fact_checking.import_pipeline.promotion import promote_candidate
from src.tasks.broker import register_task

logger = logging.getLogger(__name__)

# Threshold for auto-applying predicted ratings.
# A value of 1.0 means only apply ratings with 100% confidence.
# This aligns with bulk_approve_from_predictions() default behavior.
AUTO_PROMOTE_PREDICTION_THRESHOLD: float = 1.0


async def get_candidate(
    session: AsyncSession, candidate_id: UUID
) -> FactCheckedItemCandidate | None:
    """Fetch a candidate by ID."""
    result = await session.execute(
        select(FactCheckedItemCandidate).where(FactCheckedItemCandidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


async def update_candidate_status(
    session: AsyncSession,
    candidate_id: UUID,
    status: CandidateStatus,
    content: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update candidate status and optionally content/error.

    Note: Uses direct SQL update for performance. Must explicitly set
    updated_at since SQLAlchemy's onupdate callback only fires for
    ORM-level attribute changes, not direct SQL updates.
    """
    values: dict = {"status": status.value, "updated_at": func.now()}
    if content is not None:
        values["content"] = content
    if error_message is not None:
        values["error_message"] = error_message

    await session.execute(
        update(FactCheckedItemCandidate)
        .where(FactCheckedItemCandidate.id == candidate_id)
        .values(**values)
    )
    await session.commit()


async def apply_predicted_rating_if_available(
    session: AsyncSession,
    candidate: FactCheckedItemCandidate,
    threshold: float = AUTO_PROMOTE_PREDICTION_THRESHOLD,
) -> str | None:
    """Apply high-confidence predicted rating to candidate if eligible.

    When auto_promote is enabled and candidate has no rating but has
    predicted_ratings with a value >= threshold, this copies the predicted
    rating to the rating field to enable promotion.

    Uses atomic UPDATE with WHERE rating IS NULL to prevent TOCTOU race conditions
    when multiple workers process the same candidate concurrently.

    Args:
        session: Database session.
        candidate: The candidate to potentially update. Note: This object becomes
            stale after the update and should be refreshed if further ORM operations
            are needed.
        threshold: Minimum confidence value for a predicted rating to be applied.
            Defaults to AUTO_PROMOTE_PREDICTION_THRESHOLD (1.0).

    Returns:
        The rating applied, or None if no rating was applied (either no eligible
        prediction or another process already set a rating).
    """
    if not candidate.predicted_ratings:
        return None

    rating = extract_high_confidence_rating(candidate.predicted_ratings, threshold=threshold)
    if rating is None:
        return None

    # Use atomic UPDATE with WHERE rating IS NULL to prevent TOCTOU race.
    # If another worker already set the rating, rowcount will be 0.
    result = await session.execute(
        update(FactCheckedItemCandidate)
        .where(FactCheckedItemCandidate.id == candidate.id)
        .where(FactCheckedItemCandidate.rating.is_(None))
        .values(rating=rating, updated_at=func.now())
    )
    await session.commit()

    if result.rowcount == 0:
        logger.debug(
            f"Skipped auto-applying rating for candidate {candidate.id}: "
            "rating already set by another process"
        )
        return None

    logger.info(
        f"Auto-applied rating '{rating}' from predicted_ratings for candidate {candidate.id}"
    )
    return rating


def scrape_url_content(url: str) -> str | None:
    """Scrape and extract main content from a URL using Trafilatura.

    Trafilatura is designed for:
    - News article extraction
    - Clean main content extraction (no boilerplate)
    - Handling various HTML structures

    Args:
        url: The URL to scrape.

    Returns:
        Extracted text content, or None if extraction failed.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning(f"Failed to download URL: {url}")
            return None

        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )

        if not content:
            logger.warning(f"No content extracted from URL: {url}")
            return None

        return content.strip()

    except Exception as e:
        logger.exception(f"Error scraping URL {url}: {e}")
        return None


@register_task(
    task_name="fact_check:scrape_candidate",
    component="import_pipeline",
    task_type="scrape",
)
async def scrape_candidate_content(candidate_id: str, auto_promote: bool = True) -> dict:
    """Scrape article content for a candidate and optionally promote.

    This task:
    1. Fetches the candidate from the database
    2. Sets status to SCRAPING
    3. Scrapes content using Trafilatura
    4. Updates candidate with content or error
    5. Optionally promotes to fact_check_items if successful

    Args:
        candidate_id: UUID of the candidate to scrape.
        auto_promote: If True, automatically promote after successful scrape.

    Returns:
        Dict with status and any relevant details.
    """
    cid = UUID(candidate_id)
    result: dict = {"status": "error", "message": "No database session available"}

    async for session in get_db():
        candidate = await get_candidate(session, cid)

        if not candidate:
            logger.error(f"Candidate not found: {candidate_id}")
            result = {"status": "error", "message": "Candidate not found"}
            break

        if candidate.status == CandidateStatus.PROMOTED.value:
            logger.info(f"Candidate already promoted: {candidate_id}")
            result = {"status": "skipped", "message": "Already promoted"}
            break

        if candidate.content:
            logger.info(f"Candidate already has content: {candidate_id}")
            if auto_promote:
                await apply_predicted_rating_if_available(session, candidate)
                promoted = await promote_candidate(session, cid)
                result = {"status": "promoted" if promoted else "promotion_failed"}
            else:
                result = {"status": "skipped", "message": "Already scraped"}
            break

        await update_candidate_status(session, cid, CandidateStatus.SCRAPING)

        content = scrape_url_content(candidate.source_url)

        if content:
            await update_candidate_status(session, cid, CandidateStatus.SCRAPED, content=content)
            logger.info(f"Successfully scraped candidate: {candidate_id} ({len(content)} chars)")

            if auto_promote:
                await apply_predicted_rating_if_available(session, candidate)
                promoted = await promote_candidate(session, cid)
                result = {
                    "status": "promoted" if promoted else "scraped",
                    "content_length": len(content),
                }
            else:
                result = {"status": "scraped", "content_length": len(content)}
        else:
            error_msg = "Failed to extract content from URL"
            await update_candidate_status(
                session, cid, CandidateStatus.SCRAPE_FAILED, error_message=error_msg
            )
            logger.warning(f"Failed to scrape candidate: {candidate_id}")
            result = {"status": "scrape_failed", "message": error_msg}
        break

    return result


@register_task(
    task_name="fact_check:enqueue_scrape_batch",
    component="import_pipeline",
    task_type="batch",
)
async def enqueue_scrape_batch(batch_size: int = 100) -> dict:
    """Enqueue scrape tasks for pending candidates.

    Finds candidates with status=pending and no content,
    then enqueues scrape tasks for each.

    Args:
        batch_size: Maximum number of candidates to enqueue.

    Returns:
        Dict with count of enqueued tasks.
    """
    enqueue_result: dict = {"enqueued": 0}

    async for session in get_db():
        result = await session.execute(
            select(FactCheckedItemCandidate.id)
            .where(FactCheckedItemCandidate.status == CandidateStatus.PENDING.value)
            .where(FactCheckedItemCandidate.content.is_(None))
            .limit(batch_size)
        )
        candidate_ids = [row[0] for row in result.fetchall()]

        if not candidate_ids:
            logger.info("No pending candidates to scrape")
            break

        for cid in candidate_ids:
            await scrape_candidate_content.kiq(str(cid))

        logger.info(f"Enqueued {len(candidate_ids)} scrape tasks")
        enqueue_result = {"enqueued": len(candidate_ids)}
        break

    return enqueue_result
