"""Harness coverage for `RecordingFirecrawlClient.interact()` (TASK-1488.15).

Scope: harness-only assertions. Scenario tests that exercise the full
Tier 1 → Tier 2 ladder through the orchestrator pipeline land in
TASK-1488.11 (thread scrape result through extract) and TASK-1488.12
(SSRF eviction across both tiers).

Without these harness checks, a future regression where Tier 1 falls to
Tier 2 inside an integration test would crash with `AttributeError`
("RecordingFirecrawlClient has no attribute 'interact'") instead of
producing a clean `ScrapeResult` — the confusing failure mode the
TASK-1488.15 description called out.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.cache.scrape_cache import CachedScrape, ScrapeTier
from src.firecrawl_client import FirecrawlBlocked, ScrapeMetadata, ScrapeResult
from src.jobs.orchestrator import TerminalError, _revalidate_final_url

from .conftest import RecordingFirecrawlClient


@pytest.mark.asyncio
async def test_interact_returns_default_scrape_result_for_unknown_url() -> None:
    client = RecordingFirecrawlClient()

    result = await client.interact("https://example.com/post/1", actions=[])

    assert isinstance(result, ScrapeResult)
    assert result.metadata is not None
    assert result.metadata.source_url == "https://example.com/post/1"


@pytest.mark.asyncio
async def test_interact_records_url_and_kwargs() -> None:
    client = RecordingFirecrawlClient()

    actions = [{"type": "wait", "milliseconds": 250}]
    await client.interact(
        "https://example.com/x",
        actions,
        formats=["markdown"],
        only_main_content=True,
    )

    assert client.calls == ["https://example.com/x"]
    assert client.interact_calls == [
        (
            "https://example.com/x",
            {
                "actions": actions,
                "formats": ["markdown"],
                "only_main_content": True,
            },
        )
    ]
    assert client.scrape_calls == []


@pytest.mark.asyncio
async def test_scrape_records_url_and_kwargs_separately_from_interact() -> None:
    client = RecordingFirecrawlClient()

    await client.scrape(
        "https://example.com/x",
        ["markdown", "html"],
        only_main_content=True,
    )

    assert client.scrape_calls == [
        (
            "https://example.com/x",
            {
                "formats": ["markdown", "html"],
                "only_main_content": True,
            },
        )
    ]
    assert client.interact_calls == []


@pytest.mark.asyncio
async def test_interact_raises_configured_exception() -> None:
    client = RecordingFirecrawlClient(
        interact_results_by_url={
            "https://blocked.example.com": FirecrawlBlocked(
                "we don't support this site"
            ),
        }
    )

    with pytest.raises(FirecrawlBlocked):
        await client.interact("https://blocked.example.com", actions=[])

    # Even on raise, the call is still recorded.
    assert client.calls == ["https://blocked.example.com"]
    assert client.interact_calls[0][0] == "https://blocked.example.com"


@pytest.mark.asyncio
async def test_interact_invokes_callable_factory_per_call() -> None:
    counter = {"n": 0}

    def factory() -> ScrapeResult:
        counter["n"] += 1
        return ScrapeResult(
            markdown=f"call {counter['n']}",
            metadata=ScrapeMetadata(
                title="Factory", source_url="https://example.com/f"
            ),
        )

    client = RecordingFirecrawlClient(
        interact_results_by_url={"https://example.com/f": factory}
    )

    first = await client.interact("https://example.com/f", actions=[])
    second = await client.interact("https://example.com/f", actions=[])

    assert first.markdown == "call 1"
    assert second.markdown == "call 2"


@pytest.mark.asyncio
async def test_scrape_outcome_can_also_be_exception_or_factory() -> None:
    """Symmetry: scrape() honors the same ScrapeOutcome union as interact()."""
    client = RecordingFirecrawlClient(
        results_by_url={
            "https://blocked.example.com": FirecrawlBlocked("refused"),
        }
    )

    with pytest.raises(FirecrawlBlocked):
        await client.scrape("https://blocked.example.com", ["markdown"])


# ---------------------------------------------------------------------------
# TASK-1488.12 — `_revalidate_final_url` must flush BOTH tiers on poisoned
# redirect. Without `tier=None`, a Tier 2 row carrying the SSRF-poisoned
# bundle survives and replays on retry.
# ---------------------------------------------------------------------------


class _RecordingScrapeCache:
    """Minimal cache fake that records evict (url, tier) tuples.

    We only need `evict()` for this test — `_revalidate_final_url` doesn't
    consult `get`/`put` on its own.
    """

    def __init__(self) -> None:
        self.evict_calls: list[tuple[str, ScrapeTier | None]] = []

    async def evict(
        self, url: str, *, tier: ScrapeTier | None = None
    ) -> None:
        self.evict_calls.append((url, tier))


@pytest.mark.asyncio
async def test_revalidate_final_url_evicts_all_tiers_on_poisoned_redirect() -> None:
    """The redirect-block path must call `evict(tier=None)` so both Tier 1
    and Tier 2 rows are flushed. Calling `evict(tier="scrape")` would leave
    a Tier 2 row alive in the cache — replaying the SSRF input on retry.
    """
    poisoned = CachedScrape(
        markdown="x" * 200,
        html="<html>x</html>",
        raw_html=None,
        screenshot=None,
        links=None,
        metadata=ScrapeMetadata(
            title="poisoned", source_url="http://169.254.169.254/"
        ),
        warning=None,
        storage_key=None,
    )
    cache = _RecordingScrapeCache()

    with pytest.raises(TerminalError):
        await _revalidate_final_url(
            poisoned,
            url="https://example.com/legit",
            scrape_cache=cast_cache(cache),
        )

    assert cache.evict_calls == [("https://example.com/legit", None)]


def cast_cache(cache: Any) -> Any:
    """Type-only cast for the recording fake — `_revalidate_final_url`
    annotates `scrape_cache: SupabaseScrapeCache` but only touches `evict`.
    """
    return cache
