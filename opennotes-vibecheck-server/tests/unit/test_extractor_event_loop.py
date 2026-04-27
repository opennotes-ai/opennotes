"""Regression tests: sync BeautifulSoup parses must not block the event loop.

Without `asyncio.to_thread` wrappers, the post-agent `_sanitize_html` +
`attribute_media` calls in `extract_utterances` each parse the full page HTML
on the main thread. Under Cloud Run's single-CPU shape, a >300 KB parse can
take longer than the `/_healthz` liveness probe budget (period=10s,
timeout=3s, failureThreshold=3 -> 30s) and trip a SIGKILL — the silent-death
pattern documented in TASK-1474.23.

These tests assert the loop ticks repeatedly while the parse runs by spawning
a concurrent `await asyncio.sleep(...)` ticker. With the sync parses the
ticker count is ~1; with `asyncio.to_thread` wrapping it advances dozens of
times, proving the parse is no longer event-loop-blocking.

The full-stack path through `extract_utterances` exercises the two post-
agent call sites (`_sanitize_html` at extractor.py:180 and `attribute_media`
at extractor.py:181). The fake Gemini agent resolves immediately so the only
wall-time cost in the run is the two BeautifulSoup parses.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from src.analyses.schemas import PageKind
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import (
    FirecrawlClient,
    ScrapeMetadata,
    ScrapeResult,
)
from src.utterances.extractor import extract_utterances
from src.utterances.schema import Utterance, UtterancesPayload

TARGET_URL = "https://example.com/big-article"


def _build_large_html(num_blocks: int = 6000) -> str:
    """Build a synthetic >300 KB HTML page with many tags + anchors + images.

    The size + tag density together push pure-Python `html.parser` into a
    multi-hundred-millisecond parse under CPython, enough to swamp a 50ms
    ticker tick if the parse runs on the event loop. Each block contains a
    paragraph, an anchor and an image so `attribute_media`'s per-tag
    ancestor walk is exercised, not just the initial parse.
    """
    parts: list[str] = ["<html><body>"]
    for i in range(num_blocks):
        parts.append(
            f"<div class='block block-{i}'>"
            f"<p>Block {i} body text with some words to parse and process. "
            f"Lorem ipsum dolor sit amet consectetur adipiscing elit "
            f"sed do eiusmod tempor incididunt ut labore et dolore magna.</p>"
            f"<a href='https://example.com/link-{i}'>link {i}</a> "
            f"<img src='https://example.com/img-{i}.png' alt='image {i}'>"
            f"</div>"
        )
    parts.append("</body></html>")
    return "".join(parts)


class _FakeFirecrawlClient:
    def __init__(self, result: ScrapeResult) -> None:
        self._result = result

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        return self._result


class _FakeScrapeCache:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, ScrapeResult]] = []

    async def get(self, url: str) -> CachedScrape | None:
        return None

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        self.put_calls.append((url, scrape))
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

    async def signed_screenshot_url(
        self, scrape: CachedScrape | ScrapeResult
    ) -> str | None:
        return None


class _FakeRunResult:
    def __init__(self, output: UtterancesPayload) -> None:
        self.output = output


@dataclass
class _FakeAgent:
    payload: UtterancesPayload
    tool_registrations: list[tuple[str, Any]] = field(default_factory=list)

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


@pytest.mark.asyncio
async def test_extract_utterances_does_not_block_event_loop_on_large_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A >300 KB HTML parse must not starve a concurrent 50ms ticker.

    With sync `_sanitize_html` + `attribute_media` calls running directly on
    the loop, the ticker count would be ~1 because the loop is blocked for
    the full parse duration. After wrapping with `asyncio.to_thread`, the
    parses run on a worker thread and the loop continues advancing — the
    ticker should hit at least 5 ticks before the extract returns.
    """
    big_html = _build_large_html()
    assert len(big_html) > 300_000, "fixture must exceed 300 KB"

    post_text = "Block 0 body text with some words to parse and process."
    fresh = ScrapeResult(
        markdown=f"# Post\n\n{post_text}",
        html=big_html,
        metadata=ScrapeMetadata(source_url=TARGET_URL),
    )
    client = _FakeFirecrawlClient(result=fresh)
    cache = _FakeScrapeCache()

    payload = UtterancesPayload(
        source_url="",
        scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
        page_title="Big",
        page_kind=PageKind.ARTICLE,
        utterances=[Utterance(utterance_id=None, kind="post", text=post_text)],
    )
    fake_agent = _FakeAgent(payload=payload)
    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None, name=None: fake_agent,
    )

    tick_count = 0
    ticker_running = True

    async def ticker() -> None:
        nonlocal tick_count
        while ticker_running:
            tick_count += 1
            await asyncio.sleep(0.05)

    ticker_task = asyncio.create_task(ticker())

    try:
        await extract_utterances(
            TARGET_URL,
            cast(FirecrawlClient, cast(object, client)),
            cast(SupabaseScrapeCache, cast(object, cache)),
            settings=Settings(),
        )
    finally:
        ticker_running = False
        await ticker_task

    assert tick_count >= 5, (
        f"event loop ticker advanced only {tick_count} times during a "
        f"{len(big_html)}-byte HTML parse — sync BeautifulSoup parse is "
        "blocking the event loop. Wrap _sanitize_html and attribute_media "
        "in asyncio.to_thread (TASK-1474.23.04)."
    )


@pytest.mark.asyncio
async def test_get_html_tool_does_not_block_event_loop_on_large_html() -> None:
    """The `get_html` pydantic-ai tool must not block the loop.

    Per TASK-1474.23.04, the sync `def get_html` registered as an agent tool
    is the smoking-gun call site (5-minute mid-agent silences during Gemini
    tool calls). After fixing, it becomes `async def` calling
    `asyncio.to_thread(_get_html_impl, ctx.deps)` — same pattern as the
    other two sites.

    We invoke the registered tool directly from a fake agent's
    registration list and assert the loop ticks while it runs.
    """
    from src.utterances.extractor import ExtractorDeps, _register_tools

    big_html = _build_large_html()
    cached = CachedScrape(
        markdown="# Post",
        html=big_html,
        metadata=ScrapeMetadata(source_url=TARGET_URL),
        storage_key=None,
    )
    cache = _FakeScrapeCache()
    deps = ExtractorDeps(
        scrape=cached,
        scrape_cache=cast(SupabaseScrapeCache, cast(object, cache)),
    )

    fake_agent = _FakeAgent(
        payload=UtterancesPayload(
            source_url="",
            scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
            page_kind=PageKind.ARTICLE,
            utterances=[],
        )
    )
    _register_tools(cast(Any, fake_agent))
    get_html_tool = next(
        fn for name, fn in fake_agent.tool_registrations if name == "get_html"
    )

    @dataclass
    class _Ctx:
        deps: ExtractorDeps

    ctx = _Ctx(deps=deps)

    tick_count = 0
    ticker_running = True

    async def ticker() -> None:
        nonlocal tick_count
        while ticker_running:
            tick_count += 1
            await asyncio.sleep(0.05)

    ticker_task = asyncio.create_task(ticker())

    try:
        result = get_html_tool(ctx)
        if asyncio.iscoroutine(result):
            await result
    finally:
        ticker_running = False
        await ticker_task

    assert tick_count >= 5, (
        f"event loop ticker advanced only {tick_count} times while the "
        f"`get_html` tool parsed {len(big_html)} bytes — the tool is "
        "blocking the event loop. Convert it to `async def` and wrap the "
        "impl in `asyncio.to_thread` (TASK-1474.23.04)."
    )
