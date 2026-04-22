"""Unit tests for SupabaseScrapeCache (TASK-1473.08).

The Supabase client is faked in-process: these tests exercise the cache's
round-trip behavior, HTML sanitation, and signed-URL surface against a
deterministic fake, never the live Storage API.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from src.cache.scrape_cache import SupabaseScrapeCache
from src.cache.supabase_cache import normalize_url
from src.firecrawl_client import ScrapeMetadata, ScrapeResult

# ---------------------------------------------------------------------------
# Fake Supabase client (table + storage)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeTableQuery:
    """Captures chained Supabase-style table calls against an in-memory store.

    Mirrors the supabase-py postgrest builder surface we actually use: `.select`
    + `.eq` for the lookup key, `.gt("expires_at", iso_ts)` for the TTL
    predicate (strictly greater-than; server-side `expires_at > $1`), and
    `.upsert(row, on_conflict=...)` for writes. The execute() step is
    deliberately tight — supports only the shapes the real code relies on, so
    a new query shape surfaces as `AssertionError(unexpected op)` instead of
    silently returning wrong data.
    """

    def __init__(
        self, store: dict[str, dict[str, Any]], upsert_error: Exception | None = None
    ) -> None:
        self._store = store
        self._upsert_error = upsert_error
        self._op: str | None = None
        self._eq_col: str | None = None
        self._eq_val: str | None = None
        self._gt_col: str | None = None
        self._gt_val: str | None = None
        self._upsert_row: dict[str, Any] | None = None

    def select(self, *_fields: str) -> _FakeTableQuery:
        self._op = "select"
        return self

    def eq(self, column: str, value: str) -> _FakeTableQuery:
        self._eq_col = column
        self._eq_val = value
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
        return self

    def execute(self) -> _FakeResponse:
        if self._op == "select":
            assert self._eq_val is not None
            row = self._store.get(self._eq_val)
            if row is None:
                return _FakeResponse(None)
            # Apply TTL predicate if set — strictly greater-than, matching
            # `.gt("expires_at", now_iso)`. If not set, fall through without
            # filtering (storage-key-only lookups don't pass a TTL).
            if self._gt_col == "expires_at" and self._gt_val is not None:
                threshold = datetime.fromisoformat(self._gt_val)
                row_expires = datetime.fromisoformat(row["expires_at"])
                if not row_expires > threshold:
                    return _FakeResponse(None)
            return _FakeResponse(dict(row))
        if self._op == "upsert":
            assert self._upsert_row is not None
            if self._upsert_error is not None:
                raise self._upsert_error
            self._store[self._upsert_row["normalized_url"]] = dict(self._upsert_row)
            return _FakeResponse(dict(self._upsert_row))
        raise AssertionError(f"unexpected op {self._op}")


class _FakeBucket:
    def __init__(self, bucket_name: str, uploads: dict[str, bytes]) -> None:
        self.bucket_name = bucket_name
        self._uploads = uploads
        self.upload_calls: list[tuple[str, bytes, dict[str, Any] | None]] = []
        self.signed_calls: list[tuple[str, int]] = []
        self.remove_calls: list[list[str]] = []

    def upload(
        self,
        path: str,
        file: bytes,
        file_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.upload_calls.append((path, file, file_options))
        self._uploads[path] = file
        return {"path": path}

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, Any]:
        self.signed_calls.append((path, expires_in))
        if path not in self._uploads:
            # Supabase returns a 400-shaped error dict in this case; our code
            # should surface None to the caller rather than crash.
            return {"error": "not found", "signedURL": None}
        return {
            "signedURL": (
                f"https://fake.supabase.co/storage/v1/object/sign/"
                f"{self.bucket_name}/{path}?token=abc&exp={expires_in}"
            )
        }

    def remove(self, paths: list[str]) -> list[dict[str, Any]]:
        """Mirror supabase-py Storage `.remove()` — removes one or more paths.
        Returns a list with one dict per path (success-shaped for our tests).
        """
        self.remove_calls.append(list(paths))
        removed = []
        for p in paths:
            if p in self._uploads:
                del self._uploads[p]
            removed.append({"name": p})
        return removed


class _FakeStorage:
    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self._buckets: dict[str, _FakeBucket] = {}

    def from_(self, bucket_name: str) -> _FakeBucket:
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = _FakeBucket(bucket_name, self.uploads)
        return self._buckets[bucket_name]


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.storage = _FakeStorage()
        self.tables_called: list[str] = []
        # When set, the next upsert raises this error. Lets tests exercise
        # the orphan-blob cleanup path where the DB write fails after a
        # successful screenshot upload.
        self.next_upsert_error: Exception | None = None

    def table(self, name: str) -> _FakeTableQuery:
        self.tables_called.append(name)
        err = self.next_upsert_error
        self.next_upsert_error = None
        return _FakeTableQuery(self.store, upsert_error=err)


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
        metadata=ScrapeMetadata(title=title, sourceURL="https://example.com/a"),
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

        got = await cache.get(url)

        assert got is None

    @pytest.mark.asyncio
    async def test_put_normalizes_url_before_storing(self) -> None:
        fake = _FakeSupabaseClient()
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
        scrape = _make_scrape(screenshot="https://firecrawl.cdn/abc.png")
        screenshot_bytes = b"\x89PNG\r\n\x1a\nfakebody"

        await cache.put(
            "https://example.com/a", scrape, screenshot_bytes=screenshot_bytes
        )

        assert len(fake.storage.uploads) == 1
        (stored_path, stored_bytes) = next(iter(fake.storage.uploads.items()))
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
        scrape = _make_scrape(screenshot=None)

        await cache.put("https://example.com/a", scrape)

        row = fake.store[normalize_url("https://example.com/a")]
        assert row["screenshot_storage_key"] is None
        assert fake.storage.uploads == {}

    @pytest.mark.asyncio
    async def test_signed_screenshot_url_returns_none_when_no_storage_key(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        assert "token=" in signed
        bucket = fake.storage.from_("vibecheck-screenshots")
        assert len(bucket.signed_calls) >= 1
        # 15 minutes == 900s.
        assert bucket.signed_calls[-1][1] == 900

    @pytest.mark.asyncio
    async def test_signed_screenshot_url_is_resignable_on_repeat_calls(
        self,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        bucket = fake.storage.from_("vibecheck-screenshots")
        # Two independent sign calls happened (re-signable), not cached.
        assert len(bucket.signed_calls) == 2

    @pytest.mark.asyncio
    async def test_put_fetches_bytes_from_cdn_url_when_bytes_not_provided(
        self,
        httpx_mock: Any,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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

        assert len(fake.storage.uploads) == 1
        assert next(iter(fake.storage.uploads.values())) == cdn_bytes

    @pytest.mark.asyncio
    async def test_put_skips_upload_when_cdn_fetch_fails(
        self,
        httpx_mock: Any,
    ) -> None:
        fake = _FakeSupabaseClient()
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]
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
        assert fake.storage.uploads == {}


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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

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
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

        await cache.put(
            "https://example.com/a",
            _make_scrape(),
            screenshot_bytes=b"pngbytes",
        )

        bucket = fake.storage.from_("vibecheck-screenshots")
        assert len(bucket.remove_calls) == 1
        # The blob that was just uploaded should be the one removed.
        assert len(bucket.remove_calls[0]) == 1
        removed_path = bucket.remove_calls[0][0]
        # Upload + remove match the same path; post-remove the bucket is empty.
        assert removed_path not in bucket._uploads  # noqa: SLF001
        assert len(bucket.upload_calls) == 1
        assert bucket.upload_calls[0][0] == removed_path

    @pytest.mark.asyncio
    async def test_put_with_no_screenshot_skips_cleanup_on_upsert_failure(
        self,
    ) -> None:
        """No upload happened, so nothing to clean up even if upsert fails."""
        fake = _FakeSupabaseClient()
        fake.next_upsert_error = RuntimeError("db unavailable")
        cache = SupabaseScrapeCache(fake)  # pyright: ignore[reportArgumentType]

        await cache.put(
            "https://example.com/a",
            _make_scrape(screenshot=None),
        )

        bucket = fake.storage.from_("vibecheck-screenshots")
        assert bucket.remove_calls == []
        assert bucket.upload_calls == []
