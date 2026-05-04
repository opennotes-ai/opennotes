"""PDF extraction path for uploaded Vibecheck sources."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import FirecrawlClient, ScrapeMetadata
from src.jobs.pdf_storage import PdfUploadStore
from src.jobs.scrape_quality import ScrapeQuality, classify_scrape
from src.monitoring import get_logger
from src.utils.html_sanitize import strip_noise
from src.utterances.errors import (
    TransientExtractionError,
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
    created_at = now(),
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
    cleaned = strip_noise(html or "")
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

    signed_url = PdfUploadStore(settings.VIBECHECK_PDF_UPLOAD_BUCKET).signed_read_url(
        gcs_key
    )
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

    try:
        await _store_pdf_archive(pool, job_id, html)
    except Exception as exc:
        raise PDFExtractionError(f"PDF archive write failed: {exc}") from exc

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
    except Exception as exc:
        raise PDFExtractionError(f"PDF utterance extraction failed: {exc}") from exc
