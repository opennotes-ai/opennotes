"""Scrape-cache rescue integration test (TASK-1473.22 AC#2).

Flow:

  1. First job — scrape succeeds, the orchestrator caches the bundle in
     `vibecheck_scrapes`. Then the (stubbed) extractor raises so the job
     terminates as failed/extraction_failed.
  2. Re-submit the same URL within the 72h TTL — the orchestrator's
     `_scrape_step` hits the cache and DOES NOT call Firecrawl. The
     stubbed extractor succeeds this time so the second job finalizes.

The contract under test is the spec's "Re-submit within 72h skips
Firecrawl" property: cached scrape rescues the second attempt without
paying the Firecrawl cost. Firecrawl call count is the load-bearing
assertion.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from src.analyses.schemas import PageKind, SectionSlug
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.utterances.schema import UtterancesPayload

from .conftest import (
    AsyncpgScrapeCache,
    RecordingFirecrawlClient,
    insert_pending_job,
    read_job,
)


@pytest.fixture
def fake_firecrawl() -> RecordingFirecrawlClient:
    return RecordingFirecrawlClient()


def _payload(url: str) -> UtterancesPayload:
    return UtterancesPayload.model_validate(
        {
            "source_url": url,
            "scraped_at": datetime.now(UTC).isoformat(),
            "page_title": "Cache Rescue Page",
            "page_kind": PageKind.ARTICLE.value,
            "utterances": [
                {
                    "utterance_id": "u-0",
                    "kind": "post",
                    "text": "Sole utterance for cache-rescue scenario.",
                    "author": "alice",
                }
            ],
        }
    )


async def test_cache_get_uses_final_url_from_row(
    db_pool: Any,
    scrape_cache: Any,
) -> None:
    target_url = "https://example.com/final-url-cache"
    await scrape_cache.put(
        target_url,
        ScrapeResult(
            markdown="cache body",
            metadata=ScrapeMetadata(
                title="Resolved cache source",
                source_url="https://final.example/cached",
            ),
        ),
        tier="scrape",
    )
    cached = await scrape_cache.get(target_url, tier="scrape")
    assert cached is not None
    assert cached.metadata is not None
    assert cached.metadata.source_url == "https://final.example/cached"


async def test_evict_with_tier_none_tombstones_all_tiers(
    db_pool: Any,
    scrape_cache: Any,
) -> None:
    target_url = "https://example.com/tier-none-evict"
    await scrape_cache.put(
        target_url,
        ScrapeResult(
            markdown="scrape tier body",
            metadata=ScrapeMetadata(title="Scrape Tier"),
        ),
        tier="scrape",
    )
    await scrape_cache.put(
        target_url,
        ScrapeResult(
            markdown="interact tier body",
            metadata=ScrapeMetadata(title="Interact Tier"),
        ),
        tier="interact",
    )
    await scrape_cache.evict(target_url, tier=None)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tier, markdown, evicted_at
            FROM vibecheck_scrapes
            WHERE normalized_url = $1
            """,
            target_url,
        )
    assert len(rows) == 2
    assert {row["tier"] for row in rows} == {"scrape", "interact"}
    assert all(row["evicted_at"] is not None for row in rows)
    assert all(row["markdown"] is None for row in rows)


async def test_asyncpg_cache_fence_prevents_post_read_evict_resurrection(
    db_pool: Any,
) -> None:
    cache_put_url = "https://example.com/cache-parity/?utm_source=x"
    cache_get_url = "https://example.com/cache-parity"
    after_fence_read = asyncio.Event()
    release_write = asyncio.Event()
    timeout = 5.0

    async def before_atomic_write() -> None:
        after_fence_read.set()
        await release_write.wait()

    cache = AsyncpgScrapeCache(
        db_pool, after_fence_read=before_atomic_write
    )

    put_task = asyncio.create_task(
        cache.put(
            cache_put_url,
            ScrapeResult(
                markdown="resurrect-me",
                metadata=ScrapeMetadata(
                    title="Resurrect", source_url=cache_put_url
                ),
            ),
        )
    )
    await asyncio.wait_for(after_fence_read.wait(), timeout=timeout)
    await cache.evict(cache_get_url, tier="scrape")
    release_write.set()
    result = await asyncio.wait_for(put_task, timeout=timeout)

    assert result.storage_key is None

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT markdown, evicted_at
            FROM vibecheck_scrapes
            WHERE normalized_url = $1 AND tier = $2
            """,
            cache_get_url,
            "scrape",
        )
        rescue_row = await conn.fetchrow(
            "SELECT markdown FROM vibecheck_scrapes WHERE normalized_url = $1",
            cache_get_url,
        )
    assert row is not None
    assert row["markdown"] is None
    assert row["evicted_at"] is not None
    assert rescue_row is not None
    assert await cache.get(cache_get_url, tier="scrape") is None
    assert await cache.get(cache_put_url, tier="scrape") is None


async def test_second_submit_within_ttl_reuses_scrape_cache(
    http_client: httpx.AsyncClient,
    db_pool: Any,
    install_oidc_mock: Any,
    oidc_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    fake_firecrawl: RecordingFirecrawlClient,
    scrape_cache: Any,
) -> None:
    from src.jobs import orchestrator

    monkeypatch.setattr(
        orchestrator, "_build_scrape_cache", lambda _settings: scrape_cache
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda _settings: fake_firecrawl
    )
    # TASK-1488.05: Tier 1 fail-fast client is a separate factory seam.
    # Both tiers share the same fake so call counts stay deterministic.
    monkeypatch.setattr(
        orchestrator,
        "_build_firecrawl_tier1_client",
        lambda _settings: fake_firecrawl,
    )
    for slug in SectionSlug:
        async def _empty_handler(
            pool: Any,
            job_id: Any,
            task_attempt: Any,
            payload: Any,
            settings: Any,
            *,
            _slug: SectionSlug = slug,
        ) -> dict[str, Any]:
            return orchestrator._empty_section_data(_slug)

        monkeypatch.setitem(orchestrator._SECTION_HANDLERS, slug, _empty_handler)

    target_url = "https://example.com/cache-rescue"

    # ----- Job 1: scrape succeeds, extraction fails -----------------------

    async def _failing_extract(
        url: str,
        client: Any,
        cache: Any,
        *,
        settings: Any = None,
        scrape: Any = None,
    ) -> UtterancesPayload:
        raise RuntimeError("Gemini connection lost")

    monkeypatch.setattr(orchestrator, "extract_utterances", _failing_extract)

    job_one_id, job_one_attempt = await insert_pending_job(
        db_pool, url=target_url
    )
    resp = await http_client.post(
        f"/_internal/jobs/{job_one_id}/run",
        json={
            "job_id": str(job_one_id),
            "expected_attempt_id": str(job_one_attempt),
        },
        headers=oidc_headers,
    )
    # extraction_failed is a TerminalError — orchestrator returns 200, no retry.
    assert resp.status_code == 200, resp.text
    job_one = await read_job(db_pool, job_one_id)
    assert job_one["status"] == "failed"
    assert job_one["error_code"] == "extraction_failed"

    # Firecrawl was hit exactly once during job 1 — the scrape was cached.
    assert fake_firecrawl.calls == [target_url]

    # The cache row exists for the URL.
    async with db_pool.acquire() as conn:
        cached_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_scrapes WHERE normalized_url = $1",
            target_url,
        )
    assert cached_count == 1

    # ----- Job 2: extraction now succeeds; Firecrawl must NOT be called --

    async def _ok_extract(
        url: str,
        client: Any,
        cache: Any,
        *,
        settings: Any = None,
        scrape: Any = None,
    ) -> UtterancesPayload:
        return _payload(url)

    monkeypatch.setattr(orchestrator, "extract_utterances", _ok_extract)

    job_two_id, job_two_attempt = await insert_pending_job(
        db_pool, url=target_url
    )
    resp_two = await http_client.post(
        f"/_internal/jobs/{job_two_id}/run",
        json={
            "job_id": str(job_two_id),
            "expected_attempt_id": str(job_two_attempt),
        },
        headers=oidc_headers,
    )
    assert resp_two.status_code == 200, resp_two.text

    # Second job should have populated `vibecheck_analyses`. The job row
    # itself stays in `analyzing` because `maybe_finalize_job` does not
    # currently flip status to `done` (see TASK-1473 follow-up); the cache
    # row is the load-bearing post-condition.
    async with db_pool.acquire() as conn:
        analyses_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1",
            target_url,
        )
    assert analyses_count == 1, (
        f"second job did not finalize: vibecheck_analyses rows={analyses_count}"
    )
    job_two = await read_job(db_pool, job_two_id)
    assert job_two["status"] in ("analyzing", "done")
    assert job_two["error_code"] is None

    # Critical assertion: Firecrawl call count did NOT increase — the
    # second job hit the scrape cache and skipped the upstream call.
    assert fake_firecrawl.calls == [target_url], (
        f"second submit re-called Firecrawl: calls={fake_firecrawl.calls!r}"
    )
