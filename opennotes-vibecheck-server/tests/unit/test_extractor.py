"""Unit tests for the shape-agnostic utterance extractor (TASK-1473.10).

Covers the new `extract_utterances` contract:
- Cache-ladder behavior (hit reuses, miss fetches all three formats + persists)
- Shape-agnostic output for all six `PageKind` values
- `scraped_at` is overwritten unconditionally after the agent returns
- `get_html()` and `get_screenshot()` tool surface (sanitized HTML, signed
  screenshot ImageUrl)
- Contract test: every `PageKind` value is mentioned in the system prompt

All tests fake the Firecrawl client, the scrape cache, and the Gemini agent
runner so no network calls fire. We assert on state (the returned
`UtterancesPayload`, the cache's recorded side-effects) rather than
interaction patterns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic_ai.messages import ImageUrl

from src.analyses.schemas import PageKind
from src.cache.scrape_cache import SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import FirecrawlClient, ScrapeMetadata, ScrapeResult
from src.utterances.extractor import (
    EXTRACTOR_SYSTEM_PROMPT,
    ExtractorDeps,
    _get_html_impl,
    _get_screenshot_impl,
    extract_utterances,
)
from src.utterances.schema import Utterance, UtterancesPayload

TARGET_URL = "https://example.com/article"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeFirecrawlClient:
    """Records scrape() calls and returns a preconfigured ScrapeResult."""

    def __init__(self, result: ScrapeResult | None = None) -> None:
        self._result = result
        self.scrape_calls: list[dict[str, Any]] = []

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        self.scrape_calls.append(
            {
                "url": url,
                "formats": list(formats),
                "only_main_content": only_main_content,
            }
        )
        if self._result is None:
            return ScrapeResult(
                markdown="# Default\n\ndefault body",
                html="<p>default</p>",
                metadata=ScrapeMetadata(sourceURL=url),
            )
        return self._result


class _FakeScrapeCache:
    """In-memory stand-in for SupabaseScrapeCache with tracked calls."""

    def __init__(self, cached: ScrapeResult | None = None) -> None:
        self._cached = cached
        self.get_calls: list[str] = []
        self.put_calls: list[tuple[str, ScrapeResult]] = []
        self.signed_url_result: str | None = (
            "https://fake.supabase.co/storage/v1/object/sign/"
            "vibecheck-screenshots/abc?token=xyz"
        )
        self.signed_url_calls: list[ScrapeResult] = []

    async def get(self, url: str) -> ScrapeResult | None:
        self.get_calls.append(url)
        return self._cached

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
    ) -> ScrapeResult:
        self.put_calls.append((url, scrape))
        return scrape

    async def signed_screenshot_url(self, scrape: ScrapeResult) -> str | None:
        self.signed_url_calls.append(scrape)
        return self.signed_url_result


class _FakeRunResult:
    def __init__(self, output: UtterancesPayload) -> None:
        self.output = output


@dataclass
class _FakeAgent:
    """Records prompts passed to run() and returns a fixed payload."""

    payload: UtterancesPayload
    prompts: list[str] = field(default_factory=list)

    def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
        """Stand-in decorator that no-ops tool registration."""
        if func is None:
            def _wrap(f: Any) -> Any:
                return f

            return _wrap
        return func

    async def run(self, user_prompt: str, *, deps: Any = None) -> _FakeRunResult:
        self.prompts.append(user_prompt)
        return _FakeRunResult(self.payload)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _scrape(
    *,
    markdown: str | None = "# Post\n\nBody.",
    html: str | None = "<p>body</p>",
    screenshot: str | None = None,
    source_url: str = TARGET_URL,
    title: str | None = "Post",
) -> ScrapeResult:
    return ScrapeResult(
        markdown=markdown,
        html=html,
        screenshot=screenshot,
        metadata=ScrapeMetadata(sourceURL=source_url, title=title),
    )


def _payload(
    *,
    page_kind: PageKind = PageKind.BLOG_POST,
    utterances: list[Utterance] | None = None,
    scraped_at: datetime | None = None,
    title: str | None = "Sample",
) -> UtterancesPayload:
    return UtterancesPayload(
        source_url="",
        scraped_at=scraped_at or datetime(2020, 1, 1, tzinfo=UTC),
        page_title=title,
        page_kind=page_kind,
        utterances=utterances
        or [Utterance(utterance_id=None, kind="post", text="the post body")],
    )


def _stub_agent(
    monkeypatch: pytest.MonkeyPatch, payload: UtterancesPayload
) -> _FakeAgent:
    fake = _FakeAgent(payload=payload)
    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None: fake,
    )
    return fake


async def _call(
    url: str,
    client: _FakeFirecrawlClient,
    cache: _FakeScrapeCache,
    settings: Settings,
) -> UtterancesPayload:
    """Thin typed adapter so tests don't need to cast at every call site."""
    return await extract_utterances(
        url,
        cast(FirecrawlClient, cast(object, client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Contract test — every PageKind is covered by the system prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page_kind", list(PageKind))
def test_all_pagekind_values_are_present_in_system_prompt(
    page_kind: PageKind,
) -> None:
    """Guard against future PageKind additions being silently ignored."""
    assert page_kind.value in EXTRACTOR_SYSTEM_PROMPT


def test_system_prompt_instructs_markdown_first_and_single_tool_call() -> None:
    """Tool-usage guidance is the only contract the prompt makes with tools."""
    prompt = EXTRACTOR_SYSTEM_PROMPT.lower()
    assert "markdown-first" in prompt
    assert "at most once" in prompt


# ---------------------------------------------------------------------------
# Cache ladder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_reuses_scrape_without_firecrawl_call(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    cached = _scrape(markdown="# cached\n\nbody from cache")
    client = _FakeFirecrawlClient()
    cache = _FakeScrapeCache(cached=cached)
    _stub_agent(monkeypatch, _payload())

    await _call(TARGET_URL, client, cache, settings)

    assert cache.get_calls == [TARGET_URL]
    assert client.scrape_calls == []
    assert cache.put_calls == []


@pytest.mark.asyncio
async def test_cache_miss_fetches_all_formats_and_persists(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fresh = _scrape(markdown="# fresh", html="<p>fresh</p>", screenshot="cdn://x")
    client = _FakeFirecrawlClient(result=fresh)
    cache = _FakeScrapeCache(cached=None)
    _stub_agent(monkeypatch, _payload())

    await _call(TARGET_URL, client, cache, settings)

    assert len(client.scrape_calls) == 1
    call = client.scrape_calls[0]
    assert call["url"] == TARGET_URL
    assert call["formats"] == ["markdown", "html", "screenshot@fullPage"]
    assert call["only_main_content"] is True
    assert len(cache.put_calls) == 1
    assert cache.put_calls[0][0] == TARGET_URL


# ---------------------------------------------------------------------------
# Shape-agnostic output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blog_post_with_comments_produces_root_post_plus_comment_utterances(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.BLOG_POST,
            utterances=[
                Utterance(utterance_id=None, kind="post", text="root post"),
                Utterance(
                    utterance_id=None, kind="comment", text="c1", author="alice"
                ),
                Utterance(
                    utterance_id=None, kind="comment", text="c2", author="bob"
                ),
            ],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    assert payload.page_kind == PageKind.BLOG_POST
    kinds = [u.kind for u in payload.utterances]
    assert kinds.count("post") == 1
    assert kinds.count("comment") == 2
    assert payload.utterances[0].kind == "post"


@pytest.mark.asyncio
async def test_forum_thread_sequential_posts_use_parent_ids(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.FORUM_THREAD,
            utterances=[
                Utterance(
                    utterance_id="op", kind="post", text="opening post", author="op"
                ),
                Utterance(
                    utterance_id="r1",
                    kind="reply",
                    text="first reply",
                    author="u1",
                    parent_id="op",
                ),
                Utterance(
                    utterance_id="r2",
                    kind="reply",
                    text="second reply",
                    author="u2",
                    parent_id="op",
                ),
            ],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    assert payload.page_kind == PageKind.FORUM_THREAD
    replies = [u for u in payload.utterances if u.kind == "reply"]
    assert all(r.parent_id == "op" for r in replies)


@pytest.mark.asyncio
async def test_hierarchical_thread_builds_tree_via_parent_ids(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.HIERARCHICAL_THREAD,
            utterances=[
                Utterance(utterance_id="root", kind="post", text="root"),
                Utterance(
                    utterance_id="a",
                    kind="reply",
                    text="child",
                    parent_id="root",
                ),
                Utterance(
                    utterance_id="a1",
                    kind="reply",
                    text="grandchild",
                    parent_id="a",
                ),
            ],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    by_id = {u.utterance_id: u for u in payload.utterances}
    assert by_id["a"].parent_id == "root"
    assert by_id["a1"].parent_id == "a"


@pytest.mark.asyncio
async def test_blog_index_returns_multiple_post_utterances(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.BLOG_INDEX,
            utterances=[
                Utterance(utterance_id=None, kind="post", text="entry one"),
                Utterance(utterance_id=None, kind="post", text="entry two"),
                Utterance(utterance_id=None, kind="post", text="entry three"),
            ],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    assert payload.page_kind == PageKind.BLOG_INDEX
    assert all(u.kind == "post" for u in payload.utterances)
    assert len(payload.utterances) == 3


@pytest.mark.asyncio
async def test_article_returns_single_post_utterance(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.ARTICLE,
            utterances=[
                Utterance(utterance_id=None, kind="post", text="the whole article"),
            ],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    assert payload.page_kind == PageKind.ARTICLE
    assert len(payload.utterances) == 1
    assert payload.utterances[0].kind == "post"


# ---------------------------------------------------------------------------
# scraped_at override (TASK-1471.23 source fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scraped_at_is_overwritten_after_agent_run(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    # Agent returns an ancient timestamp; extract_utterances must overwrite it
    # with the current UTC time regardless of whether it was None or set.
    stale = datetime(1990, 1, 1, tzinfo=UTC)
    _stub_agent(
        monkeypatch,
        _payload(scraped_at=stale),
    )

    before = datetime.now(UTC)
    payload = await _call(TARGET_URL, client, cache, settings)
    after = datetime.now(UTC)

    assert payload.scraped_at != stale
    assert payload.scraped_at.tzinfo is not None
    assert before <= payload.scraped_at <= after


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


def test_get_html_tool_returns_sanitized_html() -> None:
    """`<script>` contents are stripped; benign markup survives."""
    scrape = _scrape(
        html=(
            "<script>alert('x')</script>"
            "<style>.a { color: red; }</style>"
            "<p>keep me</p>"
        )
    )
    cache = _FakeScrapeCache()
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    html = _get_html_impl(deps)

    assert "<script" not in html
    assert "<style" not in html
    assert "<p>keep me</p>" in html


def test_get_html_tool_returns_empty_string_when_no_html() -> None:
    scrape = _scrape(html=None)
    cache = _FakeScrapeCache()
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    html = _get_html_impl(deps)

    assert html == ""


@pytest.mark.asyncio
async def test_get_screenshot_tool_returns_signed_url_imageurl() -> None:
    scrape = _scrape(screenshot="cdn://foo")
    cache = _FakeScrapeCache()
    cache.signed_url_result = "https://fake/signed?token=abc"
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    result = await _get_screenshot_impl(deps)

    assert isinstance(result, ImageUrl)
    assert result.url == "https://fake/signed?token=abc"
    assert cache.signed_url_calls == [scrape]


@pytest.mark.asyncio
async def test_get_screenshot_tool_returns_none_url_when_no_screenshot() -> None:
    """When no screenshot is persisted, the tool returns a sentinel ImageUrl.

    Agents receive a stub so they can continue from markdown without blowing
    up on a missing screenshot. Documented in the extractor module.
    """
    scrape = _scrape(screenshot=None)
    cache = _FakeScrapeCache()
    cache.signed_url_result = None
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    result = await _get_screenshot_impl(deps)

    assert result is None or (isinstance(result, ImageUrl) and result.url == "")


@pytest.mark.asyncio
async def test_signed_url_is_re_minted_on_each_screenshot_tool_call() -> None:
    """15-min TTL means repeated calls must re-sign, not cache."""
    scrape = _scrape(screenshot="cdn://foo")
    cache = _FakeScrapeCache()
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    await _get_screenshot_impl(deps)
    await _get_screenshot_impl(deps)

    assert len(cache.signed_url_calls) == 2
