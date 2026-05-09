"""Viafoura ladder integration coverage."""

from __future__ import annotations

from typing import Any

import pytest

from src.cache.scrape_cache import CachedScrape, ScrapeTier
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.jobs.orchestrator import _scrape_step
from src.utterances.extractor import (
    COMMENTS_PROMPT_ADDENDUM,
    _agent_user_prompt,
)
from src.viafoura import ViafouraUnsupportedError

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
