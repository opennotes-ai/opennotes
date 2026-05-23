"""Tests for TASK-1657.25: extension screenshot submission + cache-first screenshots.

Covers:
- Extension submits screenshot → stored in cache + screenshot_store with correct content type
- Frame route returns cached screenshot when available (typed lookup)
- Frame route returns typed-miss (queued / not_captured) when not in cache
- raw_html preserved through scrape submit (not stripped during sanitization)
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta

import pytest

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.url_content_scan.frame import lookup_screenshot_typed
from src.url_content_scan.models import UrlScanScrape
from src.url_content_scan.schemas import ScreenshotMissReason


@dataclass
class _CachedScrape:
    html: str | None = None
    markdown: str | None = None
    metadata: ScrapeMetadata | None = None
    storage_key: str | None = None


class _FakeScrapeCache:
    def __init__(
        self,
        cached_by_tier: dict[str, _CachedScrape | None] | None = None,
        *,
        extension_key: str | None = None,
    ) -> None:
        self._cached_by_tier = cached_by_tier or {}
        self._extension_key = extension_key
        self.get_calls: list[tuple[str, str]] = []
        self.put_calls: list[tuple[str, ScrapeResult, str]] = []
        self.cache_extension_screenshot_calls: list[tuple[str, bytes, str]] = []

    async def get(self, url: str, *, tier: str = "scrape") -> _CachedScrape | None:
        self.get_calls.append((url, tier))
        return self._cached_by_tier.get(tier)

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
        *,
        tier: str = "scrape",
    ) -> _CachedScrape:
        self.put_calls.append((url, scrape, tier))
        return _CachedScrape(storage_key="shots/generated.png")

    async def evict(self, url: str, *, tier: str = "scrape") -> None:
        pass

    async def cache_extension_screenshot(
        self,
        url: str,
        screenshot_bytes: bytes,
        *,
        content_type: str = "image/png",
    ) -> str | None:
        self.cache_extension_screenshot_calls.append((url, screenshot_bytes, content_type))
        return self._extension_key


class _FakeScreenshotStore:
    def __init__(self, signed_url: str = "https://signed.example/shots/example.png") -> None:
        self.signed_url = signed_url
        self.calls: list[tuple[str, timedelta]] = []

    async def sign_url(self, storage_key: str, *, ttl: timedelta) -> str | None:
        self.calls.append((storage_key, ttl))
        return self.signed_url


def _scrape_with_storage_key(storage_key: str = "shots/ext.png") -> _CachedScrape:
    return _CachedScrape(
        html="<main><p>Body</p></main>",
        markdown="# Body",
        metadata=ScrapeMetadata(title="Example", source_url="https://example.com/article"),
        storage_key=storage_key,
    )


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: bytes) -> bool:
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    async def delete(self, key: str) -> int:
        existed = int(key in self.values)
        self.values.pop(key, None)
        return existed


@dataclass
class _FakeBlob:
    path: str
    uploads: dict[str, bytes]
    content_types: dict[str, str]
    deletes: list[str]

    def upload_from_string(self, value: bytes, *, content_type: str) -> None:
        self.uploads[self.path] = value
        self.content_types[self.path] = content_type

    def delete(self) -> None:
        self.deletes.append(self.path)
        self.uploads.pop(self.path, None)


class _FakeBucket:
    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.deletes: list[str] = []

    def blob(self, path: str) -> _FakeBlob:
        return _FakeBlob(
            path=path,
            uploads=self.uploads,
            content_types=self.content_types,
            deletes=self.deletes,
        )


class _FakeStorageClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, _name: str) -> _FakeBucket:
        return self._bucket


class _FakeDBSession:
    def __init__(self, store: dict[tuple[str, str], UrlScanScrape]) -> None:
        self._store = store

    async def get(self, model: type[UrlScanScrape], key: tuple[str, str]) -> UrlScanScrape | None:
        assert model is UrlScanScrape
        return self._store.get(key)

    async def merge(self, row: UrlScanScrape) -> UrlScanScrape:
        self._store[(row.normalized_url, row.tier)] = row
        return row

    async def delete(self, row: UrlScanScrape) -> None:
        self._store.pop((row.normalized_url, row.tier), None)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _FakeSessionFactory:
    def __init__(self, session: _FakeDBSession) -> None:
        self.session = session

    @asynccontextmanager
    async def __call__(self):
        yield self.session


def _make_real_cache(db_store=None, bucket=None):
    from src.url_content_scan.scrape_cache import ScrapeCache
    from src.url_content_scan.screenshot_store import ScreenshotStore

    db_store = db_store if db_store is not None else {}
    bucket = bucket or _FakeBucket()
    redis = _FakeRedis()
    session = _FakeDBSession(db_store)
    screenshot_store = ScreenshotStore(
        bucket_name="url-scan-screenshots",
        storage_client=_FakeStorageClient(bucket),
    )
    cache = ScrapeCache(
        redis_client=redis,
        session_factory=_FakeSessionFactory(session),
        screenshot_store=screenshot_store,
    )
    return cache, redis, db_store, bucket


class TestScreenshotMissReasonEnum:
    def test_enum_has_queued_value(self) -> None:
        assert ScreenshotMissReason.QUEUED == "queued"

    def test_enum_has_not_captured_value(self) -> None:
        assert ScreenshotMissReason.NOT_CAPTURED == "not_captured"

    def test_enum_has_available_value(self) -> None:
        assert ScreenshotMissReason.AVAILABLE == "available"


class TestLookupScreenshotTyped:
    @pytest.mark.asyncio
    async def test_returns_available_when_screenshot_in_cache(self) -> None:
        cache = _FakeScrapeCache(
            cached_by_tier={"interact": _scrape_with_storage_key("shots/ext.png")}
        )
        screenshot_store = _FakeScreenshotStore()

        result = await lookup_screenshot_typed(
            "https://example.com/article",
            scrape_cache=cache,
            screenshot_store=screenshot_store,
        )

        assert result["reason"] == ScreenshotMissReason.AVAILABLE
        assert result["screenshot_url"] == "https://signed.example/shots/example.png"

    @pytest.mark.asyncio
    async def test_returns_not_captured_when_no_storage_key(self) -> None:
        cache = _FakeScrapeCache(
            cached_by_tier={"scrape": _CachedScrape(html="<p>body</p>", storage_key=None)}
        )
        screenshot_store = _FakeScreenshotStore()

        result = await lookup_screenshot_typed(
            "https://example.com/article",
            scrape_cache=cache,
            screenshot_store=screenshot_store,
        )

        assert result["reason"] == ScreenshotMissReason.NOT_CAPTURED
        assert result.get("screenshot_url") is None

    @pytest.mark.asyncio
    async def test_returns_queued_when_no_cache_entry_at_all(self) -> None:
        cache = _FakeScrapeCache()
        screenshot_store = _FakeScreenshotStore()

        result = await lookup_screenshot_typed(
            "https://example.com/article",
            scrape_cache=cache,
            screenshot_store=screenshot_store,
        )

        assert result["reason"] == ScreenshotMissReason.QUEUED
        assert result.get("screenshot_url") is None

    @pytest.mark.asyncio
    async def test_checks_all_tiers_in_order(self) -> None:
        cache = _FakeScrapeCache(
            cached_by_tier={"scrape": _scrape_with_storage_key("shots/scrape.png")}
        )
        screenshot_store = _FakeScreenshotStore()

        result = await lookup_screenshot_typed(
            "https://example.com/article",
            scrape_cache=cache,
            screenshot_store=screenshot_store,
        )

        assert result["reason"] == ScreenshotMissReason.AVAILABLE
        assert cache.get_calls[0] == ("https://example.com/article", "browser_html")

    @pytest.mark.asyncio
    async def test_returns_available_with_signed_url_using_15min_ttl(self) -> None:
        cache = _FakeScrapeCache(
            cached_by_tier={"browser_html": _scrape_with_storage_key("shots/bh.png")}
        )
        screenshot_store = _FakeScreenshotStore()

        result = await lookup_screenshot_typed(
            "https://example.com/article",
            scrape_cache=cache,
            screenshot_store=screenshot_store,
        )

        assert result["reason"] == ScreenshotMissReason.AVAILABLE
        assert screenshot_store.calls == [("shots/bh.png", timedelta(minutes=15))]


class TestScrapeCacheExtensionScreenshot:
    @pytest.mark.asyncio
    async def test_cache_extension_screenshot_stores_bytes_with_correct_content_type(
        self,
    ) -> None:
        cache, _redis, _db_store, bucket = _make_real_cache()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        storage_key = await cache.cache_extension_screenshot(
            "https://example.com/article",
            png_bytes,
            content_type="image/png",
        )

        assert storage_key is not None
        assert bucket.uploads[storage_key] == png_bytes
        assert bucket.content_types[storage_key] == "image/png"

    @pytest.mark.asyncio
    async def test_cache_extension_screenshot_updates_db_row_storage_key(self) -> None:
        cache, _redis, db_store, _bucket = _make_real_cache()

        storage_key = await cache.cache_extension_screenshot(
            "https://example.com/article",
            b"png-bytes",
            content_type="image/png",
        )

        assert storage_key is not None
        row = db_store.get(("https://example.com/article", "browser_html"))
        assert row is not None
        assert row.screenshot_storage_key == storage_key

    @pytest.mark.asyncio
    async def test_cache_extension_screenshot_uses_browser_html_tier(self) -> None:
        cache, _redis, db_store, _bucket = _make_real_cache()

        await cache.cache_extension_screenshot(
            "https://example.com/article",
            b"png",
            content_type="image/png",
        )

        assert ("https://example.com/article", "browser_html") in db_store


class TestRawHtmlPreservation:
    @pytest.mark.asyncio
    async def test_raw_html_is_not_stripped_from_scrape_cache_put(self) -> None:
        cache, _redis, _db_store, _bucket = _make_real_cache()

        raw_html = "<html><head><script>alert(1)</script></head><body><p>Keep</p></body></html>"
        scrape = ScrapeResult(
            html="<p>Keep</p>",
            markdown="Keep",
            raw_html=raw_html,
            metadata=ScrapeMetadata(
                title="Test",
                source_url="https://example.com/article",
                status_code=200,
            ),
        )

        cached = await cache.put(
            "https://example.com/article",
            scrape,
            tier="browser_html",
        )

        assert cached.raw_html == raw_html

    @pytest.mark.asyncio
    async def test_submit_browser_scrape_passes_raw_html_to_cache_unchanged(self) -> None:
        from src.url_content_scan.analyze_handler import submit_browser_scrape
        from src.url_content_scan.schemas import BrowserScrapeRequest
        from tests.unit.url_content_scan.test_analyze_handler import (
            _FakeSession,
            _request,
        )

        session = _FakeSession()
        raw_html = "<html><script>alert(1)</script><body><p>Content</p></body></html>"

        dispatch_calls: list[dict] = []

        async def fake_dispatch(job_id, source_url, normalized_url, attempt_id):
            dispatch_calls.append(
                {
                    "job_id": job_id,
                    "source_url": source_url,
                    "normalized_url": normalized_url,
                    "attempt_id": attempt_id,
                }
            )
            return "wf-123"

        async def fake_web_risk(_url):
            return None

        cache = _FakeScrapeCache(extension_key="ext/shots/abc.png")

        response = await submit_browser_scrape(
            session,
            _request(),
            BrowserScrapeRequest(
                url="https://example.com/article",
                html=raw_html,
                markdown="Content",
                title="Test",
                screenshot_base64=None,
            ),
            dispatch=fake_dispatch,
            web_risk=fake_web_risk,
            scrape_cache=cache,
        )

        assert response is not None
        assert len(dispatch_calls) == 1
        assert dispatch_calls[0]["source_url"] == "https://example.com/article"
        assert len(cache.put_calls) == 1
        _url, scrape_put, tier = cache.put_calls[0]
        assert tier == "browser_html"
        assert scrape_put.raw_html is not None
        assert "<script>" in scrape_put.raw_html
        assert scrape_put.html is not None
        assert "<script>" not in scrape_put.html

    @pytest.mark.asyncio
    async def test_submit_browser_scrape_uploads_screenshot_when_provided(self) -> None:
        from src.url_content_scan.analyze_handler import submit_browser_scrape
        from src.url_content_scan.schemas import BrowserScrapeRequest
        from tests.unit.url_content_scan.test_analyze_handler import (
            _FakeSession,
            _request,
        )

        session = _FakeSession()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        b64 = base64.b64encode(png_bytes).decode()

        async def fake_dispatch(*_args):
            return "wf-123"

        async def fake_web_risk(_url):
            return None

        cache = _FakeScrapeCache(extension_key="ext/shots/screenshot.png")

        response = await submit_browser_scrape(
            session,
            _request(),
            BrowserScrapeRequest(
                url="https://example.com/article",
                html="<html><body><p>Content</p></body></html>",
                markdown=None,
                title="Test",
                screenshot_base64=b64,
            ),
            dispatch=fake_dispatch,
            web_risk=fake_web_risk,
            scrape_cache=cache,
        )

        assert response is not None
        assert len(cache.cache_extension_screenshot_calls) == 1
        _call_url, call_bytes, call_ct = cache.cache_extension_screenshot_calls[0]
        assert call_bytes == png_bytes
        assert call_ct == "image/png"
