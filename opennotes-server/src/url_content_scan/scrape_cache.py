from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import ConfigDict, Field

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.url_content_scan.html_sanitize import strip_noise
from src.url_content_scan.models import UrlScanScrape
from src.url_content_scan.normalize import canonical_cache_key
from src.url_content_scan.screenshot_store import ScreenshotStore

logger = logging.getLogger(__name__)

ScrapeTier = str
_BODY_TTL = timedelta(hours=72)
_SIGNED_URL_TTL = timedelta(minutes=15)
_KNOWN_TIERS: tuple[ScrapeTier, ...] = ("scrape", "interact")


class RedisLike(Protocol):
    async def get(self, key: str) -> bytes | str | None: ...
    async def setex(self, key: str, ttl: int, value: bytes) -> bool: ...
    async def delete(self, key: str) -> int: ...


class SessionLike(Protocol):
    async def get(
        self, model: type[UrlScanScrape], key: tuple[str, str]
    ) -> UrlScanScrape | None: ...
    async def merge(self, row: UrlScanScrape) -> UrlScanScrape: ...
    async def delete(self, row: UrlScanScrape) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SessionFactoryLike(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[SessionLike]: ...


class CachedScrape(ScrapeResult):
    storage_key: str | None = Field(default=None)
    model_config = ConfigDict(populate_by_name=True)


class ScrapeCache:
    def __init__(
        self,
        *,
        redis_client: RedisLike,
        session_factory: SessionFactoryLike,
        screenshot_store: ScreenshotStore,
        ttl: timedelta = _BODY_TTL,
    ) -> None:
        self._redis = redis_client
        self._session_factory = session_factory
        self._screenshot_store = screenshot_store
        self._ttl = ttl
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def get(self, url: str, *, tier: ScrapeTier = "scrape") -> CachedScrape | None:
        normalized_url = canonical_cache_key(url)
        async with self._session_factory() as session:
            row = await session.get(UrlScanScrape, (normalized_url, tier))
        if row is None or row.expires_at <= datetime.now(UTC):
            return None

        body = await self._read_body(normalized_url, tier)
        if body is None:
            return None

        metadata = ScrapeMetadata(
            title=row.page_title,
            source_url=row.source_url,
        )
        return CachedScrape(
            markdown=body.get("markdown"),
            html=body.get("html"),
            metadata=metadata,
            storage_key=row.screenshot_storage_key,
        )

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
        *,
        tier: ScrapeTier = "scrape",
    ) -> CachedScrape:
        normalized_url = canonical_cache_key(url)
        async with self._locks[normalized_url]:
            return await self._put_locked(
                normalized_url,
                url,
                scrape,
                screenshot_bytes,
                tier=tier,
            )

    async def _put_locked(
        self,
        normalized_url: str,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None,
        *,
        tier: ScrapeTier,
    ) -> CachedScrape:
        expires_at = datetime.now(UTC) + self._ttl
        storage_key = None
        if screenshot_bytes is not None:
            storage_key = await self._screenshot_store.upload(
                self._storage_key_for(normalized_url, tier),
                screenshot_bytes,
            )

        session: SessionLike | None = None
        try:
            async with self._session_factory() as session:
                row = UrlScanScrape(
                    normalized_url=normalized_url,
                    tier=tier,
                    source_url=scrape.metadata.source_url
                    if scrape.metadata and scrape.metadata.source_url
                    else url,
                    host=urlparse(normalized_url).netloc,
                    page_kind="other",
                    page_title=scrape.metadata.title if scrape.metadata else None,
                    screenshot_storage_key=storage_key,
                    scraped_at=datetime.now(UTC),
                    expires_at=expires_at,
                )
                await session.merge(row)
                await session.commit()
        except Exception:
            try:
                if session is not None:
                    await session.rollback()
            except Exception:
                logger.warning("scrape cache rollback failed", exc_info=True)
            await self._cleanup_uploaded_blob(storage_key)
            raise

        ttl_seconds = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
        await self._redis.setex(
            self._redis_key(normalized_url, tier),
            ttl_seconds,
            json.dumps(
                {
                    "markdown": scrape.markdown,
                    "html": strip_noise(scrape.html),
                }
            ).encode("utf-8"),
        )

        return CachedScrape(
            markdown=scrape.markdown,
            html=strip_noise(scrape.html),
            metadata=scrape.metadata,
            warning=scrape.warning,
            links=scrape.links,
            actions=scrape.actions,
            raw_html=scrape.raw_html,
            storage_key=storage_key,
        )

    async def signed_screenshot_url(self, cached: CachedScrape) -> str | None:
        if not cached.storage_key:
            return None
        return await self._screenshot_store.sign_url(cached.storage_key, ttl=_SIGNED_URL_TTL)

    async def evict(self, url: str, *, tier: ScrapeTier | None = None) -> None:
        normalized_url = canonical_cache_key(url)
        async with self._locks[normalized_url]:
            tiers = _KNOWN_TIERS if tier is None else (tier,)
            for item_tier in tiers:
                await self._evict_tier(normalized_url, item_tier)

    async def _evict_tier(self, normalized_url: str, tier: ScrapeTier) -> None:
        await self._redis.delete(self._redis_key(normalized_url, tier))
        storage_key: str | None = None
        async with self._session_factory() as session:
            row = await session.get(UrlScanScrape, (normalized_url, tier))
            if row is not None:
                storage_key = row.screenshot_storage_key
                await session.delete(row)
                await session.commit()

        if storage_key is None:
            return
        try:
            await self._screenshot_store.delete(storage_key)
        except Exception:
            logger.warning(
                "best-effort screenshot delete failed for %s", storage_key, exc_info=True
            )

    async def _read_body(
        self, normalized_url: str, tier: ScrapeTier
    ) -> dict[str, str | None] | None:
        raw = await self._redis.get(self._redis_key(normalized_url, tier))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        markdown = payload.get("markdown")
        html = payload.get("html")
        return {
            "markdown": markdown if isinstance(markdown, str) or markdown is None else None,
            "html": html if isinstance(html, str) or html is None else None,
        }

    async def _cleanup_uploaded_blob(self, storage_key: str | None) -> None:
        if storage_key is None:
            return
        try:
            await self._screenshot_store.delete(storage_key)
        except Exception:
            logger.warning(
                "best-effort screenshot cleanup failed for %s", storage_key, exc_info=True
            )

    @staticmethod
    def _redis_key(normalized_url: str, tier: ScrapeTier) -> str:
        digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
        return f"url_scan:scrape:{digest}:{tier}"

    @staticmethod
    def _storage_key_for(normalized_url: str, tier: ScrapeTier) -> str:
        digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]
        return f"url-content-scan/{tier}/{digest}-{uuid4().hex}.png"
