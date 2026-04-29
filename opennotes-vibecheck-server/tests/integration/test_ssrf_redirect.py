"""SSRF redirect-target rejection integration test (TASK-1473.22 AC#5).

The orchestrator's post-scrape revalidator must reject a Firecrawl response
whose `metadata.source_url` ends up at a private/loopback host (the most
common shape: a 302 to the GCE metadata IP `169.254.169.254`). The
contract:

  1. The job flips to `failed` with `error_code='invalid_url'`.
  2. The cached scrape is evicted so a future submit can't replay the
     poisoned entry.
  3. The HTTP response is 200 (terminal — Cloud Tasks does not retry).
  4. The section fan-out NEVER runs.

This integration test wires the real orchestrator + real DB; only the
upstream Firecrawl HTTP call is faked (returning a malicious metadata.
source_url).
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.firecrawl_client import ScrapeMetadata, ScrapeResult

from .conftest import (
    RecordingFirecrawlClient,
    insert_pending_job,
    read_job,
)


async def test_post_scrape_redirect_to_private_ip_marks_invalid_url(
    http_client: httpx.AsyncClient,
    db_pool: Any,
    install_oidc_mock: Any,
    oidc_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    scrape_cache: Any,
) -> None:
    from src.jobs import orchestrator

    target_url = "https://example.com/ssrf-redirect"
    poisoned_metadata = ScrapeMetadata(
        title="poisoned",
        # Firecrawl reports the final URL after following 302 redirects;
        # this is the post-scrape SSRF revalidator's load-bearing input.
        source_url="http://169.254.169.254/computeMetadata/v1/",
    )
    poisoned_result = ScrapeResult(
        markdown="redirected content",
        html="<p>redirected content</p>",
        metadata=poisoned_metadata,
    )
    fake_firecrawl = RecordingFirecrawlClient(
        results_by_url={target_url: poisoned_result}
    )

    monkeypatch.setattr(
        orchestrator, "_build_scrape_cache", lambda _settings: scrape_cache
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda _settings: fake_firecrawl
    )
    # TASK-1488.05: Tier 1 fail-fast client is a separate factory seam.
    monkeypatch.setattr(
        orchestrator,
        "_build_firecrawl_tier1_client",
        lambda _settings: fake_firecrawl,
    )

    # Stub the extractor so a hypothetical fall-through past revalidate
    # doesn't reach Vertex AI. The contract under test requires revalidate
    # to raise TerminalError BEFORE extract_utterances is awaited; this
    # stub belt-and-braces against a regression that flips the order.
    extract_called = False

    async def _spy_extract(
        url: str, client: Any, cache: Any, *, settings: Any = None
    ) -> Any:
        nonlocal extract_called
        extract_called = True
        raise AssertionError("extract_utterances must not run after SSRF reject")

    monkeypatch.setattr(orchestrator, "extract_utterances", _spy_extract)

    # If the section fan-out runs we have a bug — assert by raising.
    async def _fail_fanout(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "section fan-out must not run when post-scrape SSRF rejects"
        )

    monkeypatch.setattr(orchestrator, "_run_all_sections", _fail_fanout)

    job_id, expected_attempt = await insert_pending_job(
        db_pool, url=target_url
    )

    resp = await http_client.post(
        f"/_internal/jobs/{job_id}/run",
        json={
            "job_id": str(job_id),
            "expected_attempt_id": str(expected_attempt),
        },
        headers=oidc_headers,
    )
    # TerminalError → 200 (Cloud Tasks must not retry).
    assert resp.status_code == 200, resp.text

    final = await read_job(db_pool, job_id)
    assert final["status"] == "failed"
    assert final["error_code"] == "invalid_url"
    assert "private" in (final["error_message"] or "").lower()

    # Extraction must not have been reached — revalidate is upstream of it.
    assert not extract_called, (
        "extract_utterances ran even though SSRF revalidate should reject first"
    )

    # Cache eviction: the poisoned scrape row must be gone after revalidate.
    # `_scrape_step` put() the fresh scrape into the cache; revalidate
    # caught the private redirect and called `cache.evict(tier=None)` to
    # discard both scrape/interact tiers as tombstones (TASK-1488.18).
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tier
            FROM vibecheck_scrapes
            WHERE normalized_url = $1
              AND evicted_at IS NOT NULL
              AND markdown IS NULL
              AND html IS NULL
              AND screenshot_storage_key IS NULL
              AND expires_at < now()
            """,
            target_url,
        )
    tiers = {row["tier"] for row in rows}
    assert tiers == {"scrape", "interact"}, (
        "evict(tier=None) must write tombstones for both scrape and interact tiers"
    )

    assert await scrape_cache.get(
        target_url, tier="scrape"
    ) is None, "poisoned scrape must not be replayable after evict"
    assert await scrape_cache.get(
        target_url, tier="interact"
    ) is None, "interact tier must also not be replayable after evict"
