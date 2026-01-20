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
from urllib.parse import urlparse
from uuid import UUID

import trafilatura
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_service import (
    extract_high_confidence_rating,
)
from src.fact_checking.import_pipeline.promotion import promote_candidate
from src.tasks.broker import register_task

logger = logging.getLogger(__name__)

AUTO_PROMOTE_PREDICTION_THRESHOLD: float = 1.0

DEFAULT_BASE_DELAY = 1.0
DEFAULT_JITTER_MAX = 0.5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def extract_domain(url: str) -> str:
    """Extract normalized domain from a URL for rate limiting.

    Args:
        url: The URL to extract domain from.

    Returns:
        Normalized domain string (lowercase, www. prefix stripped).
        Returns 'unknown' if URL cannot be parsed.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or "unknown"
    except Exception:
        return "unknown"


def get_random_user_agent() -> str:
    """Get a random user agent from the rotation list."""
    return random.choice(USER_AGENTS)


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

    result: CursorResult = await session.execute(  # type: ignore[type-arg]
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


def scrape_url_content(url: str, user_agent: str | None = None) -> str | None:
    """Scrape and extract main content from a URL using Trafilatura.

    Trafilatura is designed for:
    - News article extraction
    - Clean main content extraction (no boilerplate)
    - Handling various HTML structures

    Args:
        url: The URL to scrape.
        user_agent: Optional custom user agent. If None, uses a random one from rotation.

    Returns:
        Extracted text content, or None if extraction failed.
    """
    try:
        if user_agent is None:
            user_agent = get_random_user_agent()

        config = trafilatura.settings.use_config()  # type: ignore[attr-defined]
        config.set("DEFAULT", "USER_AGENT", user_agent)

        downloaded = trafilatura.fetch_url(url, config=config)
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
) -> dict:
    """Fetch URL content with per-domain rate limiting.

    This task is rate-limited per domain to ensure politeness when scraping.
    After acquiring the semaphore (handled by middleware), it adds an explicit
    delay with jitter before making the request.

    Args:
        url: The URL to fetch content from.
        domain: The domain for rate limiting (used in rate_limit_name template).
        base_delay: Minimum delay in seconds between requests to same domain.

    Returns:
        Dict with 'content' key containing extracted text, or 'error' on failure.
    """
    jitter = random.uniform(0, DEFAULT_JITTER_MAX)
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


@register_task(
    task_name="fact_check:scrape_candidate",
    component="import_pipeline",
    task_type="scrape",
)
async def scrape_candidate_content(
    candidate_id: str,
    auto_promote: bool = True,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> dict:
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

        domain = extract_domain(candidate.source_url)
        fetch_task = await fetch_url_content.kiq(
            url=candidate.source_url,
            domain=domain,
            base_delay=base_delay,
        )
        fetch_result = await fetch_task.wait_result(timeout=120)

        content = fetch_result.return_value.get("content") if fetch_result.return_value else None

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
            error_msg = (
                fetch_result.return_value.get("error", "Failed to extract content from URL")
                if fetch_result.return_value
                else "Failed to extract content from URL"
            )
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
async def enqueue_scrape_batch(
    batch_size: int = 100,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> dict:
    """Enqueue scrape tasks for pending candidates.

    Finds candidates with status=pending and no content,
    then enqueues scrape tasks for each.

    Args:
        batch_size: Maximum number of candidates to enqueue.
        base_delay: Minimum delay in seconds between requests to same domain.

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
            await scrape_candidate_content.kiq(str(cid), base_delay=base_delay)

        logger.info(f"Enqueued {len(candidate_ids)} scrape tasks")
        enqueue_result = {"enqueued": len(candidate_ids)}
        break

    return enqueue_result
