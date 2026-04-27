"""Unit tests for SupabaseScrapeCache (TASK-1473.08).

The Supabase client is faked in-process. After the GCS migration
(2026-04-23) the screenshot leg is a separate `ScreenshotStore` interface;
the in-memory test double is `InMemoryScreenshotStore`. These tests
exercise the cache's round-trip behavior, HTML sanitation, and signed-URL
surface against a deterministic fake, never the live Postgres or GCS APIs.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest

from src.cache.scrape_cache import SupabaseScrapeCache, canonical_cache_key
from src.cache.screenshot_store import InMemoryScreenshotStore
from src.cache.supabase_cache import normalize_url
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.utils.url_security import InvalidURL

# ---------------------------------------------------------------------------
# Fake Supabase client (table + storage)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeTableQuery:
    """Captures chained Supabase-style table calls against an in-memory store.

    Mirrors the supabase-py postgrest builder surface we actually use: `.select`
    + `.eq` (chainable, multiple times), `.gt("expires_at", iso_ts)` for the
    TTL predicate (strictly greater-than; server-side `expires_at > $1`),
    `.upsert(row, on_conflict=...)` for writes, and `.delete()` for evict.

    Storage is keyed by `(normalized_url, tier)` so the cache's tier-aware
    contract is exercised honestly: scrape-tier rows and interact-tier rows
    coexist under the same URL with independent TTLs and screenshot keys
    (TASK-1488.01).
    """

    def __init__(
        self,
        store: dict[tuple[str, str], dict[str, Any]],
        client: _FakeSupabaseClient,
    ) -> None:
        self._store = store
        # Read-through to the client so `next_upsert_error` is only consumed
        # when the op turns out to be an upsert. A bare `select` (e.g. the
        # TASK-1488.18 evict-fence read in `put()`) must NOT pop the flag,
        # otherwise tests that arm an upsert-failure error never see it
        # raised on the actual upsert that follows.
        self._client = client
        self._op: str | None = None
        self._eqs: dict[str, Any] = {}
        self._gt_col: str | None = None
        self._gt_val: str | None = None
        self._upsert_row: dict[str, Any] | None = None
        self._upsert_on_conflict: str | None = None

    def select(self, *_fields: str) -> _FakeTableQuery:
        self._op = "select"
        return self

    def eq(self, column: str, value: Any) -> _FakeTableQuery:
        self._eqs[column] = value
        return self

    def gt(self, column: str, value: str) -> _FakeTableQuery:
        self._gt_col = column
        self._gt_val = value
        return self

    def maybe_single(self) -> _FakeTableQuery:
        return self

    def upsert(
        self, row: dict[str, Any], *, on_conflict: str | None = None
    ) -> _FakeTableQuery:
        self._op = "upsert"
        self._upsert_row = row
        self._upsert_on_conflict = on_conflict
        return self

    def delete(self) -> _FakeTableQuery:
        self._op = "delete"
        return self

    def _matches_eqs(self, row: dict[str, Any]) -> bool:
        return all(row.get(col) == val for col, val in self._eqs.items())

    def execute(self) -> _FakeResponse:
        if self._op == "select":
            for row in self._store.values():
                if not self._matches_eqs(row):
                    continue
                if self._gt_col == "expires_at" and self._gt_val is not None:
                    threshold = datetime.fromisoformat(self._gt_val)
                    row_expires = datetime.fromisoformat(row["expires_at"])
                    if not row_expires > threshold:
                        continue
                return _FakeResponse(dict(row))
            return _FakeResponse(None)
        if self._op == "upsert":
            assert self._upsert_row is not None
            err = self._client.next_upsert_error
            self._client.next_upsert_error = None
            if err is not None:
                raise err
            tier = self._upsert_row.get("tier", "scrape")
            key = (self._upsert_row["normalized_url"], tier)
            self._store[key] = dict(self._upsert_row)
            return _FakeResponse(dict(self._upsert_row))
        if self._op == "delete":
            to_delete = [
                key for key, row in self._store.items() if self._matches_eqs(row)
            ]
            for key in to_delete:
                del self._store[key]
            return _FakeResponse(None)
        raise AssertionError(f"unexpected op {self._op}")


class _FakeSupabaseClient:
    def __init__(self) -> None:
        # Keyed by (normalized_url, tier). The store property exposes a
        # back-compat dict view keyed by normalized_url that returns the
        # scrape-tier row, so existing tests that index `fake.store[norm]`
        # continue to read the default tier transparently.
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.tables_called: list[str] = []
        # When set, the next upsert raises this error. Lets tests exercise
        # the orphan-blob cleanup path where the DB write fails after a
        # successful screenshot upload.
        self.next_upsert_error: Exception | None = None

    @property
    def store(self) -> _StoreView:
        return _StoreView(self._rows)

    def table(self, name: str) -> _FakeTableQuery:
        self.tables_called.append(name)
        return _FakeTableQuery(self._rows, client=self)


class _StoreView:
    """Back-compat view: indexing by `normalized_url` reads the scrape-tier row.

    Existing tests pre-seed rows with `fake.store[norm] = {...}` and read
    them back with `fake.store[norm]`. After the tier-aware redesign the
    underlying storage is keyed by `(normalized_url, tier)`; this view
    transparently maps the legacy single-key indexing to the default
    scrape-tier slot so those tests keep working without per-line edits.
    """

    def __init__(self, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
        self._rows = rows

    def __getitem__(self, norm: str) -> dict[str, Any]:
        return self._rows[(norm, "scrape")]

    def __setitem__(self, norm: str, row: dict[str, Any]) -> None:
        # Default seed rows to scrape-tier so legacy seeders are tier-aware
        # without per-line edits. Tier-aware tests bypass this view and
        # write through `cache.put(..., tier=...)`.
        materialized = dict(row)
        materialized.setdefault("tier", "scrape")
        self._rows[(norm, materialized["tier"])] = materialized

    def __contains__(self, norm: str) -> bool:
        return (norm, "scrape") in self._rows

    def __len__(self) -> int:
        return len(self._rows)

    def values(self) -> Any:
        return self._rows.values()


def _make_cache(
    fake: _FakeSupabaseClient, store: InMemoryScreenshotStore | None = None
) -> tuple[SupabaseScrapeCache, InMemoryScreenshotStore]:
    """Construct a SupabaseScrapeCache wired to the supplied fakes.

    Returns the (cache, screenshot_store) pair so tests can assert on the
    store independently. The pair is what the GCS migration introduced —
    pre-migration the storage handle hung off the supabase client.
    """
    s = store or InMemoryScreenshotStore()
    cache = SupabaseScrapeCache(fake, s)  # pyright: ignore[reportArgumentType]
    return cache, s


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_scrape(
    *,
    markdown: str | None = "# Hello world\n\nContent body.",
    html: str | None = "<html><body><p>keep</p></body></html>",
    screenshot: str | None = None,
    title: str | None = "Hello",
) -> ScrapeResult:
    return ScrapeResult(
        markdown=markdown,
        html=html,
        screenshot=screenshot,
        metadata=ScrapeMetadata(title=title, source_url="https://example.com/a"),
    )


# ---------------------------------------------------------------------------
# AC#1 — put + get round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_put_then_get_returns_scrape_result_with_markdown_and_metadata(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        scrape = _make_scrape(
            markdown="# Article\n\nThe body.",
            html="<p>keep</p>",
            title="Article",
        )

        await cache.put("https://example.com/a", scrape)
        got = await cache.get("https://example.com/a")

        assert got is not None
        assert got.markdown == "# Article\n\nThe body."
        assert got.metadata is not None
        assert got.metadata.title == "Article"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_url_not_cached(self) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        got = await cache.get("https://nowhere.example.com/")

        assert got is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_cache_entry_is_expired(self) -> None:
        fake = _FakeSupabaseClient()
        url = "https://example.com/stale"
        fake.store[normalize_url(url)] = {
            "normalized_url": normalize_url(url),
            "url": url,
            "host": "example.com",
            "page_kind": "other",
            "page_title": None,
            "markdown": "old",
            "html": None,
            "screenshot_storage_key": None,
            "scraped_at": (datetime.now(UTC) - timedelta(hours=100)).isoformat(),
            "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }
        cache, _ = _make_cache(fake)

        got = await cache.get(url)

        assert got is None

    @pytest.mark.asyncio
    async def test_put_normalizes_url_before_storing(self) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        await cache.put("HTTPS://Example.com/A/?utm_source=x", _make_scrape())
        got = await cache.get("https://example.com/A")

        assert got is not None


# ---------------------------------------------------------------------------
# AC#4 — HTML sanitation
# ---------------------------------------------------------------------------


class TestHtmlSanitation:
    @pytest.mark.asyncio
    async def test_script_style_link_tags_and_html_comments_stripped_on_put(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        raw = (
            '<script>bad()</script>'
            '<style>h1 { color: red; }</style>'
            '<!--secret comment-->'
            '<link rel="stylesheet" href="x.css"/>'
            '<p>keep</p>'
        )
        scrape = _make_scrape(html=raw)

        await cache.put("https://example.com/a", scrape)
        got = await cache.get("https://example.com/a")

        assert got is not None
        assert got.html is not None
        assert "<script" not in got.html
        assert "<style" not in got.html
        assert "<link" not in got.html
        assert "<!--" not in got.html
        assert "<p>keep</p>" in got.html

    @pytest.mark.asyncio
    async def test_sanitation_is_case_insensitive(self) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        raw = "<SCRIPT>x</SCRIPT><Style>y</Style><p>ok</p>"
        scrape = _make_scrape(html=raw)

        await cache.put("https://example.com/a", scrape)
        got = await cache.get("https://example.com/a")

        assert got is not None
        assert got.html is not None
        assert "x" not in got.html
        assert "y" not in got.html
        assert "<p>ok</p>" in got.html

    @pytest.mark.asyncio
    async def test_html_none_is_preserved_as_none(self) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        scrape = _make_scrape(html=None)

        await cache.put("https://example.com/a", scrape)
        got = await cache.get("https://example.com/a")

        assert got is not None
        assert got.html is None


# ---------------------------------------------------------------------------
# AC#2 / AC#3 — Screenshot persistence + signed URLs
# ---------------------------------------------------------------------------


class TestScreenshotPersistence:
    @pytest.mark.asyncio
    async def test_put_with_screenshot_bytes_uploads_to_storage_and_drops_cdn_url(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        scrape = _make_scrape(screenshot="https://firecrawl.cdn/abc.png")
        screenshot_bytes = b"\x89PNG\r\n\x1a\nfakebody"

        await cache.put(
            "https://example.com/a", scrape, screenshot_bytes=screenshot_bytes
        )

        assert len(store.uploads) == 1
        (stored_path, stored_bytes) = next(iter(store.uploads.items()))
        assert stored_bytes == screenshot_bytes
        # The cached row stores the path, not the Firecrawl CDN URL.
        row = fake.store[normalize_url("https://example.com/a")]
        assert row["screenshot_storage_key"] == stored_path
        # The reconstructed ScrapeResult does not re-expose the CDN URL.
        got = await cache.get("https://example.com/a")
        assert got is not None
        assert got.screenshot is None

    @pytest.mark.asyncio
    async def test_put_without_screenshot_bytes_or_url_stores_null_storage_key(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        scrape = _make_scrape(screenshot=None)

        await cache.put("https://example.com/a", scrape)

        row = fake.store[normalize_url("https://example.com/a")]
        assert row["screenshot_storage_key"] is None
        assert store.uploads == {}

    @pytest.mark.asyncio
    async def test_signed_screenshot_url_returns_none_when_no_storage_key(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put("https://example.com/a", _make_scrape(screenshot=None))
        got = await cache.get("https://example.com/a")
        assert got is not None

        signed = await cache.signed_screenshot_url(got)

        assert signed is None

    @pytest.mark.asyncio
    async def test_signed_screenshot_url_returns_signed_url_with_15min_expiry(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"pngbytes",
        )
        got = await cache.get("https://example.com/a")
        assert got is not None

        signed = await cache.signed_screenshot_url(got)

        assert signed is not None
        assert signed.startswith("https://")
        # InMemoryScreenshotStore stamps an X-Goog-Expires marker; the real
        # GCSScreenshotStore returns a v4-signed URL with the same expiry.
        assert "X-Goog-Expires=900" in signed
        assert len(store.signed_calls) >= 1
        # 15 minutes == 900s.
        assert store.signed_calls[-1][1] == 900

    @pytest.mark.asyncio
    async def test_signed_screenshot_url_is_resignable_on_repeat_calls(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"pngbytes",
        )
        got = await cache.get("https://example.com/a")
        assert got is not None

        first = await cache.signed_screenshot_url(got)
        second = await cache.signed_screenshot_url(got)

        assert first is not None
        assert second is not None
        # Two independent sign calls happened (re-signable), not cached.
        assert len(store.signed_calls) == 2

    @pytest.mark.asyncio
    async def test_put_fetches_bytes_from_cdn_url_when_bytes_not_provided(
        self,
        httpx_mock: Any,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        cdn_bytes = b"cdn-png-bytes"
        httpx_mock.add_response(
            url="https://firecrawl.cdn/abc.png",
            content=cdn_bytes,
            status_code=200,
        )

        await cache.put(
            "https://example.com/a",
            _make_scrape(screenshot="https://firecrawl.cdn/abc.png"),
        )

        assert len(store.uploads) == 1
        assert next(iter(store.uploads.values())) == cdn_bytes

    @pytest.mark.asyncio
    async def test_put_skips_upload_when_cdn_fetch_fails(
        self,
        httpx_mock: Any,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        httpx_mock.add_exception(
            httpx.ConnectError("boom"),
            url="https://firecrawl.cdn/abc.png",
        )

        await cache.put(
            "https://example.com/a",
            _make_scrape(screenshot="https://firecrawl.cdn/abc.png"),
        )

        # Cache row still persisted, but with no storage key and no upload.
        row = fake.store[normalize_url("https://example.com/a")]
        assert row["screenshot_storage_key"] is None
        assert store.uploads == {}


# ---------------------------------------------------------------------------
# Fix B — TTL predicate is strictly-greater-than + server-evaluable ISO ts
# ---------------------------------------------------------------------------


class TestTtlPredicate:
    @pytest.mark.asyncio
    async def test_boundary_row_not_yet_expired_returns_cached_value(self) -> None:
        """`expires_at` slightly in the future must still be returned — the
        TTL filter is `expires_at > now()` and a 10s buffer is comfortably
        past `now()` even after ISO-roundtrip latency.
        """
        fake = _FakeSupabaseClient()
        url = "https://example.com/fresh"
        fake.store[normalize_url(url)] = {
            "normalized_url": normalize_url(url),
            "url": url,
            "host": "example.com",
            "page_kind": "other",
            "page_title": "Fresh",
            "markdown": "md",
            "html": None,
            "screenshot_storage_key": None,
            "scraped_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        }
        cache, _ = _make_cache(fake)

        got = await cache.get(url)

        assert got is not None
        assert got.markdown == "md"

    @pytest.mark.asyncio
    async def test_boundary_row_expired_by_one_second_returns_none(self) -> None:
        """A row whose `expires_at` is 1s in the past must not be returned,
        even though the legacy `.gte("now()")` string-literal comparison
        would have admitted it.
        """
        fake = _FakeSupabaseClient()
        url = "https://example.com/just-expired"
        fake.store[normalize_url(url)] = {
            "normalized_url": normalize_url(url),
            "url": url,
            "host": "example.com",
            "page_kind": "other",
            "page_title": None,
            "markdown": "stale",
            "html": None,
            "screenshot_storage_key": None,
            "scraped_at": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
            "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        }
        cache, _ = _make_cache(fake)

        got = await cache.get(url)

        assert got is None


# ---------------------------------------------------------------------------
# Fix B — Signed URL uses the storage_key snapshotted at get()/put() time,
# not a fresh row lookup that could race a concurrent put().
# ---------------------------------------------------------------------------


class TestSignedUrlSnapshot:
    @pytest.mark.asyncio
    async def test_signed_url_uses_snapshotted_storage_key_not_row_lookup(
        self,
    ) -> None:
        """If a second `put()` replaces the cached row between `get()` and
        `signed_screenshot_url()`, the signed URL must still reference the
        storage_key captured at the original `get()` — not the newer row's
        key. Re-lookup by source_url would TOCTOU-race against a concurrent
        put and sign stale data pointers.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        # First put → storage_key#1.
        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"first-png",
        )
        got = await cache.get("https://example.com/a")
        assert got is not None
        first_storage_key = fake.store[normalize_url("https://example.com/a")][
            "screenshot_storage_key"
        ]
        assert first_storage_key is not None

        # Concurrent put replaces the row with a new storage_key#2.
        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"second-png",
        )
        second_storage_key = fake.store[normalize_url("https://example.com/a")][
            "screenshot_storage_key"
        ]
        assert second_storage_key is not None
        assert second_storage_key != first_storage_key

        # Now sign using the first cached result — must reference the
        # snapshotted first_storage_key, not the row's current value.
        signed = await cache.signed_screenshot_url(got)

        assert signed is not None
        assert first_storage_key in signed
        assert second_storage_key not in signed

    @pytest.mark.asyncio
    async def test_signed_url_on_put_result_uses_snapshotted_key(self) -> None:
        """`put()` returns a cached-scrape handle that carries the
        storage_key it just wrote. Signing directly off the put() return
        must not race any subsequent put.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        original = await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"original",
        )
        original_key = fake.store[normalize_url("https://example.com/a")][
            "screenshot_storage_key"
        ]

        # Replace the row with a second put.
        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"replacement",
        )
        replacement_key = fake.store[normalize_url("https://example.com/a")][
            "screenshot_storage_key"
        ]
        assert replacement_key != original_key

        signed = await cache.signed_screenshot_url(original)

        assert signed is not None
        assert original_key in signed


# ---------------------------------------------------------------------------
# Fix B — Orphan blob cleanup on DB upsert failure.
# ---------------------------------------------------------------------------


class TestOrphanBlobCleanup:
    @pytest.mark.asyncio
    async def test_put_upsert_failure_triggers_blob_cleanup_attempt(self) -> None:
        """When the Storage upload succeeds but the DB upsert fails, the
        freshly-uploaded blob must be deleted (best-effort) so it doesn't
        orphan in the bucket. Cross-transactional consistency is not
        guaranteed — the pg_cron sweeper catches anything this misses — but
        cleaning up synchronously shrinks the orphan window dramatically.
        """
        fake = _FakeSupabaseClient()
        fake.next_upsert_error = RuntimeError("db unavailable")
        cache, store = _make_cache(fake)

        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"pngbytes",
        )

        assert len(store.delete_calls) == 1
        removed_path = store.delete_calls[0]
        # Upload + delete match the same path; post-delete the store is empty.
        assert removed_path not in store.uploads
        assert len(store.upload_calls) == 1
        assert store.upload_calls[0][0] == removed_path

    @pytest.mark.asyncio
    async def test_put_with_no_screenshot_skips_cleanup_on_upsert_failure(
        self,
    ) -> None:
        """No upload happened, so nothing to clean up even if upsert fails."""
        fake = _FakeSupabaseClient()
        fake.next_upsert_error = RuntimeError("db unavailable")
        cache, store = _make_cache(fake)

        await cache.put(
            "https://example.com/a",
            _make_scrape(screenshot=None),
        )

        assert store.delete_calls == []
        assert store.upload_calls == []


# ---------------------------------------------------------------------------
# Fix D (codex W3 P2-7) — canonical_cache_key funnels validator + normalize
#
# Dedup keys and cache keys must always agree. validate_public_http_url
# normalizes the "public host + path" form (scheme/host/fragment/IDNA);
# normalize_url strips tracking params + trailing slashes. Mixing only one
# pass would let ?utm_source=x and the bare URL occupy different DB rows.
# ---------------------------------------------------------------------------


class TestCanonicalCacheKey:
    def test_strips_tracking_params_after_validator(self) -> None:
        """Validator preserves query verbatim; canonical key must drop UTM."""
        key = canonical_cache_key("https://example.com/a?utm_source=x&keep=y")

        assert "utm_source" not in key
        assert "keep=y" in key

    def test_lowercases_scheme_and_host(self) -> None:
        key = canonical_cache_key("HTTPS://Example.COM/path")

        parsed = urlparse(key)
        assert parsed.scheme == "https"
        assert parsed.netloc == "example.com"

    def test_drops_fragment(self) -> None:
        key = canonical_cache_key("https://example.com/a#frag")

        assert "#" not in key

    def test_strips_trailing_slash_on_path(self) -> None:
        key = canonical_cache_key("https://example.com/a/")

        assert key == "https://example.com/a"

    def test_tracking_param_and_trailing_slash_same_key(self) -> None:
        """The two URLs share a single canonical dedup key."""
        bare = canonical_cache_key("https://example.com/a")
        noisy = canonical_cache_key("https://example.com/a/?utm_source=x")

        assert bare == noisy

    def test_propagates_invalid_url(self) -> None:
        """Validator rejection bubbles up; caller decides how to surface."""
        with pytest.raises(InvalidURL):
            canonical_cache_key("ftp://example.com/a")


# ---------------------------------------------------------------------------
# TASK-1488.01 — Tier-aware cache (scrape vs interact)
#
# The vibecheck_scrapes UNIQUE constraint moves from `normalized_url` to
# `(normalized_url, tier)` so the Tier 1 (`scrape`) cheap-failure cache and
# the Tier 2 (`interact`) post-fallback cache can coexist for the same URL.
# A retry that successfully fell through to interact must not be short-
# circuited by the still-fresh scrape-tier failure-flagged row, and vice
# versa.
# ---------------------------------------------------------------------------


class TestTierAwareCache:
    @pytest.mark.asyncio
    async def test_put_scrape_tier_then_interact_tier_persists_two_rows(
        self,
    ) -> None:
        """Same URL written under both tiers produces two independent rows.

        Asserts on the underlying store rather than mocked calls — the
        UNIQUE(normalized_url, tier) contract is what we care about, not
        which postgrest method was invoked.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="scrape-md"),
            tier="scrape",
        )
        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="interact-md"),
            tier="interact",
        )

        norm = normalize_url("https://example.com/a")
        rows = list(fake._rows.values())  # pyright: ignore[reportPrivateUsage]
        assert len(rows) == 2
        keys = {(r["normalized_url"], r["tier"]) for r in rows}
        assert keys == {(norm, "scrape"), (norm, "interact")}
        markdowns = {r["tier"]: r["markdown"] for r in rows}
        assert markdowns["scrape"] == "scrape-md"
        assert markdowns["interact"] == "interact-md"

    @pytest.mark.asyncio
    async def test_get_filters_by_tier_returning_matching_row(self) -> None:
        """`get(url, tier='scrape')` and `get(url, tier='interact')`
        return distinct cached payloads for the same URL.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="scrape-md", title="Scrape"),
            tier="scrape",
        )
        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="interact-md", title="Interact"),
            tier="interact",
        )

        scrape_hit = await cache.get("https://example.com/a", tier="scrape")
        interact_hit = await cache.get("https://example.com/a", tier="interact")

        assert scrape_hit is not None
        assert scrape_hit.markdown == "scrape-md"
        assert scrape_hit.metadata is not None
        assert scrape_hit.metadata.title == "Scrape"
        assert interact_hit is not None
        assert interact_hit.markdown == "interact-md"
        assert interact_hit.metadata is not None
        assert interact_hit.metadata.title == "Interact"

    @pytest.mark.asyncio
    async def test_get_default_tier_is_scrape_for_backward_compat(self) -> None:
        """A call without `tier=` resolves to the scrape-tier row, matching
        the behavior of every existing call site before TASK-1488.01.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="scrape-default"),
            tier="scrape",
        )
        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="interact-default"),
            tier="interact",
        )

        defaulted = await cache.get("https://example.com/a")

        assert defaulted is not None
        assert defaulted.markdown == "scrape-default"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_only_other_tier_is_cached(self) -> None:
        """A scrape-tier hit must NOT satisfy an interact-tier read.

        Tier separation is the whole point — a Tier 1 failure-flagged row
        should not poison the Tier 2 retry path.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put(
            "https://example.com/a",
            _make_scrape(markdown="scrape-only"),
            tier="scrape",
        )

        miss = await cache.get("https://example.com/a", tier="interact")

        assert miss is None

    @pytest.mark.asyncio
    async def test_evict_with_tier_removes_only_that_tier(self) -> None:
        """`evict(url, tier='scrape')` leaves the interact-tier row intact.

        Asserts on the visible cache state via `get()`. After TASK-1488.18
        the evicted slot keeps a tombstone row (`evicted_at` set,
        `expires_at` in the past) — the TTL filter excludes it from
        `get()` so the caller-visible behavior is unchanged.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put(
            "https://example.com/a", _make_scrape(markdown="s"), tier="scrape"
        )
        await cache.put(
            "https://example.com/a", _make_scrape(markdown="i"), tier="interact"
        )

        await cache.evict("https://example.com/a", tier="scrape")

        norm = normalize_url("https://example.com/a")
        scrape_row = fake._rows[(norm, "scrape")]  # pyright: ignore[reportPrivateUsage]
        # Scrape slot is tombstoned (TASK-1488.18 fence): markdown nulled,
        # evicted_at set, expires_at in the past.
        assert scrape_row["markdown"] is None
        assert scrape_row["evicted_at"] is not None
        # Interact slot is untouched.
        interact_row = fake._rows[(norm, "interact")]  # pyright: ignore[reportPrivateUsage]
        assert interact_row["markdown"] == "i"
        assert interact_row.get("evicted_at") is None
        assert await cache.get("https://example.com/a", tier="scrape") is None
        assert await cache.get("https://example.com/a", tier="interact") is not None

    @pytest.mark.asyncio
    async def test_evict_without_tier_removes_all_tiers_for_url(self) -> None:
        """`evict(url)` with no tier kwarg drops every cached tier row for
        the URL — the redirect-revalidation path needs to flush both
        tiers in one shot rather than poisoning only Tier 1.

        Both slots are tombstoned (TASK-1488.18 fence) but the TTL filter
        excludes tombstones from `get()`, so caller-visible behavior is
        identical to a hard delete.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put(
            "https://example.com/a", _make_scrape(markdown="s"), tier="scrape"
        )
        await cache.put(
            "https://example.com/a", _make_scrape(markdown="i"), tier="interact"
        )

        await cache.evict("https://example.com/a")

        norm = normalize_url("https://example.com/a")
        for tier in ("scrape", "interact"):
            row = fake._rows[(norm, tier)]  # pyright: ignore[reportPrivateUsage]
            assert row["markdown"] is None
            assert row["screenshot_storage_key"] is None
            assert row["evicted_at"] is not None
        assert await cache.get("https://example.com/a", tier="scrape") is None
        assert await cache.get("https://example.com/a", tier="interact") is None

    @pytest.mark.asyncio
    async def test_put_default_tier_writes_scrape_row(self) -> None:
        """No-kwarg `put()` keeps every legacy caller pinned to scrape-tier
        without per-site code changes — backward-compat AC#2.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        await cache.put("https://example.com/a", _make_scrape(markdown="legacy"))

        rows = list(fake._rows.values())  # pyright: ignore[reportPrivateUsage]
        assert len(rows) == 1
        assert rows[0]["tier"] == "scrape"
        assert rows[0]["markdown"] == "legacy"


# TASK-1488.18 — evict-tombstone fence + final_url rehydration


class TestEvictFenceAndFinalUrl:
    @pytest.mark.asyncio
    async def test_put_after_recent_evict_aborts(self) -> None:
        """A recent `evict()` writes a tombstone; the next `put()` reads
        `evicted_at`, recognizes the fence is active, and aborts (no
        upsert lands). The just-uploaded screenshot blob is cleaned up
        so it doesn't orphan in the bucket.
        """
        fake = _FakeSupabaseClient()
        cache, store = _make_cache(fake)
        norm = normalize_url("https://example.com/poisoned")

        # Seed a fresh tombstone the way `evict(tier=None)` would.
        now_iso = datetime.now(UTC).isoformat()
        past_iso = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        fake._rows[(norm, "scrape")] = {  # pyright: ignore[reportPrivateUsage]
            "normalized_url": norm,
            "tier": "scrape",
            "url": norm,
            "final_url": None,
            "host": "example.com",
            "page_kind": "other",
            "page_title": None,
            "markdown": None,
            "html": None,
            "screenshot_storage_key": None,
            "scraped_at": now_iso,
            "expires_at": past_iso,
            "evicted_at": now_iso,
        }

        result = await cache.put(
            "https://example.com/poisoned",
            _make_scrape(markdown="raced", screenshot=None),
            screenshot_bytes=b"pngbytes",
        )

        # Put aborted: result has no storage_key.
        assert result.storage_key is None
        # Tombstone row is unchanged: still NULL markdown, evicted_at set.
        row = fake._rows[(norm, "scrape")]  # pyright: ignore[reportPrivateUsage]
        assert row["markdown"] is None
        assert row["evicted_at"] is not None
        # Just-uploaded blob was cleaned up.
        assert len(store.delete_calls) == 1

    @pytest.mark.asyncio
    async def test_put_after_old_evict_proceeds(self) -> None:
        """An evict that fired LONG ago (outside the fence window) must
        not block fresh puts forever. The fence releases on a stale
        `evicted_at`.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        norm = normalize_url("https://example.com/long-ago-evicted")

        # evicted_at older than the 30s fence window → fence released.
        old_iso = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        past_iso = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        now_iso = datetime.now(UTC).isoformat()
        fake._rows[(norm, "scrape")] = {  # pyright: ignore[reportPrivateUsage]
            "normalized_url": norm,
            "tier": "scrape",
            "url": norm,
            "final_url": None,
            "host": "example.com",
            "page_kind": "other",
            "page_title": None,
            "markdown": None,
            "html": None,
            "screenshot_storage_key": None,
            "scraped_at": now_iso,
            "expires_at": past_iso,
            "evicted_at": old_iso,
        }

        await cache.put(
            "https://example.com/long-ago-evicted",
            _make_scrape(markdown="fresh"),
        )

        row = fake._rows[(norm, "scrape")]  # pyright: ignore[reportPrivateUsage]
        assert row["markdown"] == "fresh"
        # Successful put clears the tombstone marker.
        assert row["evicted_at"] is None

    @pytest.mark.asyncio
    async def test_get_rehydrates_metadata_source_url_from_final_url(
        self,
    ) -> None:
        """`get()` returns `metadata.source_url` populated from the row's
        `final_url` (Firecrawl's resolved post-redirect URL), not from
        the input URL. Without this, `_revalidate_final_url` on a
        replayed poisoned row sees the input URL as the resolved URL
        and silently skips the SSRF re-check.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)

        # Firecrawl returned a resolved URL different from the input.
        scrape = ScrapeResult(
            markdown="body",
            metadata=ScrapeMetadata(
                title="Resolved",
                source_url="https://final.example/resolved",
            ),
        )
        await cache.put(
            "https://input.example/in", scrape, tier="scrape"
        )

        cached = await cache.get("https://input.example/in", tier="scrape")
        assert cached is not None
        assert cached.metadata is not None
        assert cached.metadata.source_url == "https://final.example/resolved"

    @pytest.mark.asyncio
    async def test_get_falls_back_to_input_url_when_final_url_null(
        self,
    ) -> None:
        """Legacy rows (pre-TASK-1488.18) have `final_url=NULL`.
        `_row_to_cached_scrape` falls back to the row's `url` so existing
        rows still hydrate cleanly.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        norm = normalize_url("https://legacy.example/bare")
        now_iso = datetime.now(UTC).isoformat()
        fresh_iso = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

        fake._rows[(norm, "scrape")] = {  # pyright: ignore[reportPrivateUsage]
            "normalized_url": norm,
            "tier": "scrape",
            "url": "https://legacy.example/bare",
            "final_url": None,
            "host": "legacy.example",
            "page_kind": "other",
            "page_title": "Legacy",
            "markdown": "legacy body",
            "html": None,
            "screenshot_storage_key": None,
            "scraped_at": now_iso,
            "expires_at": fresh_iso,
            "evicted_at": None,
        }

        cached = await cache.get("https://legacy.example/bare", tier="scrape")
        assert cached is not None
        assert cached.metadata is not None
        assert cached.metadata.source_url == "https://legacy.example/bare"

    @pytest.mark.asyncio
    async def test_evict_writes_tombstone_with_evicted_at(self) -> None:
        """`evict()` leaves a tombstone row with `evicted_at` set so a
        concurrent put can recognize the fence on its pre-upsert read.
        """
        fake = _FakeSupabaseClient()
        cache, _ = _make_cache(fake)
        await cache.put(
            "https://example.com/x", _make_scrape(markdown="hi"), tier="scrape"
        )

        await cache.evict("https://example.com/x", tier="scrape")

        norm = normalize_url("https://example.com/x")
        row = fake._rows[(norm, "scrape")]  # pyright: ignore[reportPrivateUsage]
        assert row["evicted_at"] is not None
        # Tombstone is filtered from get() by the TTL predicate.
        assert await cache.get("https://example.com/x", tier="scrape") is None
