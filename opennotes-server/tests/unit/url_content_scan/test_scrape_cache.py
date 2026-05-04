from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.url_content_scan.models import UrlScanScrape


@dataclass
class _FakeBlob:
    path: str
    uploads: dict[str, bytes]
    deletes: list[str]
    signed_calls: list[tuple[str, timedelta, str | None, str | None]]
    fail_delete_once: bool = False

    def upload_from_string(self, value: bytes, *, content_type: str) -> None:
        assert content_type == "image/png"
        self.uploads[self.path] = value

    def delete(self) -> None:
        self.deletes.append(self.path)
        if self.fail_delete_once:
            self.fail_delete_once = False
            raise RuntimeError("delete failed")
        self.uploads.pop(self.path, None)

    def generate_signed_url(
        self,
        *,
        version: str,
        expiration: timedelta,
        method: str,
        service_account_email: str,
        access_token: str,
    ) -> str:
        assert version == "v4"
        assert method == "GET"
        self.signed_calls.append(
            (self.path, expiration, service_account_email, access_token)
        )
        return f"https://signed.example/{self.path}?ttl={int(expiration.total_seconds())}"


class _FakeBucket:
    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self.deletes: list[str] = []
        self.signed_calls: list[tuple[str, timedelta, str | None, str | None]] = []
        self.fail_delete_once_for: str | None = None

    def blob(self, path: str) -> _FakeBlob:
        return _FakeBlob(
            path=path,
            uploads=self.uploads,
            deletes=self.deletes,
            signed_calls=self.signed_calls,
            fail_delete_once=path == self.fail_delete_once_for,
        )


class _FakeStorageClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, _name: str) -> _FakeBucket:
        return self._bucket


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.fail_setex = False

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: bytes) -> bool:
        if self.fail_setex:
            raise RuntimeError("redis write failed")
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    async def delete(self, key: str) -> int:
        existed = int(key in self.values)
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return existed


class _FakeScalarResult:
    def __init__(self, row: UrlScanScrape | None) -> None:
        self._row = row

    def one_or_none(self) -> UrlScanScrape | None:
        return self._row


class _FakeResult:
    def __init__(self, row: UrlScanScrape | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> UrlScanScrape | None:
        return self._row

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._row)


class _FakeSession:
    def __init__(
        self, store: dict[tuple[str, str], UrlScanScrape], *, fail_commit: bool = False
    ) -> None:
        self._store = store
        self._fail_commit = fail_commit
        self.commit_calls = 0
        self.rollback_calls = 0

    async def get(self, model: type[UrlScanScrape], key: tuple[str, str]) -> UrlScanScrape | None:
        assert model is UrlScanScrape
        return self._store.get(key)

    async def merge(self, row: UrlScanScrape) -> UrlScanScrape:
        self._store[(row.normalized_url, row.tier)] = row
        return row

    async def delete(self, row: UrlScanScrape) -> None:
        self._store.pop((row.normalized_url, row.tier), None)

    async def commit(self) -> None:
        self.commit_calls += 1
        if self._fail_commit:
            raise RuntimeError("db commit failed")

    async def rollback(self) -> None:
        self.rollback_calls += 1

    async def execute(self, _statement: object) -> _FakeResult:
        raise AssertionError("test should not issue free-form execute() calls")


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    @asynccontextmanager
    async def __call__(self):
        yield self.session


def _make_scrape(
    *,
    markdown: str = "# Example\n\nBody text.",
    html: str | None = "<main><p>Body text.</p></main>",
    screenshot: str | None = "https://cdn.example/s.png",
) -> ScrapeResult:
    return ScrapeResult(
        markdown=markdown,
        html=html,
        screenshot=screenshot,
        metadata=ScrapeMetadata(
            title="Example",
            source_url="https://example.com/source",
            status_code=200,
        ),
    )


def _make_cache(
    *,
    store: dict[tuple[str, str], UrlScanScrape] | None = None,
    fail_commit: bool = False,
):
    from src.url_content_scan.scrape_cache import ScrapeCache
    from src.url_content_scan.screenshot_store import ScreenshotStore

    db_store = store or {}
    redis = _FakeRedis()
    session = _FakeSession(db_store, fail_commit=fail_commit)
    bucket = _FakeBucket()
    screenshot_store = ScreenshotStore(
        bucket_name="url-scan-screenshots",
        storage_client=_FakeStorageClient(bucket),
    )
    cache = ScrapeCache(
        redis_client=redis,
        session_factory=_FakeSessionFactory(session),
        screenshot_store=screenshot_store,
    )
    return cache, redis, session, db_store, bucket


def _fake_adc():
    credentials = SimpleNamespace(
        service_account_email="url-scan@example.iam.gserviceaccount.com",
        token="adc-token",
        refresh=lambda _request: None,
    )
    return patch("google.auth.default", return_value=(credentials, "open-notes-core"))


@pytest.mark.asyncio
async def test_get_returns_none_on_cache_miss() -> None:
    cache, _, _, _, _ = _make_cache()

    assert await cache.get("https://example.com/miss") is None


@pytest.mark.asyncio
async def test_put_then_get_round_trips_through_redis_and_db() -> None:
    cache, redis, _, db_store, bucket = _make_cache()

    cached = await cache.put(
        "https://example.com/a?utm_source=test",
        _make_scrape(
            html="<main><!--x--><script>bad()</script><p>keep</p></main>",
        ),
        screenshot_bytes=b"png-bytes",
    )

    assert cached.storage_key is not None
    assert bucket.uploads[cached.storage_key] == b"png-bytes"
    assert len(redis.values) == 1
    row = next(iter(db_store.values()))
    assert row.screenshot_storage_key == cached.storage_key
    assert row.page_title == "Example"

    got = await cache.get("https://example.com/a")

    assert got is not None
    assert got.markdown == "# Example\n\nBody text."
    assert got.html == "<main><p>keep</p></main>"
    assert got.storage_key == cached.storage_key
    assert got.screenshot is None


@pytest.mark.asyncio
async def test_get_returns_none_when_redis_body_is_missing_even_if_db_row_exists() -> None:
    cache, redis, _, db_store, _ = _make_cache()
    cached = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"png")
    assert cached.storage_key is not None
    redis.values.clear()

    got = await cache.get("https://example.com/a")

    assert got is None
    assert len(db_store) == 1


@pytest.mark.asyncio
async def test_get_evicts_expired_row_and_screenshot() -> None:
    cache, redis, _, db_store, bucket = _make_cache()
    cached = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"png")
    assert cached.storage_key is not None
    row = next(iter(db_store.values()))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    got = await cache.get("https://example.com/a")

    assert got is None
    assert not db_store
    assert not redis.values
    assert cached.storage_key in bucket.deletes


@pytest.mark.asyncio
async def test_signed_screenshot_url_uses_cached_storage_key_without_db_requery() -> None:
    cache, _, session, db_store, bucket = _make_cache()
    original = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"old")
    assert original.storage_key is not None

    db_row = next(iter(db_store.values()))
    db_row.screenshot_storage_key = "newer-key.png"
    with _fake_adc():
        signed = await cache.signed_screenshot_url(original)

    assert signed == f"https://signed.example/{original.storage_key}?ttl=900"
    assert bucket.signed_calls == [
        (
            original.storage_key,
            timedelta(minutes=15),
            "url-scan@example.iam.gserviceaccount.com",
            "adc-token",
        )
    ]
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_evict_is_idempotent_and_tolerates_gcs_delete_failure() -> None:
    cache, redis, _, db_store, bucket = _make_cache()
    cached = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"old")
    assert cached.storage_key is not None
    bucket.fail_delete_once_for = cached.storage_key

    await cache.evict("https://example.com/a")
    await cache.evict("https://example.com/a")

    assert await cache.get("https://example.com/a") is None
    assert not db_store
    assert not redis.values
    assert bucket.deletes.count(cached.storage_key) == 1


@pytest.mark.asyncio
async def test_scrape_and_interact_tiers_are_separate() -> None:
    cache, _, _, db_store, _ = _make_cache()

    await cache.put("https://example.com/a", _make_scrape(markdown="scrape"), tier="scrape")
    await cache.put("https://example.com/a", _make_scrape(markdown="interact"), tier="interact")

    scrape_hit = await cache.get("https://example.com/a", tier="scrape")
    interact_hit = await cache.get("https://example.com/a", tier="interact")

    assert scrape_hit is not None
    assert interact_hit is not None
    assert scrape_hit.markdown == "scrape"
    assert interact_hit.markdown == "interact"
    assert set(db_store) == {
        ("https://example.com/a", "scrape"),
        ("https://example.com/a", "interact"),
    }


@pytest.mark.asyncio
async def test_evict_without_tier_removes_scrape_and_interact_legs() -> None:
    cache, redis, _, db_store, bucket = _make_cache()

    scrape = await cache.put(
        "https://example.com/a", _make_scrape(markdown="scrape"), screenshot_bytes=b"scrape"
    )
    interact = await cache.put(
        "https://example.com/a",
        _make_scrape(markdown="interact"),
        screenshot_bytes=b"interact",
        tier="interact",
    )

    await cache.evict("https://example.com/a")

    assert await cache.get("https://example.com/a", tier="scrape") is None
    assert await cache.get("https://example.com/a", tier="interact") is None
    assert not db_store
    assert not redis.values
    assert scrape.storage_key is not None
    assert interact.storage_key is not None
    assert scrape.storage_key in bucket.deletes
    assert interact.storage_key in bucket.deletes


@pytest.mark.asyncio
async def test_put_replaces_existing_screenshot_blob() -> None:
    cache, _, _, db_store, bucket = _make_cache()
    first = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"old")
    second = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"new")

    assert first.storage_key is not None
    assert second.storage_key is not None
    assert first.storage_key != second.storage_key
    assert first.storage_key in bucket.deletes
    assert first.storage_key not in bucket.uploads
    assert bucket.uploads[second.storage_key] == b"new"
    row = next(iter(db_store.values()))
    assert row.screenshot_storage_key == second.storage_key


@pytest.mark.asyncio
async def test_put_without_screenshot_deletes_previous_screenshot_blob() -> None:
    cache, _, _, db_store, bucket = _make_cache()
    first = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"old")
    second = await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=None)

    assert first.storage_key is not None
    assert second.storage_key is None
    assert first.storage_key in bucket.deletes
    assert first.storage_key not in bucket.uploads
    row = next(iter(db_store.values()))
    assert row.screenshot_storage_key is None


@pytest.mark.asyncio
async def test_put_cleans_up_uploaded_blob_when_db_write_fails() -> None:
    cache, _, session, _, bucket = _make_cache(fail_commit=True)

    with pytest.raises(RuntimeError, match="db commit failed"):
        await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"png")

    assert session.rollback_calls == 1
    assert bucket.uploads == {}


@pytest.mark.asyncio
async def test_put_cleans_up_committed_row_and_blob_when_redis_write_fails() -> None:
    cache, redis, _, db_store, bucket = _make_cache()
    redis.fail_setex = True

    with pytest.raises(RuntimeError, match="redis write failed"):
        await cache.put("https://example.com/a", _make_scrape(), screenshot_bytes=b"png")

    assert not db_store
    assert not redis.values
    assert bucket.uploads == {}
