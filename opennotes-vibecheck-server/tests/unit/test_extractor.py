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
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ImageUrl

from src.analyses.schemas import PageKind
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import (
    FirecrawlClient,
    FirecrawlError,
    ScrapeMetadata,
    ScrapeResult,
)
from src.services.gemini_agent import google_vertex_model_name
from src.utterances.errors import (
    TransientExtractionError,
    UtteranceExtractionError,
)
from src.utterances.extractor import (
    EXTRACTOR_SYSTEM_PROMPT,
    ExtractorDeps,
    ZeroUtterancesError,
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
                metadata=ScrapeMetadata(source_url=url),
            )
        return self._result


class _FakeScrapeCache:
    """In-memory stand-in for SupabaseScrapeCache with tracked calls.

    Matches the production contract from `SupabaseScrapeCache`:
    `get()` returns `CachedScrape | None`, `put()` returns `CachedScrape`
    (carrying a `storage_key` when a screenshot was uploaded), and
    `signed_screenshot_url()` signs off the snapshotted key.
    """

    def __init__(
        self,
        cached: CachedScrape | None = None,
        *,
        put_storage_key: str | None = "put-key-default",
    ) -> None:
        self._cached = cached
        self._put_storage_key = put_storage_key
        self.get_calls: list[str] = []
        self.put_calls: list[tuple[str, ScrapeResult]] = []
        self.signed_url_result: str | None = (
            "https://storage.googleapis.com/test-vibecheck-screenshots/abc?X-Goog-Expires=900"
        )
        self.signed_url_calls: list[CachedScrape | ScrapeResult] = []

    async def get(self, url: str, *, tier: str = "scrape") -> CachedScrape | None:
        self.get_calls.append(url)
        return self._cached

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        *,
        tier: str = "scrape",
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        self.put_calls.append((url, scrape))
        # Match production: `put()` returns a `CachedScrape` carrying the
        # storage_key assigned at upload time. If no screenshot would have
        # been uploaded (scrape.screenshot is falsy), mint no key.
        key = self._put_storage_key if scrape.screenshot else None
        return CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=scrape.raw_html,
            screenshot=scrape.screenshot,
            links=scrape.links,
            metadata=scrape.metadata,
            warning=scrape.warning,
            storage_key=key,
        )

    async def signed_screenshot_url(self, scrape: CachedScrape | ScrapeResult) -> str | None:
        self.signed_url_calls.append(scrape)
        # Mirror the production contract — sign only when a storage_key is
        # attached to the passed-in scrape; bare ScrapeResults return None.
        key = getattr(scrape, "storage_key", None)
        if not isinstance(key, str) or not key:
            return None
        return self.signed_url_result


class _FakeRunResult:
    def __init__(self, output: UtterancesPayload) -> None:
        self.output = output


class _FakeModel:
    model_name = "gemini-fake-from-agent"


@dataclass
class _FakeAgent:
    """Records prompts passed to run() and tool registrations.

    `tool_registrations` captures each `(name, callable)` pair that
    `_register_tools` attaches so tests can assert the extractor actually
    wires both `get_html` and `get_screenshot` — a previous no-op
    `tool()` stand-in let a silent deletion of `_register_tools(agent)`
    in production slip past the test suite (codex W3 P2-8).
    """

    payload: UtterancesPayload
    prompts: list[str] = field(default_factory=list)
    tool_registrations: list[tuple[str, Any]] = field(default_factory=list)
    model: Any = field(default_factory=_FakeModel)

    def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
        """Spy decorator. Supports both `@agent.tool` and `@agent.tool(...)`."""
        if func is None:

            def _wrap(f: Any) -> Any:
                self.tool_registrations.append((getattr(f, "__name__", "?"), f))
                return f

            return _wrap
        self.tool_registrations.append((getattr(func, "__name__", "?"), func))
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
        metadata=ScrapeMetadata(source_url=source_url, title=title),
    )


def _cached_scrape(
    *,
    storage_key: str | None = "cached-storage-key",
    markdown: str | None = "# Cached\n\nFrom cache.",
    html: str | None = "<p>cached</p>",
    screenshot: str | None = None,
    source_url: str = TARGET_URL,
    title: str | None = "Cached",
) -> CachedScrape:
    return CachedScrape(
        markdown=markdown,
        html=html,
        screenshot=screenshot,
        metadata=ScrapeMetadata(source_url=source_url, title=title),
        storage_key=storage_key,
    )


def _payload(
    *,
    page_kind: PageKind = PageKind.BLOG_POST,
    utterances: list[Utterance] | None = None,
    scraped_at: datetime | None = None,
    title: str | None = "Sample",
) -> UtterancesPayload:
    # Distinguish "caller didn't pass utterances" (None → default to one
    # post utterance) from "caller explicitly passed []" (empty list →
    # used verbatim, drives the ZeroUtterancesError path).
    if utterances is None:
        utterances = [Utterance(utterance_id=None, kind="post", text="the post body")]
    return UtterancesPayload(
        source_url="",
        scraped_at=scraped_at or datetime(2020, 1, 1, tzinfo=UTC),
        page_title=title,
        page_kind=page_kind,
        utterances=utterances,
    )


def _stub_agent(monkeypatch: pytest.MonkeyPatch, payload: UtterancesPayload) -> _FakeAgent:
    fake = _FakeAgent(payload=payload)
    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None, name=None, tier="fast": fake,
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
# Fix D (codex W3 P2-8) — _register_tools actually wires the tool surface
#
# Previously `_FakeAgent.tool()` was a no-op, so a production refactor that
# dropped `_register_tools(agent)` would slip past every test in this
# module. The spy variant records registrations so we can assert them.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_utterances_registers_both_tools_on_agent(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """Both `get_html` and `get_screenshot` must be decorated onto the agent
    during extractor setup. The spy records each registration so a silent
    removal of `_register_tools(agent)` fails loudly.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    fake_agent = _stub_agent(monkeypatch, _payload())

    await _call(TARGET_URL, client, cache, settings)

    names = [name for name, _f in fake_agent.tool_registrations]
    assert "get_html" in names
    assert "get_screenshot" in names


# ---------------------------------------------------------------------------
# Cache ladder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_reuses_scrape_without_firecrawl_call(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    cached = _cached_scrape(markdown="# cached\n\nbody from cache")
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
# Fix A (codex W3 P1-2) — cache-miss must thread CachedScrape (with storage_key)
# into the agent's deps so get_screenshot() can mint a signed URL on first run.
# Previously _get_or_scrape returned the bare ScrapeResult, dropping the
# storage_key that cache.put() had just assigned — get_screenshot returned None.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_then_get_screenshot_returns_signed_url(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """After a miss → firecrawl → put() round-trip, the agent's
    `get_screenshot` tool must receive a scrape carrying the newly minted
    `storage_key` so `signed_screenshot_url()` can sign it.
    """
    fresh = _scrape(markdown="# fresh", screenshot="cdn://abc")
    client = _FakeFirecrawlClient(result=fresh)
    cache = _FakeScrapeCache(cached=None, put_storage_key="minted-key-123")
    # Capture the deps the extractor hands into agent.run so we can assert
    # on the .scrape payload the tool would see.
    captured_deps: dict[str, Any] = {}

    fake_agent = _FakeAgent(payload=_payload())

    original_run = fake_agent.run

    async def capturing_run(user_prompt: str, *, deps: Any = None) -> _FakeRunResult:
        captured_deps["deps"] = deps
        return await original_run(user_prompt, deps=deps)

    fake_agent.run = capturing_run  # pyright: ignore[reportAttributeAccessIssue]
    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None, name=None: fake_agent,
    )

    await _call(TARGET_URL, client, cache, settings)

    deps = captured_deps["deps"]
    assert isinstance(deps, ExtractorDeps)
    # After the fix: deps.scrape must be a CachedScrape carrying storage_key.
    assert isinstance(deps.scrape, CachedScrape)
    assert deps.scrape.storage_key == "minted-key-123"

    # And the tool itself must successfully mint a signed URL.
    result = await _get_screenshot_impl(deps)
    assert isinstance(result, ImageUrl)


@pytest.mark.asyncio
async def test_cache_hit_preserves_storage_key_through_tool_call(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A cache hit produces a CachedScrape with a storage_key. The agent
    must receive that exact CachedScrape in deps so tool calls sign off the
    snapshotted key without re-querying the DB.
    """
    cached = _cached_scrape(storage_key="cached-key-xyz", screenshot=None)
    client = _FakeFirecrawlClient()
    cache = _FakeScrapeCache(cached=cached)

    captured_deps: dict[str, Any] = {}

    fake_agent = _FakeAgent(payload=_payload())
    original_run = fake_agent.run

    async def capturing_run(user_prompt: str, *, deps: Any = None) -> _FakeRunResult:
        captured_deps["deps"] = deps
        return await original_run(user_prompt, deps=deps)

    fake_agent.run = capturing_run  # pyright: ignore[reportAttributeAccessIssue]
    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None, name=None: fake_agent,
    )

    await _call(TARGET_URL, client, cache, settings)

    deps = captured_deps["deps"]
    assert isinstance(deps, ExtractorDeps)
    assert isinstance(deps.scrape, CachedScrape)
    assert deps.scrape.storage_key == "cached-key-xyz"
    # No firecrawl, no put — cache hit path.
    assert client.scrape_calls == []
    assert cache.put_calls == []


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
                Utterance(utterance_id=None, kind="comment", text="c1", author="alice"),
                Utterance(utterance_id=None, kind="comment", text="c2", author="bob"),
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
                Utterance(utterance_id="op", kind="post", text="opening post", author="op"),
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
        html=("<script>alert('x')</script><style>.a { color: red; }</style><p>keep me</p>")
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
    scrape = _cached_scrape(screenshot="cdn://foo", storage_key="k")
    cache = _FakeScrapeCache()
    cache.signed_url_result = "https://fake/signed?token=abc"
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    result = await _get_screenshot_impl(deps)

    assert isinstance(result, ImageUrl)
    assert result.url == "https://fake/signed?token=abc"
    assert cache.signed_url_calls == [scrape]


@pytest.mark.asyncio
async def test_get_screenshot_tool_returns_none_url_when_no_screenshot() -> None:
    """When no screenshot is persisted (no storage_key), the tool returns None.

    Agents receive None so they can continue from markdown without blowing
    up on a missing screenshot. Documented in the extractor module.
    """
    scrape = _cached_scrape(screenshot=None, storage_key=None)
    cache = _FakeScrapeCache()
    cache.signed_url_result = None
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    result = await _get_screenshot_impl(deps)

    assert result is None or (isinstance(result, ImageUrl) and result.url == "")


@pytest.mark.asyncio
async def test_signed_url_is_re_minted_on_each_screenshot_tool_call() -> None:
    """15-min TTL means repeated calls must re-sign, not cache."""
    scrape = _cached_scrape(screenshot="cdn://foo", storage_key="k")
    cache = _FakeScrapeCache()
    deps = ExtractorDeps(scrape=scrape, scrape_cache=cache)  # pyright: ignore[reportArgumentType]

    await _get_screenshot_impl(deps)
    await _get_screenshot_impl(deps)

    assert len(cache.signed_url_calls) == 2


# ---------------------------------------------------------------------------
# Media attribution integration (TASK-1474.05)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_utterances_populates_media_from_html(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """HTML with inline images + links populates utterance media lists."""
    post_text = "The post body content here."
    html = (
        "<div>"
        f"<p>{post_text}</p>"
        '<img src="https://example.com/post.png">'
        '<a href="https://example.com/link1">read more</a>'
        "</div>"
    )
    fresh = _scrape(markdown=f"# Post\n\n{post_text}", html=html)
    client = _FakeFirecrawlClient(result=fresh)
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.BLOG_POST,
            utterances=[Utterance(utterance_id=None, kind="post", text=post_text)],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    post_utterance = payload.utterances[0]
    assert "https://example.com/post.png" in post_utterance.mentioned_images
    assert "https://example.com/link1" in post_utterance.mentioned_urls


@pytest.mark.asyncio
async def test_extract_utterances_media_empty_when_no_html(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """When html is empty string, all utterance media lists stay empty."""
    post_text = "The post body content here."
    fresh = _scrape(markdown=f"# Post\n\n{post_text}", html="")
    client = _FakeFirecrawlClient(result=fresh)
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.ARTICLE,
            utterances=[Utterance(utterance_id=None, kind="post", text=post_text)],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    post_utterance = payload.utterances[0]
    assert post_utterance.mentioned_images == []
    assert post_utterance.mentioned_urls == []
    assert post_utterance.mentioned_videos == []


# ---------------------------------------------------------------------------
# Phase B (TASK-1474.23.03.03) — classifier wiring at agent.run + Firecrawl
# scrape, plus the `vibecheck.extract_utterances` Logfire span. The span body
# is exercised via a recording stub patched onto `extractor.logfire.span`,
# since logfire isn't configured in the test process.
# ---------------------------------------------------------------------------


def _stub_agent_raising(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    """Replace `build_agent` with a fake whose `run` raises `exc`."""

    class _RaisingAgent:
        model = type("_Model", (), {"model_name": "gemini-fake-from-agent"})()

        def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
            if func is None:

                def _wrap(f: Any) -> Any:
                    return f

                return _wrap
            return func

        async def run(self, *_args: Any, **_kwargs: Any) -> Any:
            raise exc

    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None, name=None, tier="fast": (
            _RaisingAgent()
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 503, 504])
async def test_extract_utterances_classifies_vertex_retriable_as_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, status_code: int
) -> None:
    """`agent.run` raising `ModelHTTPError(429|503|504)` must surface as a
    `TransientExtractionError(provider="vertex")` so the orchestrator can
    redeliver. Non-transient surfaces would have been wrapped as a terminal
    `UtteranceExtractionError`.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent_raising(
        monkeypatch,
        ModelHTTPError(status_code=status_code, model_name="gemini-2.5-pro", body=None),
    )

    with pytest.raises(TransientExtractionError) as exc_info:
        await _call(TARGET_URL, client, cache, settings)

    assert exc_info.value.provider == "vertex"
    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_extract_utterances_classifies_unexpected_model_behavior_with_inner_504(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """`UnexpectedModelBehavior` wrapping a 504 must unwrap to transient.

    pydantic-ai surfaces tool-loop or schema-mismatch retries as
    `UnexpectedModelBehavior(__cause__=ModelHTTPError)`; the classifier walks
    the cause chain and the wire-up must respect that.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    inner = ModelHTTPError(status_code=504, model_name="gemini-2.5-pro", body=None)
    outer = UnexpectedModelBehavior("tool retry exhausted")
    outer.__cause__ = inner
    _stub_agent_raising(monkeypatch, outer)

    with pytest.raises(TransientExtractionError) as exc_info:
        await _call(TARGET_URL, client, cache, settings)

    assert exc_info.value.provider == "vertex"
    assert exc_info.value.status_code == 504
    assert exc_info.value.status == "DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_extract_utterances_treats_parse_failure_as_terminal(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A non-HTTP, non-network exception (e.g. ValueError) must NOT be
    classified as transient — it surfaces as `UtteranceExtractionError` so
    the orchestrator marks the job EXTRACTION_FAILED without retrying.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent_raising(monkeypatch, ValueError("schema validation failed"))

    with pytest.raises(UtteranceExtractionError):
        await _call(TARGET_URL, client, cache, settings)


# ---------------------------------------------------------------------------
# TASK-1488.06 — ZeroUtterancesError on empty Gemini output
# ---------------------------------------------------------------------------
#
# After Gemini agent runs and returns 0 utterances, `extract_utterances` must
# raise a typed `ZeroUtterancesError` instead of silently succeeding with an
# empty payload. The orchestrator catches this signal to layer a once-only
# Tier 2 escalation. Today's silent-empty path masked the failure mode where
# /scrape returned non-trivial markdown but the agent couldn't parse a single
# utterance — an INTERSTITIAL classification that snuck past the cheap quality
# checks but still left no extractable content.
#
# `UtteranceExtractionError` is unchanged for true scrape/agent failures
# (Firecrawl errors, Gemini agent exceptions, missing markdown).


@pytest.mark.asyncio
async def test_extract_utterances_raises_zero_utterances_error_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """Gemini returning utterances=[] is a typed signal, not a success.

    The orchestrator distinguishes ZeroUtterancesError from
    UtteranceExtractionError so it can escalate to Tier 2 once before
    declaring EXTRACTION_FAILED. Today's silent-empty path was the bug.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.ARTICLE,
            utterances=[],
        ),
    )

    with pytest.raises(ZeroUtterancesError):
        await _call(TARGET_URL, client, cache, settings)


@pytest.mark.asyncio
async def test_zero_utterances_error_is_distinct_from_utterance_extraction_error(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """ZeroUtterancesError must NOT subclass UtteranceExtractionError.

    The orchestrator catches them on different paths — escalating on
    ZeroUtterancesError, terminating on UtteranceExtractionError — so a
    subclass relationship would collapse the two cases together.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.ARTICLE,
            utterances=[],
        ),
    )

    with pytest.raises(ZeroUtterancesError) as exc_info:
        await _call(TARGET_URL, client, cache, settings)

    assert not isinstance(exc_info.value, UtteranceExtractionError)


@pytest.mark.asyncio
async def test_extract_utterances_still_raises_extraction_error_on_agent_exception(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """The existing UtteranceExtractionError path remains intact: a Gemini
    agent exception (network blip, model timeout) is NOT a zero-utterance
    signal — it's a true scrape/agent failure that should not trigger Tier 2
    escalation.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()

    class _ExplodingAgent:
        model = type("_Model", (), {"model_name": "gemini-fake-from-agent"})()

        def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
            if func is None:
                return lambda f: f
            return func

        async def run(self, user_prompt: str, *, deps: Any = None) -> Any:
            raise RuntimeError("upstream Gemini blew up")

    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None, name=None, tier="fast": (
            _ExplodingAgent()
        ),
    )

    with pytest.raises(UtteranceExtractionError):
        await _call(TARGET_URL, client, cache, settings)


@pytest.mark.asyncio
async def test_extract_utterances_classifies_firecrawl_503_as_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """`client.scrape` raising `FirecrawlError(503)` must surface as a
    `TransientExtractionError(provider="firecrawl")` — the upstream scraper
    is allowed to redeliver.
    """
    raising = _FakeFirecrawlClient()

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise FirecrawlError("upstream unavailable", status_code=503)

    raising.scrape = boom  # pyright: ignore[reportAttributeAccessIssue]
    cache = _FakeScrapeCache()
    _stub_agent(monkeypatch, _payload())

    with pytest.raises(TransientExtractionError) as exc_info:
        await _call(TARGET_URL, raising, cache, settings)

    assert exc_info.value.provider == "firecrawl"
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_extract_utterances_classifies_firecrawl_404_as_terminal(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A non-retriable FirecrawlError (404) must surface as the terminal
    `UtteranceExtractionError`, not transient.
    """
    raising = _FakeFirecrawlClient()

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise FirecrawlError("page not found", status_code=404)

    raising.scrape = boom  # pyright: ignore[reportAttributeAccessIssue]
    cache = _FakeScrapeCache()
    _stub_agent(monkeypatch, _payload())

    with pytest.raises(UtteranceExtractionError):
        await _call(TARGET_URL, raising, cache, settings)


@pytest.mark.asyncio
async def test_extract_utterances_wraps_body_in_logfire_span(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """The whole `extract_utterances` body must run inside a single
    `vibecheck.extract_utterances` span carrying the `url` attribute. We
    patch `logfire.span` at the extractor module to a recording stub so we
    can assert the span name + initial attrs without depending on Logfire
    being configured in tests.
    """
    from src.utterances import extractor as extractor_mod

    recorded: list[dict[str, Any]] = []

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            recorded[-1].setdefault("set_attrs", {})[key] = value

    def _fake_span(name: str, **attrs: Any) -> _RecordingSpan:
        recorded.append({"name": name, "attrs": dict(attrs), "set_attrs": {}})
        return _RecordingSpan()

    monkeypatch.setattr(extractor_mod.logfire, "span", _fake_span)

    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(monkeypatch, _payload())

    await _call(TARGET_URL, client, cache, settings)

    extractor_span = next(
        span for span in recorded if span["name"] == "vibecheck.extract_utterances"
    )
    assert extractor_span["attrs"].get("url") == TARGET_URL


@pytest.mark.asyncio
async def test_extract_utterances_sets_upstream_attrs_on_vertex_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """When the agent run raises a retriable Vertex error, the span gains
    both the neutral `upstream_*` attrs AND the legacy `vertex_*` attrs for
    backward-compat with saved Logfire searches.
    """
    from src.utterances import extractor as extractor_mod

    set_attrs: dict[str, Any] = {}

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            set_attrs[key] = value

    def _fake_span(_name: str, **_attrs: Any) -> _RecordingSpan:
        return _RecordingSpan()

    monkeypatch.setattr(extractor_mod.logfire, "span", _fake_span)

    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent_raising(
        monkeypatch,
        ModelHTTPError(status_code=503, model_name="gemini-2.5-pro", body=None),
    )

    with pytest.raises(TransientExtractionError):
        await _call(TARGET_URL, client, cache, settings)

    assert set_attrs.get("upstream_provider") == "vertex"
    assert set_attrs.get("upstream_status_code") == 503
    assert set_attrs.get("upstream_status") == "UNAVAILABLE"
    assert set_attrs.get("model_name") == google_vertex_model_name(
        settings.VERTEXAI_FAST_MODEL,
        setting_name="VERTEXAI_FAST_MODEL",
    )
    # Vertex-arm legacy compat — saved Logfire searches keyed on these.
    assert set_attrs.get("vertex_status_code") == 503
    assert set_attrs.get("vertex_status") == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_extract_utterances_sets_upstream_attrs_on_firecrawl_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A transient Firecrawl error must set `upstream_provider="firecrawl"`
    on the span — and must NOT leak the Vertex-arm legacy `vertex_*` attrs
    onto a non-Vertex provider.
    """
    from src.utterances import extractor as extractor_mod

    set_attrs: dict[str, Any] = {}

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            set_attrs[key] = value

    def _fake_span(_name: str, **_attrs: Any) -> _RecordingSpan:
        return _RecordingSpan()

    monkeypatch.setattr(extractor_mod.logfire, "span", _fake_span)

    raising = _FakeFirecrawlClient()

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise FirecrawlError("upstream unavailable", status_code=503)

    raising.scrape = boom  # pyright: ignore[reportAttributeAccessIssue]
    cache = _FakeScrapeCache()
    _stub_agent(monkeypatch, _payload())

    with pytest.raises(TransientExtractionError):
        await _call(TARGET_URL, raising, cache, settings)

    assert set_attrs.get("upstream_provider") == "firecrawl"
    assert set_attrs.get("upstream_status_code") == 503
    # Vertex-only legacy attrs must not be set on non-Vertex transient.
    assert "vertex_status_code" not in set_attrs
    assert "vertex_status" not in set_attrs


@pytest.mark.asyncio
async def test_extract_utterances_succeeds_when_payload_has_one_or_more_utterances(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """Sanity guard: the new ZeroUtterancesError check must not mis-fire on
    a non-empty payload. A single utterance is enough to take the success
    path.
    """
    client = _FakeFirecrawlClient(result=_scrape())
    cache = _FakeScrapeCache()
    _stub_agent(
        monkeypatch,
        _payload(
            page_kind=PageKind.ARTICLE,
            utterances=[Utterance(utterance_id=None, kind="post", text="present")],
        ),
    )

    payload = await _call(TARGET_URL, client, cache, settings)

    assert len(payload.utterances) == 1
    assert payload.utterances[0].text == "present"
