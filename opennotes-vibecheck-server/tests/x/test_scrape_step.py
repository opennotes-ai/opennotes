from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

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
        self.put_calls: list[tuple[str, str, ScrapeResult, bytes | None]] = []

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
        self.put_calls.append((url, tier, scrape, screenshot_bytes))
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

    async def fake_og(url: str, **kwargs: object) -> str:
        del kwargs
        assert url == "https://x.com/i/status/100"
        return "https://pbs.twimg.com/media/post.jpg"

    async def fake_thumbnail(image_url: str, **kwargs: object) -> bytes:
        del kwargs
        assert image_url == "https://pbs.twimg.com/media/post.jpg"
        return b"png-thumbnail"

    monkeypatch.setattr(orchestrator, "get_x_bearer", fake_bearer)
    monkeypatch.setattr(orchestrator, "fetch_x_conversation", fake_fetch)
    monkeypatch.setattr(orchestrator, "fetch_x_og_image_url", fake_og)
    monkeypatch.setattr(orchestrator, "materialize_og_image_png", fake_thumbnail)

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
    assert cache.put_calls[0][3] == b"png-thumbnail"


@pytest.mark.asyncio
async def test_scrape_step_writes_x_api_tier_without_thumbnail_on_og_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_bearer(settings: Settings, http: object) -> str:
        del settings, http
        return "token"

    async def fake_fetch(post_id: str, **kwargs: object) -> XConversation:
        del post_id, kwargs
        return _conversation()

    async def fake_og(url: str, **kwargs: object) -> None:
        del url, kwargs

    monkeypatch.setattr(orchestrator, "get_x_bearer", fake_bearer)
    monkeypatch.setattr(orchestrator, "fetch_x_conversation", fake_fetch)
    monkeypatch.setattr(orchestrator, "fetch_x_og_image_url", fake_og)

    cache = _FakeScrapeCache()
    result = await orchestrator._scrape_step(
        "https://x.com/alice/status/100",
        _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
        _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
        cache,  # pyright: ignore[reportArgumentType]
        settings=Settings(VIBECHECK_X_BEARER_TOKEN="token"),
    )

    assert result.html is not None
    assert cache.put_calls[0][1] == "x_api"
    assert cache.put_calls[0][3] is None


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

    async def fail_og_fetch(url: str, **kwargs: object) -> None:
        del url, kwargs
        raise AssertionError("og fetch should not run")

    monkeypatch.setattr(orchestrator, "fetch_x_og_image_url", fail_og_fetch)

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
    assert all(tier != "x_api" for _, tier, _, _ in cache.put_calls)


@pytest.mark.asyncio
async def test_scrape_step_logs_when_x_credentials_are_missing(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_bearer(settings: Settings, http: object) -> str | None:
        del settings, http
        return None

    monkeypatch.setattr(orchestrator, "get_x_bearer", fake_bearer)

    firecrawl_scrape = ScrapeResult(
        html="<main>Firecrawl content</main>",
        markdown="Firecrawl content",
        metadata=ScrapeMetadata(source_url="https://x.com/alice/status/100"),
    )
    scrape_client = _FakeFirecrawlClient(firecrawl_scrape)
    cache = _FakeScrapeCache()

    with caplog.at_level("INFO", logger="src.jobs.orchestrator"):
        result = await orchestrator._scrape_step(
            "https://x.com/alice/status/100",
            scrape_client,  # pyright: ignore[reportArgumentType]
            _FakeFirecrawlClient(),  # pyright: ignore[reportArgumentType]
            cache,  # pyright: ignore[reportArgumentType]
            settings=Settings(),
        )

    assert result.markdown == "Firecrawl content"
    assert scrape_client.scrape_calls == ["https://x.com/alice/status/100"]
    matching_records = [
        record
        for record in caplog.records
        if record.message == "x api scrape path skipped; no credentials available"
    ]
    assert len(matching_records) == 1
    record = cast(Any, matching_records[0])
    assert record.platform == "x"
    assert record.platform_outcome == "x_api_fallthrough_no_bearer"
    assert record.post_id == "100"
    assert record.url == "https://x.com/alice/status/100"
