"""PDF extraction path for uploaded Vibecheck sources."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import FirecrawlClient, ScrapeMetadata
from src.jobs.pdf_storage import get_pdf_upload_store
from src.jobs.scrape_quality import ScrapeQuality, classify_scrape
from src.monitoring import get_logger
from src.utils.html_sanitize import strip_for_llm
from src.utterances.errors import (
    TransientExtractionError,
    ZeroUtterancesError,
    classify_firecrawl_error,
)
from src.utterances.extractor import extract_utterances
from src.utterances.schema import UtterancesPayload

logger = get_logger(__name__)

_STORE_PDF_ARCHIVE_SQL = """
INSERT INTO vibecheck_pdf_archives (job_id, html, expires_at)
VALUES ($1, $2, now() + INTERVAL '7 days')
ON CONFLICT (job_id) DO UPDATE
SET html = EXCLUDED.html,
    expires_at = EXCLUDED.expires_at
"""

_BLOCK_HTML_RE = re.compile(
    r"<\s*(article|main|section|p|div|li|h[1-6]|blockquote|table)\b",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class PDFExtractionError(Exception):
    """Raised when an uploaded PDF cannot produce usable analysis input."""


def _clean_pdf_html(html: str | None) -> str:
    cleaned = strip_for_llm(html or "") or ""
    return cleaned.strip()


def _has_block_html(html: str) -> bool:
    return bool(_BLOCK_HTML_RE.search(html))


def _html_text_fallback(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", text).strip()


async def _store_pdf_archive(pool: Any, job_id: UUID, html: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_STORE_PDF_ARCHIVE_SQL, job_id, html)


async def pdf_extract_step(
    pool: Any,
    job_id: UUID,
    gcs_key: str,
    *,
    settings: Settings,
    client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
) -> UtterancesPayload:
    """Scrape an uploaded PDF through a signed GCS GET URL and extract utterances.

    The signed URL is only used as transient Firecrawl input. The archive table
    stores sanitized HTML keyed by job_id, and the extractor receives a
    CachedScrape whose source_url is the durable GCS key, not the signed URL.
    """
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        raise PDFExtractionError("PDF upload bucket is not configured")

    # TASK-1498.27: Mint the signed read URL immediately before the Firecrawl
    # call (not at the start of the step) and use a 1-hour TTL. Firecrawl
    # scrapes can be queued for tens of minutes; the previous 15-minute URL
    # was racing scrape latency and expiring before fetch.
    signed_url = get_pdf_upload_store(
        settings.VIBECHECK_PDF_UPLOAD_BUCKET
    ).signed_read_url(gcs_key, ttl_seconds=3600)
    if not signed_url:
        raise PDFExtractionError("could not sign PDF read URL")

    try:
        scrape = await client.scrape(
            signed_url,
            formats=["html", "markdown"],
            only_main_content=True,
        )
    except Exception as exc:
        transient = classify_firecrawl_error(exc)
        if transient is not None:
            raise transient from exc
        raise PDFExtractionError(f"Firecrawl PDF scrape failed: {exc}") from exc

    html = _clean_pdf_html(scrape.html or scrape.raw_html)
    if not html or not _has_block_html(html):
        raise PDFExtractionError("Firecrawl PDF scrape returned no usable HTML")

    archive_probe = CachedScrape(
        html=html,
        markdown=scrape.markdown or _html_text_fallback(html),
        raw_html=html,
        metadata=ScrapeMetadata(source_url=gcs_key),
    )
    if classify_scrape(archive_probe) is not ScrapeQuality.OK:
        raise PDFExtractionError("Firecrawl PDF scrape returned unusable content")
    if not archive_probe.markdown or not archive_probe.markdown.strip():
        raise PDFExtractionError("Firecrawl PDF scrape returned no text")

    # TASK-1498.16: populate the scrape cache BEFORE writing the archive row
    # so that a transient Postgres failure during the archive write (which we
    # raise as TransientExtractionError below to trigger Cloud Tasks redelivery)
    # does not re-charge Firecrawl on retry — `extract_utterances` will hit the
    # cache for `gcs_key` instead of re-scraping.
    # TASK-1498.31: If the cache put fails we MUST NOT proceed to the archive
    # write. Swallowing the error breaks the TASK-1498.16 invariant that the
    # cache is populated before the archive: a subsequent transient archive
    # failure would then re-charge Firecrawl on retry. Surfacing as
    # TransientExtractionError causes Cloud Tasks to redeliver, and the retry
    # will re-scrape Firecrawl fresh (worst case: one extra Firecrawl call,
    # but integrity is preserved).
    try:
        await scrape_cache.put(gcs_key, archive_probe)
    except Exception as exc:
        logger.warning(
            "pdf scrape cache put failed gcs_key=%s job_id=%s: %s",
            gcs_key,
            job_id,
            exc,
        )
        raise TransientExtractionError(
            provider="supabase",
            status_code=None,
            status="ERROR",
            fallback_message=(
                f"PDF scrape cache put failed; retry will re-scrape: {exc}"
            ),
        ) from exc

    try:
        await _store_pdf_archive(pool, job_id, html)
    except Exception as exc:
        raise TransientExtractionError(
            provider="postgres",
            status_code=None,
            status="ERROR",
            fallback_message=f"PDF archive write failed: {exc}",
        ) from exc

    try:
        return await extract_utterances(
            gcs_key,
            client,
            scrape_cache,
            settings=settings,
            scrape=archive_probe,
        )
    except TransientExtractionError:
        raise
    except ZeroUtterancesError as exc:
        raise PDFExtractionError(
            f"PDF text extraction produced zero utterances: {exc}"
        ) from exc
    except Exception as exc:
        raise PDFExtractionError(f"PDF utterance extraction failed: {exc}") from exc
