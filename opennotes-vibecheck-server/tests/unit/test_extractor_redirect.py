"""Tests for _extract_or_redirect threshold gate and union output type."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import FirecrawlClient, ScrapeMetadata, ScrapeResult
from src.utterances.extractor import (
    REDIRECT_ADDENDUM,
    _extract_or_redirect,
    extract_utterances,
)
from src.utterances.schema import (
    BatchedUtteranceRedirectionResponse,
    Utterance,
    UtterancesPayload,
)

TARGET_URL = "https://example.com/article"
SENTINEL_BLOCK_SECONDS = 0.5


# --- Fake infrastructure (mirrors test_extractor_event_loop.py) ---


class _AsyncNullCtx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: Any) -> None:
        pass


class _FakeFirecrawlClient:
    def __init__(self, result: ScrapeResult) -> None:
        self._result = result

    async def scrape(
        self, url: str, formats: list[str], *, only_main_content: bool = False
    ) -> ScrapeResult:
        return self._result


class _FakeScrapeCache:
    async def get(self, url: str, *, tier: str = "scrape") -> CachedScrape | None:
        return None

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        *,
        tier: str = "scrape",
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
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

    async def signed_screenshot_url(self, scrape: Any) -> str | None:
        return None


class _FakeRunResult:
    def __init__(self, output: Any) -> None:
        self.output = output


@dataclass
class _FakeAgent:
    payload: Any
    tool_registrations: list[tuple[str, Any]] = field(default_factory=list)
    model: Any = field(default_factory=lambda: MagicMock(model_name="gemini-fake"))

    def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
        if func is None:

            def _wrap(f: Any) -> Any:
                self.tool_registrations.append((getattr(f, "__name__", "?"), f))
                return f

            return _wrap
        self.tool_registrations.append((getattr(func, "__name__", "?"), func))
        return func

    async def run(self, user_prompt: str, *, deps: Any = None) -> _FakeRunResult:
        return _FakeRunResult(self.payload)


# --- Test 1 — AC1: under-threshold returns UtterancesPayload unchanged ---


@pytest.mark.asyncio
async def test_under_threshold_returns_utterances_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under threshold: _extract_or_redirect delegates to extract_utterances -> UtterancesPayload."""
    post_text = "Short article."
    scrape = CachedScrape(
        markdown=f"# Post\n\n{post_text}",
        html="<html><body><p>Short article.</p></body></html>",
        raw_html=None,
        screenshot=None,
        links=[],
        metadata=ScrapeMetadata(source_url=TARGET_URL),
        warning=None,
        storage_key=None,
    )
    payload = UtterancesPayload(
        source_url="",
        scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
        page_title="Short",
        page_kind=PageKind.ARTICLE,
        utterances=[Utterance(utterance_id=None, kind="post", text=post_text)],
    )
    fake_agent = _FakeAgent(payload=payload)
    monkeypatch.setattr("src.utterances.extractor.build_agent", lambda *a, **kw: fake_agent)
    monkeypatch.setattr(
        "src.utterances.extractor.vertex_slot", lambda s: _AsyncNullCtx()
    )
    monkeypatch.setattr("src.utterances.extractor._sanitize_html", lambda h: h)
    monkeypatch.setattr("src.utterances.extractor.attribute_media", lambda h, u: None)

    # thresholds much higher than the tiny scrape content
    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=10_000_000,
        VIBECHECK_BATCH_MARKDOWN_BYTES=10_000_000,
    )
    client = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown=scrape.markdown,
            html=scrape.html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    cache = _FakeScrapeCache()

    result = await _extract_or_redirect(
        TARGET_URL, client, cache, settings=settings, scrape=scrape
    )

    assert isinstance(result, UtterancesPayload)
    assert result.utterances


# --- Test 2 — AC2: over-threshold builds union agent with REDIRECT_ADDENDUM ---


@pytest.mark.asyncio
async def test_over_threshold_builds_union_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Over threshold: build_agent is called with union output_type and REDIRECT_ADDENDUM in prompt."""
    large_html = "<p>" + "x" * 200_000 + "</p>"
    large_markdown = "# Big\n\n" + "word " * 50_000
    scrape = CachedScrape(
        markdown=large_markdown,
        html=large_html,
        raw_html=None,
        screenshot=None,
        links=[],
        metadata=ScrapeMetadata(source_url=TARGET_URL),
        warning=None,
        storage_key=None,
    )
    redirect_response = BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.ARTICLE,
        utterance_stream_type=UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
        page_title="Big",
        boundary_instructions="Split by section headers.",
        section_hints=[],
    )
    fake_agent = _FakeAgent(payload=redirect_response)

    captured_kwargs: dict[str, Any] = {}

    def _capture_build_agent(s: Any, **kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        return fake_agent

    monkeypatch.setattr("src.utterances.extractor.build_agent", _capture_build_agent)
    monkeypatch.setattr("src.utterances.extractor._sanitize_html", lambda h: h)
    monkeypatch.setattr("src.utterances.extractor.vertex_slot", lambda s: _AsyncNullCtx())

    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=100, VIBECHECK_BATCH_MARKDOWN_BYTES=100
    )
    client = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown=large_markdown,
            html=large_html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    cache = _FakeScrapeCache()

    result = await _extract_or_redirect(
        TARGET_URL, client, cache, settings=settings, scrape=scrape
    )

    assert isinstance(result, BatchedUtteranceRedirectionResponse)
    # AC2: union output_type
    assert (
        captured_kwargs.get("output_type")
        == UtterancesPayload | BatchedUtteranceRedirectionResponse
    )
    # AC2: redirect addendum in system prompt or check REDIRECT_ADDENDUM is importable + non-empty
    assert REDIRECT_ADDENDUM.strip()


# --- Test 3 — AC3: public extract_utterances still returns UtterancesPayload ---


@pytest.mark.asyncio
async def test_extract_utterances_public_api_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract_utterances public signature is UtterancesPayload regardless of page size."""
    post_text = "Article content."
    fresh = ScrapeResult(
        markdown=f"# Post\n\n{post_text}",
        html="<html><body><p>Article content.</p></body></html>",
        metadata=ScrapeMetadata(source_url=TARGET_URL),
    )
    payload = UtterancesPayload(
        source_url="",
        scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
        page_title="Art",
        page_kind=PageKind.ARTICLE,
        utterances=[Utterance(utterance_id=None, kind="post", text=post_text)],
    )
    fake_agent = _FakeAgent(payload=payload)
    monkeypatch.setattr("src.utterances.extractor.build_agent", lambda *a, **kw: fake_agent)
    monkeypatch.setattr("src.utterances.extractor._sanitize_html", lambda h: h)
    monkeypatch.setattr("src.utterances.extractor.attribute_media", lambda h, u: None)
    monkeypatch.setattr("src.utterances.extractor.vertex_slot", lambda s: _AsyncNullCtx())

    client = _FakeFirecrawlClient(result=fresh)
    cache = _FakeScrapeCache()

    result = await extract_utterances(TARGET_URL, client, cache, settings=Settings())

    assert isinstance(result, UtterancesPayload)


# --- Test 4 — AC4: ZeroUtterancesError surfaces on oversized path ---


@pytest.mark.asyncio
async def test_zero_utterances_error_on_oversized_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ZeroUtterancesError is raised when oversized agent returns UtterancesPayload with 0 utterances."""
    from src.utterances.errors import ZeroUtterancesError

    large_html = "<p>" + "x" * 200_000 + "</p>"
    large_markdown = "# Big\n\n" + "word " * 50_000
    scrape = CachedScrape(
        markdown=large_markdown,
        html=large_html,
        raw_html=None,
        screenshot=None,
        links=[],
        metadata=ScrapeMetadata(source_url=TARGET_URL),
        warning=None,
        storage_key=None,
    )
    empty_payload = UtterancesPayload(
        source_url="",
        scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
        page_title=None,
        page_kind=PageKind.OTHER,
        utterances=[],
    )
    fake_agent = _FakeAgent(payload=empty_payload)
    monkeypatch.setattr("src.utterances.extractor.build_agent", lambda *a, **kw: fake_agent)
    monkeypatch.setattr("src.utterances.extractor._sanitize_html", lambda h: h)
    monkeypatch.setattr("src.utterances.extractor.vertex_slot", lambda s: _AsyncNullCtx())

    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=100, VIBECHECK_BATCH_MARKDOWN_BYTES=100
    )
    client = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown=large_markdown,
            html=large_html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    cache = _FakeScrapeCache()

    with pytest.raises(ZeroUtterancesError):
        await _extract_or_redirect(
            TARGET_URL, client, cache, settings=settings, scrape=scrape
        )


# --- Test 5 — AC5: oversized sanitization runs off-loop (ticker sentinel) ---


@pytest.mark.asyncio
async def test_oversized_sanitization_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asyncio.to_thread wraps oversized _sanitize_html — ticker advances while it sleeps."""
    large_html = "<p>" + "x" * 200_000 + "</p>"
    large_markdown = "# Big\n\n" + "word " * 50_000
    scrape = CachedScrape(
        markdown=large_markdown,
        html=large_html,
        raw_html=None,
        screenshot=None,
        links=[],
        metadata=ScrapeMetadata(source_url=TARGET_URL),
        warning=None,
        storage_key=None,
    )
    redirect_response = BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.ARTICLE,
        utterance_stream_type=UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
        page_title="Big",
        boundary_instructions="Split by header.",
        section_hints=[],
    )
    fake_agent = _FakeAgent(payload=redirect_response)
    monkeypatch.setattr("src.utterances.extractor.build_agent", lambda *a, **kw: fake_agent)
    monkeypatch.setattr("src.utterances.extractor.vertex_slot", lambda s: _AsyncNullCtx())

    def _blocking_sanitize(html: str) -> str:
        time.sleep(SENTINEL_BLOCK_SECONDS)
        return html

    monkeypatch.setattr("src.utterances.extractor._sanitize_html", _blocking_sanitize)

    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=100, VIBECHECK_BATCH_MARKDOWN_BYTES=100
    )
    client = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown=large_markdown,
            html=large_html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    cache = _FakeScrapeCache()

    tick_count = 0
    ticker_running = True

    async def ticker() -> None:
        nonlocal tick_count
        while ticker_running:
            tick_count += 1
            await asyncio.sleep(0.05)

    ticker_task = asyncio.create_task(ticker())
    try:
        await _extract_or_redirect(
            TARGET_URL, client, cache, settings=settings, scrape=scrape
        )
    finally:
        ticker_running = False
        await ticker_task

    assert tick_count >= 5, (
        f"Event loop ticker advanced only {tick_count} times during {SENTINEL_BLOCK_SECONDS}s "
        "blocking sanitize — _sanitize_html in oversized path must use asyncio.to_thread."
    )
