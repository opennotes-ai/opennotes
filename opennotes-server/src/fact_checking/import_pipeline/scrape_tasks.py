"""TaskIQ task for scraping candidate article content.

Uses Trafilatura for robust web content extraction with:
- Automatic fallback mechanisms
- HTML to clean text extraction
- Language detection
- Comment filtering
- Per-domain rate limiting for politeness
- User agent rotation for believable requests
"""

import asyncio
import logging
import random
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import AsyncTaskiqTask, TaskiqResultTimeoutError

from src.database import get_db
from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_service import (
    extract_high_confidence_rating,
)
from src.fact_checking.import_pipeline.promotion import promote_candidate
from src.shared.content_extraction import (
    DEFAULT_BASE_DELAY,
    DEFAULT_JITTER_RATIO,
    DEFAULT_SCRAPE_TIMEOUT,
    USER_AGENTS,
    extract_domain,
    get_random_user_agent,
    scrape_url_content,
)
from src.tasks.broker import register_task

logger = logging.getLogger(__name__)

AUTO_PROMOTE_PREDICTION_THRESHOLD: float = 1.0

__all__ = [
    "DEFAULT_BASE_DELAY",
    "DEFAULT_JITTER_RATIO",
    "DEFAULT_SCRAPE_TIMEOUT",
    "USER_AGENTS",
    "extract_domain",
    "get_random_user_agent",
    "scrape_url_content",
]


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
    values: dict[str, Any] = {"status": status.value, "updated_at": func.now()}
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

    result = await session.execute(
        update(FactCheckedItemCandidate)
        .where(FactCheckedItemCandidate.id == candidate.id)
        .where(FactCheckedItemCandidate.rating.is_(None))
        .values(rating=rating, updated_at=func.now())
    )
    await session.commit()

    if result.rowcount == 0:  # pyright: ignore[reportAttributeAccessIssue]
        logger.debug(
            f"Skipped auto-applying rating for candidate {candidate.id}: "
            "rating already set by another process"
        )
        return None

    logger.info(
        f"Auto-applied rating '{rating}' from predicted_ratings for candidate {candidate.id}"
    )
    return rating


@register_task(
    task_name="fact_check:fetch_url_content",
    component="import_pipeline",
    task_type="scrape",
    rate_limit_name="scrape:domain:{domain}",
    rate_limit_capacity="1",
)
async def fetch_url_content(
    url: str,
    domain: str,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> dict[str, Any]:
    """Fetch URL content with per-domain rate limiting.

    This task is rate-limited per domain to ensure politeness when scraping.
    After acquiring the semaphore (handled by middleware), it adds an explicit
    delay with jitter before making the request.

    Args:
        url: The URL to fetch content from.
        domain: The domain for rate limiting (used in rate_limit_name template).
        base_delay: Minimum delay in seconds between requests to same domain.
            Must be non-negative (negative values will be clamped to 0).

    Returns:
        Dict with 'content' key containing extracted text, or 'error' on failure.
    """
    if base_delay < 0:
        logger.warning(
            "Negative base_delay provided, clamping to 0",
            extra={"url": url, "domain": domain, "original_base_delay": base_delay},
        )
        base_delay = 0.0

    jitter = random.uniform(0, base_delay * DEFAULT_JITTER_RATIO)
    total_delay = base_delay + jitter

    logger.debug(
        "Applying politeness delay before fetch",
        extra={
            "url": url,
            "domain": domain,
            "base_delay": base_delay,
            "jitter": jitter,
            "total_delay": total_delay,
        },
    )
    await asyncio.sleep(total_delay)

    user_agent = get_random_user_agent()
    content = await asyncio.to_thread(scrape_url_content, url, user_agent)

    if content:
        logger.info(
            "Successfully fetched URL content",
            extra={
                "url": url,
                "domain": domain,
                "content_length": len(content),
            },
        )
        return {"content": content}

    logger.warning(
        "Failed to fetch URL content",
        extra={"url": url, "domain": domain},
    )
    return {"error": "Failed to extract content from URL"}


async def _mark_scrape_failed(cid: UUID, error_message: str) -> dict[str, Any]:
    """Update candidate status to SCRAPE_FAILED and return error result."""
    async for session in get_db():
        await update_candidate_status(
            session, cid, CandidateStatus.SCRAPE_FAILED, error_message=error_message
        )
        break
    return {"status": "scrape_failed", "message": error_message}


async def _process_scrape_result(
    cid: UUID, candidate_id: str, fetch_result: Any, auto_promote: bool
) -> dict[str, Any]:
    """Process fetch result and update candidate accordingly."""
    content = fetch_result.return_value.get("content") if fetch_result.return_value else None

    async for session in get_db():
        if content:
            await update_candidate_status(session, cid, CandidateStatus.SCRAPED, content=content)
            logger.info(f"Successfully scraped candidate: {candidate_id} ({len(content)} chars)")

            if auto_promote:
                promoted = await promote_candidate(session, cid)
                return {
                    "status": "promoted" if promoted else "scraped",
                    "content_length": len(content),
                }
            return {"status": "scraped", "content_length": len(content)}

        error_msg = (
            fetch_result.return_value.get("error", "Failed to extract content from URL")
            if fetch_result.return_value
            else "Failed to extract content from URL"
        )
        await update_candidate_status(
            session, cid, CandidateStatus.SCRAPE_FAILED, error_message=error_msg
        )
        logger.warning(f"Failed to scrape candidate: {candidate_id}")
        return {"status": "scrape_failed", "message": error_msg}

    return {"status": "error", "message": "Failed to process scrape result"}


async def _validate_and_dispatch_scrape(
    cid: UUID, candidate_id: str, base_delay: float, auto_promote: bool
) -> tuple[dict[str, Any] | None, AsyncTaskiqTask[dict[str, Any]] | None, str | None]:
    """Validate candidate and dispatch fetch task if needed.

    Returns:
        (early_return, fetch_task, source_url) - early_return is result dict if
        we should return early, otherwise None.
    """
    async for session in get_db():
        candidate = await get_candidate(session, cid)

        if not candidate:
            logger.error(f"Candidate not found: {candidate_id}")
            return {"status": "error", "message": "Candidate not found"}, None, None

        if candidate.status == CandidateStatus.PROMOTED.value:
            logger.info(f"Candidate already promoted: {candidate_id}")
            return {"status": "skipped", "message": "Already promoted"}, None, None

        if candidate.content:
            logger.info(f"Candidate already has content: {candidate_id}")
            if auto_promote:
                promoted = await promote_candidate(session, cid)
                return {"status": "promoted" if promoted else "promotion_failed"}, None, None
            return {"status": "skipped", "message": "Already scraped"}, None, None

        await update_candidate_status(session, cid, CandidateStatus.SCRAPING)
        source_url = candidate.source_url

        domain = extract_domain(source_url)
        fetch_task = await fetch_url_content.kiq(
            url=source_url, domain=domain, base_delay=base_delay
        )
        return None, fetch_task, source_url

    return {"status": "error", "message": "No database session available"}, None, None


@register_task(
    task_name="fact_check:scrape_candidate",
    component="import_pipeline",
    task_type="scrape",
)
async def scrape_candidate_content(
    candidate_id: str,
    auto_promote: bool = True,
    base_delay: float = DEFAULT_BASE_DELAY,
    scrape_timeout: int = DEFAULT_SCRAPE_TIMEOUT,
) -> dict[str, Any]:
    """Scrape article content for a candidate and optionally promote.

    This task:
    1. Fetches the candidate from the database
    2. Sets status to SCRAPING
    3. Dispatches to fetch_url_content task (rate-limited per domain)
    4. Updates candidate with content or error
    5. Optionally promotes to fact_check_items if successful

    Args:
        candidate_id: UUID of the candidate to scrape.
        auto_promote: If True, automatically promote after successful scrape.
        base_delay: Minimum delay in seconds between requests to same domain.
        scrape_timeout: Timeout in seconds for waiting on fetch task result.
            Reasonable range is 30-300 seconds.

    Returns:
        Dict with status and any relevant details.
    """
    cid = UUID(candidate_id)

    early_return, fetch_task, source_url = await _validate_and_dispatch_scrape(
        cid, candidate_id, base_delay, auto_promote
    )
    if early_return is not None:
        return early_return

    assert fetch_task is not None, "fetch_task must be set when early_return is None"

    try:
        fetch_result = await fetch_task.wait_result(timeout=scrape_timeout)
    except TaskiqResultTimeoutError:
        msg = f"Fetch task timed out after {scrape_timeout}s"
        logger.error(msg, extra={"candidate_id": candidate_id, "url": source_url})
        return await _mark_scrape_failed(cid, msg)
    except Exception as e:
        msg = f"Unexpected error: {str(e)[:200]}"
        logger.exception(
            f"Unexpected error waiting for fetch task: {e}",
            extra={"candidate_id": candidate_id, "url": source_url},
        )
        return await _mark_scrape_failed(cid, msg)

    if fetch_result is None:
        logger.error(
            "Fetch result is None (task may have failed)",
            extra={"candidate_id": candidate_id, "url": source_url},
        )
        return await _mark_scrape_failed(cid, "Fetch task returned no result")

    return await _process_scrape_result(cid, candidate_id, fetch_result, auto_promote)


@register_task(
    task_name="fact_check:enqueue_scrape_batch",
    component="import_pipeline",
    task_type="batch",
)
async def enqueue_scrape_batch(
    batch_size: int = 100,
    base_delay: float = DEFAULT_BASE_DELAY,
    scrape_timeout: int = DEFAULT_SCRAPE_TIMEOUT,
) -> dict[str, Any]:
    """Enqueue scrape tasks for pending candidates.

    Finds candidates with status=pending and no content,
    then enqueues scrape tasks for each.

    Args:
        batch_size: Maximum number of candidates to enqueue.
        base_delay: Minimum delay in seconds between requests to same domain.
        scrape_timeout: Timeout in seconds for each scrape task.

    Returns:
        Dict with count of enqueued tasks.
    """
    enqueue_result: dict[str, Any] = {"enqueued": 0}

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
            await scrape_candidate_content.kiq(
                str(cid), base_delay=base_delay, scrape_timeout=scrape_timeout
            )

        logger.info(f"Enqueued {len(candidate_ids)} scrape tasks")
        enqueue_result = {"enqueued": len(candidate_ids)}
        break

    return enqueue_result
