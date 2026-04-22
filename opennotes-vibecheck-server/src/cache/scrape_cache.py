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
a real parser. (See TASK-1473 follow-up filed for hardening beyond this
regex set — malformed/nested/unclosed tags are out of scope for the first
pass.)

Race / orphan notes:

- `signed_screenshot_url(cached)` signs by the `storage_key` that was
  captured when the `ScrapeResult` was fetched from the cache, NOT by
  re-querying the row. If two concurrent `put()` calls land for the same
  normalized URL, the later upsert replaces the row's `screenshot_storage_key`
  — re-lookup by `source_url` would then sign the *newer* key against the
  *older* cached result (TOCTOU). Snapshotting the key removes the race.
- When a `put()`'s DB upsert fails after the Storage upload already
  succeeded, the just-uploaded blob would orphan in the bucket. We attempt a
  best-effort `.remove([key])` on the same path to shrink the orphan window;
  the pg_cron sweeper is the long-term backstop if the cleanup itself fails.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import ConfigDict, Field
from supabase import Client

from src.cache.supabase_cache import normalize_url
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.monitoring import get_logger
from src.utils.url_security import validate_public_http_url

logger = get_logger(__name__)


def canonical_cache_key(raw_url: str) -> str:
    """Return the canonical dedup/cache key for a raw user URL.

    Funnels `validate_public_http_url` → `normalize_url`. Two normalization
    passes run, in order, with distinct jobs (spec + codex W3 P2-7):

    1. `validate_public_http_url` enforces SSRF/scheme/host rules and returns
       the **"public host + path"** form: scheme lowercased, host IDNA-encoded
       and lowercased, trailing dot dropped from host, fragment removed, path
       and query preserved verbatim.

    2. `normalize_url` then collapses the **"dedup key"** form: strips common
       tracking params (utm_*, fbclid, gclid, mc_*) and a single trailing
       slash off the path. Cache keys and dedup keys are keyed off this
       output so `?utm_source=foo` and the bare URL share a row.

    Callers that compute a DB key (advisory lock, `vibecheck_jobs.normalized_url`,
    `vibecheck_scrapes.normalized_url`, `vibecheck_analyses.url`) should use
    this helper instead of composing the two passes by hand — mixing the two
    forms is the path to dedup drift. `InvalidURL` propagates unchanged for
    callers that want to return a 400 to the client.
    """
    public = validate_public_http_url(raw_url)
    return normalize_url(public)

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


class CachedScrape(ScrapeResult):
    """A `ScrapeResult` augmented with the Supabase storage_key captured at
    cache write (or cache read) time.

    Subclasses `ScrapeResult` so existing callers that access `.markdown`,
    `.html`, `.metadata`, etc. continue to work unchanged. The attached
    `storage_key` lets `signed_screenshot_url` mint a URL for the exact
    object this scrape references, immune to a concurrent `put()` that may
    have replaced the row's stored key in the meantime.
    """

    storage_key: str | None = Field(default=None)
    model_config = ConfigDict(populate_by_name=True)


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

    async def get(self, url: str) -> CachedScrape | None:
        norm = normalize_url(url)
        # TTL filter: strictly greater-than, evaluated server-side against an
        # ISO timestamp we compute now. The prior `.gte("now()")` passed the
        # literal string "now()" as a comparison value, which postgrest sent
        # as a string literal (never as SQL) so every row trivially "matched"
        # the filter. Fake Supabase client in tests masked it.
        now_iso = datetime.now(UTC).isoformat()
        try:
            resp = (
                self._client.table(_TABLE_NAME)
                .select(_SELECTED_COLUMNS)
                .eq("normalized_url", norm)
                .gt("expires_at", now_iso)
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
        return _row_to_cached_scrape(data)

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
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
            # Storage upload succeeded but DB upsert failed → best-effort
            # cleanup so the blob doesn't orphan. pg_cron sweeps anything
            # this misses.
            if storage_key is not None:
                self._cleanup_orphan_blob(storage_key)
            storage_key = None
        return CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=scrape.raw_html,
            screenshot=scrape.screenshot,
            links=scrape.links,
            metadata=scrape.metadata,
            warning=scrape.warning,
            storage_key=storage_key,
        )

    async def evict(self, url: str) -> None:
        """Discard the cached scrape row + screenshot blob for a URL.

        Used by the orchestrator's post-scrape redirect revalidation
        (TASK-1473.12, codex P1-3): when Firecrawl follows a 3xx into a
        private host we must not retain the response — a later retry that
        hits the same normalized_url should re-fetch, not replay the
        poisoned cache entry.

        Best-effort: either leg (row delete or blob remove) may fail; we
        log and continue so a partial cleanup still progresses the caller
        toward the TerminalError path. pg_cron sweeps anything we miss.
        """
        norm = normalize_url(url)
        storage_key: str | None = None
        try:
            resp = (
                self._client.table(_TABLE_NAME)
                .select("screenshot_storage_key")
                .eq("normalized_url", norm)
                .maybe_single()
                .execute()
            )
            if resp and isinstance(resp.data, dict):
                key = resp.data.get("screenshot_storage_key")
                storage_key = key if isinstance(key, str) else None
        except Exception as exc:
            logger.warning("scrape cache evict lookup failed for %s: %s", norm, exc)

        try:
            self._client.table(_TABLE_NAME).delete().eq(
                "normalized_url", norm
            ).execute()
        except Exception as exc:
            logger.warning("scrape cache evict delete failed for %s: %s", norm, exc)

        if storage_key:
            self._cleanup_orphan_blob(storage_key)

    async def signed_screenshot_url(self, scrape: ScrapeResult) -> str | None:
        """Mint a fresh 15-minute signed URL for a cached screenshot.

        Uses the storage_key snapshotted on the passed-in `CachedScrape`
        (attached at `get()` / `put()` time). When given a bare `ScrapeResult`
        — i.e. not from this cache — there is no key to sign against, so we
        return None rather than racing a DB lookup against a concurrent put.
        """
        storage_key = getattr(scrape, "storage_key", None)
        if not isinstance(storage_key, str) or not storage_key:
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

    def _cleanup_orphan_blob(self, storage_key: str) -> None:
        """Remove a just-uploaded blob when its corresponding DB upsert fails.

        Best-effort: we log and swallow Storage errors because the pg_cron
        sweeper catches whatever this misses, and raising here would hide the
        original upsert failure from the caller's retry logic.
        """
        try:
            self._client.storage.from_(_BUCKET_NAME).remove([storage_key])
        except Exception as exc:
            logger.warning(
                "orphan blob cleanup failed for %s: %s", storage_key, exc
            )

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


def _row_to_cached_scrape(row: dict[str, Any]) -> CachedScrape:
    metadata = ScrapeMetadata(
        title=row.get("page_title"),
        source_url=row.get("url"),
    )
    storage_key = row.get("screenshot_storage_key")
    return CachedScrape(
        markdown=row.get("markdown"),
        html=row.get("html"),
        screenshot=None,
        metadata=metadata,
        storage_key=storage_key if isinstance(storage_key, str) else None,
    )
