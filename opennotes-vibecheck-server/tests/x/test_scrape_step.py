from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.cache.scrape_cache import CachedScrape
from src.config import Settings
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.jobs import orchestrator
from src.x.api import XApiAuthError, XConversation, XTweet


class _FakeFirecrawlClient:
    def __init__(self, scrape: ScrapeResult | None = None) -> None:
        self.scrape_result = scrape
        self.scrape_calls: list[str] = []

    async def scrape(self, url: str, **kwargs: Any) -> ScrapeResult:
        del kwargs
        self.scrape_calls.append(url)
        if self.scrape_result is None:
            raise AssertionError("firecrawl scrape should not run")
        return self.scrape_result


class _FakeScrapeCache:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], CachedScrape] = {}
        self.put_calls: list[tuple[str, str, ScrapeResult]] = []

    async def get(self, url: str, *, tier: str = "scrape") -> CachedScrape | None:
        return self.rows.get((url, tier))

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        *,
        tier: str = "scrape",
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        del screenshot_bytes
        self.put_calls.append((url, tier, scrape))
        cached = CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=scrape.raw_html,
            screenshot=scrape.screenshot,
            links=scrape.links,
            metadata=scrape.metadata,
            warning=scrape.warning,
            storage_key=None,
        )
        self.rows[(url, tier)] = cached
        return cached


def _conversation() -> XConversation:
    root = XTweet(
        id="100",
        text="Root",
        author_id="1",
        author_handle="alice",
        author_name="Alice",
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
        in_reply_to_status_id=None,
    )
    return XConversation(root=root, replies=[], raw_count=0, truncated=False)


@pytest.mark.asyncio
async def test_scrape_step_returns_cached_x_api_row_before_firecrawl() -> None:
    cache = _FakeScrapeCache()
    cache.rows[("https://x.com/alice/status/100", "x_api")] = CachedScrape(
        html="<article>X cached</article>",
        markdown="X cached",
        metadata=ScrapeMetadata(source_url="https://x.com/i/status/100"),
    )
    scrape_client = _FakeFirecrawlClient()

    result = await orchestrator._scrape_step(
        "https://x.com/alice/status/100",
        scrape_client,  # pyright: ignore[reportArgumentType]
        _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
        cache,  # pyright: ignore[reportArgumentType]
        settings=Settings(VIBECHECK_X_BEARER_TOKEN="token"),
    )

    assert result.html == "<article>X cached</article>"
    assert scrape_client.scrape_calls == []


@pytest.mark.asyncio
async def test_scrape_step_writes_x_api_tier_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_bearer(settings: Settings, http: object) -> str:
        del settings, http
        return "token"

    async def fake_fetch(post_id: str, **kwargs: object) -> XConversation:
        del kwargs
        assert post_id == "100"
        return _conversation()

    monkeypatch.setattr(orchestrator, "get_x_bearer", fake_bearer)
    monkeypatch.setattr(orchestrator, "fetch_x_conversation", fake_fetch)

    cache = _FakeScrapeCache()
    result = await orchestrator._scrape_step(
        "https://x.com/alice/status/100",
        _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
        _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
        cache,  # pyright: ignore[reportArgumentType]
        settings=Settings(VIBECHECK_X_BEARER_TOKEN="token"),
    )

    assert result.html is not None
    assert 'data-utterance-id="100"' in result.html
    assert cache.put_calls[0][0] == "https://x.com/alice/status/100"
    assert cache.put_calls[0][1] == "x_api"


@pytest.mark.asyncio
async def test_scrape_step_falls_through_to_firecrawl_when_x_auth_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_bearer(settings: Settings, http: object) -> str:
        del settings, http
        return "token"

    async def fake_fetch(post_id: str, **kwargs: object) -> XConversation:
        del post_id, kwargs
        raise XApiAuthError("bad token")

    monkeypatch.setattr(orchestrator, "get_x_bearer", fake_bearer)
    monkeypatch.setattr(orchestrator, "fetch_x_conversation", fake_fetch)

    firecrawl_scrape = ScrapeResult(
        html="<main>Firecrawl content</main>",
        markdown="Firecrawl content",
        metadata=ScrapeMetadata(source_url="https://x.com/alice/status/100"),
    )
    scrape_client = _FakeFirecrawlClient(firecrawl_scrape)
    cache = _FakeScrapeCache()

    result = await orchestrator._scrape_step(
        "https://x.com/alice/status/100",
        scrape_client,  # pyright: ignore[reportArgumentType]
        _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
        cache,  # pyright: ignore[reportArgumentType]
        settings=Settings(VIBECHECK_X_BEARER_TOKEN="token"),
    )

    assert result.markdown == "Firecrawl content"
    assert scrape_client.scrape_calls == ["https://x.com/alice/status/100"]
    assert all(tier != "x_api" for _, tier, _ in cache.put_calls)
