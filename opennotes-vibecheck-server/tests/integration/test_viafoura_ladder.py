"""Viafoura ladder integration coverage."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.cache.scrape_cache import CachedScrape, ScrapeTier
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.jobs.orchestrator import _scrape_step
from src.utterances.extractor import (
    COMMENTS_PROMPT_ADDENDUM,
    _agent_user_prompt,
)
from src.viafoura import (
    ViafouraSignal,
    ViafouraUnsupportedError,
    fetch_viafoura_comments,
    merge_viafoura_into_scrape,
)

AP_URL = "https://apnews.com/article/redistricting-virginia-congress-democrats-republicans-12a31037f3c9a94d3cb9fbcaaf84d94f"
AP_HTML = """
<html>
  <head>
    <script src="https://cdn.viafoura.net/entry/index.js" async></script>
    <meta name="vf:container_id" content="12a31037f3c9a94d3cb9fbcaaf84d94f" />
  </head>
  <body>
    <article><p>Article body with enough real text for the scraper quality gate.</p></article>
    <div id="ap-comments" class="viafoura">
      <vf-conversations id="vf-conv" limit="4"></vf-conversations>
    </div>
  </body>
</html>
"""
TIER2_HTML = """
<html>
  <body>
    <article><p>Article body with enough real text for the scraper quality gate.</p></article>
    <section data-platform-comments data-platform="viafoura" data-platform-status="copied">
      <article class="comment"><header>apreader</header><p>Visible Viafoura comment.</p></article>
    </section>
  </body>
</html>
"""


class _MemoryScrapeCache:
    def __init__(self) -> None:
        self.store: dict[tuple[str, ScrapeTier], CachedScrape] = {}

    async def get(self, url: str, *, tier: ScrapeTier = "scrape") -> CachedScrape | None:
        return self.store.get((url, tier))

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        *,
        tier: ScrapeTier = "scrape",
    ) -> CachedScrape:
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
        self.store[(url, tier)] = cached
        return cached


class _RecordingClient:
    def __init__(
        self,
        *,
        scrape_result: ScrapeResult | None = None,
        interact_result: ScrapeResult | None = None,
    ) -> None:
        self.scrape_result = scrape_result
        self.interact_result = interact_result
        self.scrape_calls: list[tuple[str, dict[str, Any]]] = []
        self.interact_calls: list[tuple[str, dict[str, Any]]] = []

    async def scrape(
        self,
        url: str,
        formats: list[str],
        **kwargs: Any,
    ) -> ScrapeResult:
        self.scrape_calls.append((url, {"formats": formats, **kwargs}))
        assert self.scrape_result is not None
        return self.scrape_result

    async def interact(
        self,
        url: str,
        actions: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ScrapeResult:
        self.interact_calls.append((url, {"actions": actions, **kwargs}))
        assert self.interact_result is not None
        return self.interact_result


@pytest.mark.asyncio
async def test_viafoura_detection_escalates_to_tier2_and_caches_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch_unavailable(*_args: Any, **_kwargs: Any) -> None:
        raise ViafouraUnsupportedError("api unavailable in this fixture")

    from src.jobs import orchestrator

    monkeypatch.setattr(orchestrator, "fetch_viafoura_comments", fetch_unavailable)

    scrape_client = _RecordingClient(
        scrape_result=ScrapeResult(
            markdown="Article body with enough real text for the scraper quality gate.",
            html=AP_HTML,
            raw_html=AP_HTML,
            metadata=ScrapeMetadata(source_url=AP_URL),
        )
    )
    interact_client = _RecordingClient(
        interact_result=ScrapeResult(
            markdown="Article body.\n\n## Comments\n- [c1] author=apreader created_at=2026-05-08T12:00:00+00:00 parent=null\n  Visible Viafoura comment.",
            html=TIER2_HTML,
            metadata=ScrapeMetadata(source_url=AP_URL),
            actions={"javascriptReturns": [{"value": "viafoura_status:copied;comments=1"}]},
        )
    )
    cache = _MemoryScrapeCache()

    result = await _scrape_step(
        AP_URL,
        scrape_client,  # pyright: ignore[reportArgumentType]
        interact_client,  # pyright: ignore[reportArgumentType]
        cache,  # pyright: ignore[reportArgumentType]
    )

    assert result.html is not None
    assert 'data-platform="viafoura"' in result.html
    assert "Visible Viafoura comment." in result.html
    assert (AP_URL, "scrape") in cache.store
    assert (AP_URL, "interact") in cache.store
    actions = interact_client.interact_calls[0][1]["actions"]
    assert "data-platform-comments" in actions[3]["script"]
    assert interact_client.interact_calls[0][1]["only_main_content"] is False


@pytest.mark.asyncio
async def test_ap_news_viafoura_authors_resolve_via_dedup(httpx_mock: HTTPXMock) -> None:
    """End-to-end: AP News-style fixture surfaces all four real usernames, not 'anonymous'."""
    signal = ViafouraSignal(
        container_id="12a31037f3c9a94d3cb9fbcaaf84d94f",
        site_domain=None,
        embed_origin="https://cdn.viafoura.net",
        iframe_src=None,
        has_conversations_component=True,
    )
    bootstrap_url = "https://api.viafoura.co/v2/apnews.com/bootstrap/v2?session=false"
    container_url = (
        "https://livecomments.viafoura.co/v4/livecomments/"
        "00000000-0000-4000-8000-3caf4df03307/contentcontainer/id"
        "?container_id=12a31037f3c9a94d3cb9fbcaaf84d94f"
    )
    comments_url = (
        "https://livecomments.viafoura.co/v4/livecomments/"
        "00000000-0000-4000-8000-3caf4df03307/fe897d9b-8fcf-411a-b9d6-97325116ed98/comments"
        "?limit=50&reply_limit=5&sorted_by=newest"
    )

    httpx_mock.add_response(url=bootstrap_url, method="POST", json={
        "result": {
            "settings": {"site_uuid": "00000000-0000-4000-8000-3caf4df03307"},
            "sectionTree": {"uuid": "00000000-0000-4000-8000-3caf4df03307"},
        }
    })
    httpx_mock.add_response(url=container_url, method="GET", json={
        "container_id": "12a31037f3c9a94d3cb9fbcaaf84d94f",
        "content_container_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
    })
    httpx_mock.add_response(url=comments_url, method="GET", json={
        "more_available": False,
        "contents": [
            {
                "content_uuid": "c1",
                "parent_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
                "content": "<p>So they ignored the voters.</p>",
                "date_created": 1778282641870,
                "state": "visible",
                "actor": None,
                "actor_uuid": "aaaaaaaa-1111-2222-3333-444444444444",
            },
            {
                "content_uuid": "c2",
                "parent_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
                "content": "<p>This is a bad ruling.</p>",
                "date_created": 1778282651870,
                "state": "visible",
                "actor": None,
                "actor_uuid": "bbbbbbbb-1111-2222-3333-444444444444",
            },
            {
                "content_uuid": "c3",
                "parent_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
                "content": "<p>Democracy at work.</p>",
                "date_created": 1778282661870,
                "state": "visible",
                "actor": None,
                "actor_uuid": "cccccccc-1111-2222-3333-444444444444",
            },
            {
                "content_uuid": "c4",
                "parent_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
                "content": "<p>Read the constitution.</p>",
                "date_created": 1778282671870,
                "state": "visible",
                "actor": None,
                "actor_uuid": "dddddddd-1111-2222-3333-444444444444",
            },
        ],
    })

    ap_scrape_html = (
        "<article><p>Article body with enough real text.</p></article>"
        '<article class="vf3-comment" aria-label="Comment by Mikeee.">'
        '<div class="vf3-comment-content">So they ignored the voters.</div></article>'
        '<article class="vf3-comment" aria-label="Comment by Bear0678.">'
        '<div class="vf3-comment-content">This is a bad ruling.</div></article>'
        '<article class="vf3-comment" aria-label="Comment by MargaretO.">'
        '<div class="vf3-comment-content">Democracy at work.</div></article>'
        '<article class="vf3-comment" aria-label="Comment by Lostagain.">'
        '<div class="vf3-comment-content">Read the constitution.</div></article>'
    )
    scrape = ScrapeResult(
        markdown="Article body with enough real text.",
        html=ap_scrape_html,
        metadata=ScrapeMetadata(source_url=AP_URL),
    )

    async with httpx.AsyncClient() as client:
        comments = await fetch_viafoura_comments(signal, AP_URL, client=client)

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "author=Mikeee" in merged.markdown
    assert "author=Bear0678" in merged.markdown
    assert "author=MargaretO" in merged.markdown
    assert "author=Lostagain" in merged.markdown
    assert "anonymous" not in merged.markdown
    assert "user-aaaaaaaa" not in merged.markdown
    assert "user-bbbbbbbb" not in merged.markdown

    assert merged.html is not None
    assert "vf3-comment" not in merged.html
    assert 'data-platform="viafoura"' in merged.html
    for username in ("Mikeee", "Bear0678", "MargaretO", "Lostagain"):
        assert username in merged.html


def test_platform_marker_addendum_recognizes_viafoura_comments() -> None:
    cached = CachedScrape(
        markdown="Article body.\n\nVisible Viafoura comment.",
        html=TIER2_HTML,
        raw_html=None,
        screenshot=None,
        links=None,
        metadata=ScrapeMetadata(source_url=AP_URL),
        warning=None,
        storage_key=None,
    )

    prompt = _agent_user_prompt(cached.markdown or "", cached)

    assert COMMENTS_PROMPT_ADDENDUM.strip() in prompt
