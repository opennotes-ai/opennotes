"""Scrape cache backed by Supabase Postgres + Storage (TASK-1473.08).

The scrape cache persists the full Firecrawl `ScrapeResult` bundle so retried
or finalize-path jobs can resume without repaying the Firecrawl cost. Two
resources are coordinated per entry:

- A row in `vibecheck_scrapes` (keyed by normalized URL, 72h TTL) storing
  markdown + sanitized HTML + metadata.
- An object in the `vibecheck-screenshots` Supabase Storage bucket holding
  the PNG bytes. Only the storage key is stored in the row — never the
  short-lived Firecrawl CDN URL, and never a signed URL (which expires).
  Callers mint a fresh 15-minute signed URL via `signed_screenshot_url`.

HTML sanitation choice: regex rather than BeautifulSoup. The four targets
(`<script>`, `<style>`, `<link>`, HTML comments) all have a well-defined
syntactic shape that a small set of regex passes strips safely, and avoiding
a ~1MB parser dep for this one method keeps the cache module self-contained.
If the target set expands to attribute-level sanitation we should switch to
a real parser.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from supabase import Client

from src.cache.supabase_cache import normalize_url
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.monitoring import get_logger

logger = get_logger(__name__)

_TABLE_NAME = "vibecheck_scrapes"
_BUCKET_NAME = "vibecheck-screenshots"
_SIGNED_URL_TTL_SECONDS = 15 * 60

_SELECTED_COLUMNS = (
    "normalized_url, url, host, page_kind, page_title, markdown, html, "
    "screenshot_storage_key, scraped_at, expires_at"
)

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r"<link\b[^>]*/?>", re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _sanitize_html(html: str | None) -> str | None:
    if html is None:
        return None
    cleaned = _SCRIPT_RE.sub("", html)
    cleaned = _STYLE_RE.sub("", cleaned)
    cleaned = _LINK_RE.sub("", cleaned)
    return _COMMENT_RE.sub("", cleaned)


def _storage_key_for(url: str) -> str:
    """Deterministic-per-url prefix + uuid suffix.

    The sha256-of-url prefix makes per-URL storage buckets inspectable in the
    Supabase dashboard; the uuid4 suffix keeps re-scrapes from overwriting
    the previous capture so a stale signed URL in flight still resolves.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}-{uuid4().hex}.png"


class SupabaseScrapeCache:
    """72h-TTL cache for Firecrawl ScrapeResult bundles + screenshots."""

    def __init__(self, client: Client, ttl_hours: int = 72) -> None:
        self._client = client
        self._ttl_hours = ttl_hours

    async def get(self, url: str) -> ScrapeResult | None:
        norm = normalize_url(url)
        try:
            resp = (
                self._client.table(_TABLE_NAME)
                .select(_SELECTED_COLUMNS)
                .eq("normalized_url", norm)
                .gte("expires_at", "now()")
                .maybe_single()
                .execute()
            )
        except Exception as exc:
            logger.warning("scrape cache get failed for %s: %s", norm, exc)
            return None
        if not resp or not resp.data:
            return None
        data = resp.data
        if not isinstance(data, dict):
            return None
        return _row_to_scrape_result(data)

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
    ) -> ScrapeResult:
        norm = normalize_url(url)
        host = urlparse(norm).netloc

        storage_key = await self._upload_screenshot(
            url=norm, scrape=scrape, screenshot_bytes=screenshot_bytes
        )

        now = datetime.now(UTC)
        expires = now + timedelta(hours=self._ttl_hours)
        metadata = scrape.metadata or ScrapeMetadata()
        row = {
            "normalized_url": norm,
            "url": url,
            "host": host,
            "page_kind": "other",
            "page_title": metadata.title,
            "markdown": scrape.markdown,
            "html": _sanitize_html(scrape.html),
            "screenshot_storage_key": storage_key,
            "scraped_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        try:
            self._client.table(_TABLE_NAME).upsert(
                row, on_conflict="normalized_url"
            ).execute()
        except Exception as exc:
            logger.warning("scrape cache put failed for %s: %s", norm, exc)
        return scrape

    async def signed_screenshot_url(self, scrape: ScrapeResult) -> str | None:
        """Mint a fresh 15-minute signed URL for a cached screenshot.

        The stored row carries the storage key; we look it up again via the
        source_url on the ScrapeResult metadata. Returns None when no key is
        persisted for this scrape, or when signing fails.
        """
        storage_key = await self._resolve_storage_key(scrape)
        if storage_key is None:
            return None
        try:
            resp = self._client.storage.from_(_BUCKET_NAME).create_signed_url(
                storage_key, _SIGNED_URL_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("signed url creation failed for %s: %s", storage_key, exc)
            return None
        if not isinstance(resp, dict):
            return None
        signed = resp.get("signedURL") or resp.get("signed_url")
        if not isinstance(signed, str):
            return None
        return signed

    async def _resolve_storage_key(self, scrape: ScrapeResult) -> str | None:
        source_url = scrape.metadata.source_url if scrape.metadata else None
        if not source_url:
            return None
        norm = normalize_url(source_url)
        try:
            resp = (
                self._client.table(_TABLE_NAME)
                .select("screenshot_storage_key")
                .eq("normalized_url", norm)
                .maybe_single()
                .execute()
            )
        except Exception as exc:
            logger.warning("scrape cache storage-key lookup failed for %s: %s", norm, exc)
            return None
        if not resp or not resp.data or not isinstance(resp.data, dict):
            return None
        key = resp.data.get("screenshot_storage_key")
        return key if isinstance(key, str) else None

    async def _upload_screenshot(
        self,
        *,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None,
    ) -> str | None:
        bytes_to_upload = screenshot_bytes
        if bytes_to_upload is None and scrape.screenshot:
            bytes_to_upload = await _fetch_bytes(scrape.screenshot)
        if not bytes_to_upload:
            return None
        storage_key = _storage_key_for(url)
        try:
            self._client.storage.from_(_BUCKET_NAME).upload(
                storage_key,
                bytes_to_upload,
                {"content-type": "image/png", "upsert": "true"},
            )
        except Exception as exc:
            logger.warning("screenshot upload failed for %s: %s", url, exc)
            return None
        return storage_key


async def _fetch_bytes(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            logger.warning(
                "screenshot cdn fetch failed for %s: status=%s", url, response.status_code
            )
            return None
        return response.content
    except Exception as exc:
        logger.warning("screenshot cdn fetch raised for %s: %s", url, exc)
        return None


def _row_to_scrape_result(row: dict[str, Any]) -> ScrapeResult:
    metadata = ScrapeMetadata(
        title=row.get("page_title"),
        sourceURL=row.get("url"),
    )
    return ScrapeResult(
        markdown=row.get("markdown"),
        html=row.get("html"),
        screenshot=None,
        metadata=metadata,
    )
