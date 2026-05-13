"""Scrape cache backed by Supabase Postgres + GCS (TASK-1473.08, GCS migration 2026-04-23).

The scrape cache persists the full Firecrawl `ScrapeResult` bundle so retried
or finalize-path jobs can resume without repaying the Firecrawl cost. Two
resources are coordinated per entry:

- A row in `vibecheck_scrapes` (keyed by normalized URL, 72h TTL) storing
  markdown + sanitized HTML + metadata.
- An object in the configured GCS bucket holding the PNG bytes (see
  `screenshot_store.py`). Only the storage key is stored in the row —
  never the short-lived Firecrawl CDN URL, and never a signed URL (which
  expires). Callers mint a fresh 15-minute signed URL via
  `signed_screenshot_url`.

HTML sanitation choice: cache writes use the shared BeautifulSoup sanitizer
for display archives. It removes scripts and comments while preserving style
and link tags so the archived iframe keeps CSS-defined layout.

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
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import ConfigDict, Field
from supabase import Client

from src.cache.screenshot_store import ScreenshotStore
from src.cache.supabase_cache import normalize_url
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.monitoring import get_logger
from src.utils.html_sanitize import strip_for_display
from src.utils.url_security import validate_public_http_url

logger = get_logger(__name__)

# TASK-1488.01: ladder tier discriminator. `scrape` = Tier 1 cheap
# Firecrawl /scrape; `interact` = Tier 2 post-fallback Firecrawl /interact.
ScrapeTier = Literal["scrape", "interact", "browser_html"]


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
_UPSERT_IF_NOT_EVICTED_RPC = "vibecheck_upsert_scrape_if_not_evicted"
_UPSERT_EVICT_TOMBSTONE_RPC = "vibecheck_upsert_scrape_evict_tombstone"
_SIGNED_URL_TTL_SECONDS = 15 * 60

# TASK-1488.18: small clock-skew tolerance when comparing the put's
# anchor timestamp (Python clock) against the row's `evicted_at`
# (Python clock at evict() time, but on a possibly-different host).
# A 1-second margin absorbs typical NTP drift between worker pods.
_EVICT_FENCE_CLOCK_SKEW_SECONDS = 1

_SELECTED_COLUMNS = (
    "normalized_url, tier, url, final_url, host, page_kind, page_title, "
    "markdown, html, raw_html, screenshot_storage_key, scraped_at, expires_at, "
    "evicted_at"
)


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
    return strip_for_display(html)


def screenshot_storage_key_for(url: str) -> str:
    """Deterministic-per-url prefix + uuid suffix.

    The sha256-of-url prefix groups per-URL screenshots together in the
    bucket listing; the uuid4 suffix keeps re-scrapes from overwriting
    the previous capture so a stale signed URL in flight still resolves.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}-{uuid4().hex}.png"


class SupabaseScrapeCache:
    """72h-TTL cache for Firecrawl ScrapeResult bundles + screenshots.

    Hybrid: Supabase Postgres holds the row, an external `ScreenshotStore`
    (GCS in production) holds the PNG bytes. The two are coordinated by
    `screenshot_storage_key` on the row.
    """

    def __init__(
        self,
        client: Client,
        screenshot_store: ScreenshotStore,
        ttl_hours: int = 72,
    ) -> None:
        self._client = client
        self._store = screenshot_store
        self._ttl_hours = ttl_hours

    async def get(
        self, url: str, *, tier: ScrapeTier = "scrape"
    ) -> CachedScrape | None:
        """Look up a fresh cached scrape for `url` under the given tier.

        TASK-1488.01: tier separates Tier 1 (`scrape`) from Tier 2
        (`interact`) so a cheap-tier failure-flagged row cannot short-
        circuit a retry that would have escalated to the interact tier
        (and vice versa). UNIQUE(normalized_url, tier) is enforced at
        the schema level.
        """
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
                .eq("tier", tier)
                .gt("expires_at", now_iso)
                .maybe_single()
                .execute()
            )
        except Exception as exc:
            logger.warning(
                "scrape cache get failed for %s (tier=%s): %s", norm, tier, exc
            )
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
        *,
        tier: ScrapeTier = "scrape",
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        """Persist `scrape` under `(normalized_url, tier)`.

        TASK-1488.01: each tier has its own row; on_conflict targets the
        composite UNIQUE so re-puts within a tier still upsert in place.

        TASK-1488.18:
        - `final_url` persists Firecrawl's resolved post-redirect URL
          (`scrape.metadata.source_url` if present, else the input url)
          so cache reads rehydrate `metadata.source_url` to the resolved
          host on a replay. Without this, `_revalidate_final_url` on a
          poisoned redirect retry sees the input URL as both the lookup
          key and the resolved URL and silently skips the SSRF re-check.
        - Evict fence: an anchor timestamp `put_started_at` is captured
          *before* the screenshot upload (which may take up to httpx's
          60s timeout). After upload, a cheap preflight reads the row's
          `evicted_at`; the actual DB write then runs through a Postgres
          RPC that keeps the same tombstone predicate inside the
          `ON CONFLICT DO UPDATE`. That closes the race where an evict
          lands after the preflight read but before the upsert.
        """
        norm = normalize_url(url)
        host = urlparse(norm).netloc

        # Capture the fence anchor BEFORE the upload so a tombstone
        # written by a concurrent evict() during the upload window is
        # always recognized, regardless of how long the upload took.
        put_started_at = datetime.now(UTC)

        storage_key = await self._upload_screenshot(
            url=norm, scrape=scrape, screenshot_bytes=screenshot_bytes
        )

        if self._evict_fence_active(norm, tier, since=put_started_at):
            logger.warning(
                "scrape cache put aborted by evict fence for %s (tier=%s)",
                norm,
                tier,
            )
            if storage_key is not None:
                self._cleanup_orphan_blob(storage_key)
            return CachedScrape(
                markdown=scrape.markdown,
                html=scrape.html,
                raw_html=scrape.raw_html,
                screenshot=scrape.screenshot,
                links=scrape.links,
                metadata=scrape.metadata,
                warning=scrape.warning,
                storage_key=None,
            )

        now = datetime.now(UTC)
        expires = now + timedelta(hours=self._ttl_hours)
        metadata = scrape.metadata or ScrapeMetadata()
        final_url = metadata.source_url or url
        row = {
            "normalized_url": norm,
            "tier": tier,
            "url": url,
            "final_url": final_url,
            "host": host,
            "page_kind": "other",
            "page_title": metadata.title,
            "markdown": scrape.markdown,
            "html": _sanitize_html(scrape.html),
            "raw_html": scrape.raw_html,
            "screenshot_storage_key": storage_key,
            "scraped_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            # Clear any tombstone marker on a successful put so future
            # fence checks don't false-positive against this fresh row.
            "evicted_at": None,
        }
        try:
            wrote_row = self._upsert_if_not_evicted(row, put_started_at)
        except Exception as exc:
            logger.warning(
                "scrape cache put failed for %s (tier=%s): %s", norm, tier, exc
            )
            # Storage upload succeeded but DB upsert failed → best-effort
            # cleanup so the blob doesn't orphan. pg_cron sweeps anything
            # this misses.
            if storage_key is not None:
                self._cleanup_orphan_blob(storage_key)
            storage_key = None
        else:
            if not wrote_row:
                logger.warning(
                    "scrape cache put skipped by atomic evict fence for %s "
                    "(tier=%s)",
                    norm,
                    tier,
                )
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

    def _upsert_if_not_evicted(
        self, row: dict[str, Any], put_started_at: datetime
    ) -> bool:
        """Atomically write a scrape row unless a newer tombstone exists."""
        resp = (
            self._client.postgrest.rpc(
                _UPSERT_IF_NOT_EVICTED_RPC,
                {
                    "p_normalized_url": row["normalized_url"],
                    "p_tier": row["tier"],
                    "p_url": row["url"],
                    "p_final_url": row["final_url"],
                    "p_host": row["host"],
                    "p_page_kind": row["page_kind"],
                    "p_page_title": row["page_title"],
                    "p_markdown": row["markdown"],
                    "p_html": row["html"],
                    "p_raw_html": row["raw_html"],
                    "p_screenshot_storage_key": row["screenshot_storage_key"],
                    "p_scraped_at": row["scraped_at"],
                    "p_expires_at": row["expires_at"],
                    "p_put_started_at": put_started_at.isoformat(),
                    "p_clock_skew_seconds": str(_EVICT_FENCE_CLOCK_SKEW_SECONDS),
                },
            ).execute()
        )
        data = getattr(resp, "data", None)
        if isinstance(data, bool):
            return data
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], bool):
            return data[0]
        if isinstance(data, dict):
            value = data.get(_UPSERT_IF_NOT_EVICTED_RPC)
            if isinstance(value, bool):
                return value
        return False

    def _evict_fence_active(
        self, norm: str, tier: ScrapeTier, *, since: datetime
    ) -> bool:
        """Read `evicted_at` for `(norm, tier)` and return True iff the
        slot was tombstoned at-or-after `since` (the put's anchor).

        A small clock-skew tolerance subtracts
        `_EVICT_FENCE_CLOCK_SKEW_SECONDS` from the comparison so an
        evict that happened a sub-second before the put started is still
        recognized when worker pod clocks drift slightly (typical NTP
        skew under a second).

        Bypasses the TTL filter (`expires_at > now()`) used by `get()`
        because tombstones intentionally have an `expires_at` in the past
        — the TTL filter would hide them from this fence check.
        """
        try:
            resp = (
                self._client.table(_TABLE_NAME)
                .select("evicted_at")
                .eq("normalized_url", norm)
                .eq("tier", tier)
                .maybe_single()
                .execute()
            )
        except Exception as exc:
            logger.warning(
                "scrape cache evict-fence read failed for %s (tier=%s): %s",
                norm,
                tier,
                exc,
            )
            return False
        data = getattr(resp, "data", None) if resp is not None else None
        if not isinstance(data, dict):
            return False
        evicted_at_raw = data.get("evicted_at")
        if not isinstance(evicted_at_raw, str) or not evicted_at_raw:
            return False
        try:
            evicted_at = datetime.fromisoformat(evicted_at_raw)
        except ValueError:
            return False
        threshold = since - timedelta(seconds=_EVICT_FENCE_CLOCK_SKEW_SECONDS)
        return evicted_at >= threshold

    async def evict(self, url: str, *, tier: ScrapeTier | None = None) -> None:
        """Discard the cached scrape row(s) + screenshot blob(s) for a URL.

        TASK-1488.01: when `tier` is given, only that tier's row is dropped;
        when `tier` is None, every tier's row for the URL is removed. The
        redirect-revalidation path (orchestrator) needs the tier=None
        flush so a poisoned target can't survive on the other tier; the
        ladder retry path may want to drop just the failure-flagged
        Tier 1 row.

        TASK-1488.18: after the delete, write a tombstone row per affected
        tier with `evicted_at = now()` and `expires_at` in the past. The
        tombstone fences a concurrent `put()` that started before this
        evict but commits after — `put()`'s pre-upsert fence check reads
        `evicted_at` and aborts when a recent eviction is observed.
        Tombstones are filtered out of `get()` by the existing
        `expires_at > now()` predicate so callers never see them.

        Best-effort: any leg (lookup, delete, tombstone, blob remove) may
        fail; we log and continue so a partial cleanup still progresses
        the caller toward the TerminalError path. pg_cron sweeps anything
        we miss.
        """
        norm = normalize_url(url)
        storage_keys: list[str] = []
        try:
            select_query = (
                self._client.table(_TABLE_NAME)
                .select("screenshot_storage_key")
                .eq("normalized_url", norm)
            )
            if tier is not None:
                select_query = select_query.eq("tier", tier)
            resp = select_query.execute()
            data = getattr(resp, "data", None) if resp is not None else None
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        key = item.get("screenshot_storage_key")
                        if isinstance(key, str) and key:
                            storage_keys.append(key)
            elif isinstance(data, dict):
                key = data.get("screenshot_storage_key")
                if isinstance(key, str) and key:
                    storage_keys.append(key)
        except Exception as exc:
            logger.warning(
                "scrape cache evict lookup failed for %s (tier=%s): %s",
                norm,
                tier,
                exc,
            )

        try:
            delete_query = (
                self._client.table(_TABLE_NAME).delete().eq("normalized_url", norm)
            )
            if tier is not None:
                delete_query = delete_query.eq("tier", tier)
            delete_query.execute()
        except Exception as exc:
            logger.warning(
                "scrape cache evict delete failed for %s (tier=%s): %s",
                norm,
                tier,
                exc,
            )

        self._write_evict_tombstones(norm, tier)

        for key in storage_keys:
            self._cleanup_orphan_blob(key)

    def _write_evict_tombstones(
        self, norm: str, tier: ScrapeTier | None
    ) -> None:
        """Upsert tombstone rows for the evicted tier(s).

        A tombstone row holds `evicted_at = now()` and `expires_at` in
        the past, with NULL scrape data + NULL `screenshot_storage_key`.
        It serves only to be read by `put()`'s pre-upsert fence check;
        it is never returned from `get()` (the TTL filter excludes it).
        """
        now = datetime.now(UTC)
        expires_past = now - timedelta(hours=1)
        host = urlparse(norm).netloc
        tiers: tuple[ScrapeTier, ...] = (
            (tier,) if tier is not None else ("scrape", "interact")
        )
        for t in tiers:
            scraped_at = now.isoformat()
            expires_at = expires_past.isoformat()
            evicted_at = now.isoformat()
            try:
                self._client.postgrest.rpc(
                    _UPSERT_EVICT_TOMBSTONE_RPC,
                    {
                        "p_normalized_url": norm,
                        "p_tier": t,
                        "p_url": norm,
                        "p_host": host,
                        "p_scraped_at": scraped_at,
                        "p_expires_at": expires_at,
                        "p_evicted_at": evicted_at,
                    },
                ).execute()
            except Exception as exc:
                logger.warning(
                    "scrape cache evict tombstone write failed for %s "
                    "(tier=%s): %s",
                    norm,
                    t,
                    exc,
                )

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
        return self._store.signed_url(storage_key, ttl_seconds=_SIGNED_URL_TTL_SECONDS)

    def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        """Mint a 15-minute signed URL directly from a storage key.

        TASK-1485.03 helper: the recent-analyses query reads raw rows from
        vibecheck_scrapes and needs to sign by `screenshot_storage_key`
        without first hydrating a `CachedScrape`. Returns None for empty/None
        keys so the caller can drop unviewable cards.
        """
        if not isinstance(storage_key, str) or not storage_key:
            return None
        return self._store.signed_url(storage_key, ttl_seconds=_SIGNED_URL_TTL_SECONDS)

    def _cleanup_orphan_blob(self, storage_key: str) -> None:
        """Remove a just-uploaded blob when its corresponding DB upsert fails.

        Best-effort: store-level errors are logged inside `delete()` because
        the pg_cron sweeper catches whatever this misses, and raising here
        would hide the original upsert failure from the caller's retry logic.
        """
        self._store.delete(storage_key)

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
        storage_key = screenshot_storage_key_for(url)
        if not self._store.upload(storage_key, bytes_to_upload, content_type="image/png"):
            return None
        return storage_key


async def _fetch_bytes(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
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
    # TASK-1488.18: rehydrate metadata.source_url from Firecrawl's resolved
    # post-redirect URL when persisted, falling back to the input url for
    # legacy rows that pre-date the final_url column. Without this,
    # `_revalidate_final_url` on a poisoned cache replay sees the input
    # URL as both lookup key and resolved URL and silently bypasses the
    # SSRF re-check.
    final_url_raw = row.get("final_url")
    source_url = (
        final_url_raw
        if isinstance(final_url_raw, str) and final_url_raw
        else row.get("url")
    )
    metadata = ScrapeMetadata(
        title=row.get("page_title"),
        source_url=source_url,
    )
    storage_key = row.get("screenshot_storage_key")
    raw_html = row.get("raw_html")
    return CachedScrape(
        markdown=row.get("markdown"),
        html=row.get("html"),
        raw_html=raw_html if isinstance(raw_html, str) else None,
        screenshot=None,
        metadata=metadata,
        storage_key=storage_key if isinstance(storage_key, str) else None,
    )
