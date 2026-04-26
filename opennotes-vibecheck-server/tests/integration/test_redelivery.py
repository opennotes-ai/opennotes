"""Cloud Tasks redelivery idempotency integration test (TASK-1473.22 AC#4).

Calls the internal worker endpoint twice with the same `expected_attempt_id`
and asserts the second call is a 200 no-op. The first call drives the
orchestrator; the second hits the stale-claim path (`_claim_job` returns
None because the row's attempt_id has rotated) and short-circuits.

What we prove end-to-end:
  * Cloud Tasks at-least-once redeliveries do NOT double-process a job.
  * Both responses are HTTP 200 (Cloud Tasks does not retry on 200).
  * The DB ends up in the same state the first run produced — no torn
    sections, no double UPSERT into `vibecheck_analyses`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from src.analyses.schemas import PageKind, SectionSlug
from src.utterances.schema import UtterancesPayload

from .conftest import (
    RecordingFirecrawlClient,
    insert_pending_job,
    read_job,
    read_sections,
)


@pytest.fixture
def fake_firecrawl() -> RecordingFirecrawlClient:
    return RecordingFirecrawlClient()


def _payload(url: str) -> UtterancesPayload:
    return UtterancesPayload.model_validate(
        {
            "source_url": url,
            "scraped_at": datetime.now(UTC).isoformat(),
            "page_title": "Redelivery Page",
            "page_kind": PageKind.ARTICLE.value,
            "utterances": [
                {
                    "utterance_id": "u-0",
                    "kind": "post",
                    "text": "Single utterance for redelivery test.",
                    "author": "alice",
                }
            ],
        }
    )


async def test_two_deliveries_with_same_expected_attempt_id_are_idempotent(
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
    monkeypatch.setattr(
        orchestrator,
        "_build_firecrawl_tier1_client",
        lambda _settings: fake_firecrawl,
    )

    target_url = "https://example.com/redelivery"
    extract_calls = 0

    async def _stub_extract(
        url: str, client: Any, cache: Any, *, settings: Any = None
    ) -> UtterancesPayload:
        nonlocal extract_calls
        extract_calls += 1
        return _payload(url)

    monkeypatch.setattr(orchestrator, "extract_utterances", _stub_extract)

    job_id, expected_attempt = await insert_pending_job(
        db_pool, url=target_url
    )

    body = {
        "job_id": str(job_id),
        "expected_attempt_id": str(expected_attempt),
    }

    # First delivery — drives the full pipeline.
    first = await http_client.post(
        f"/_internal/jobs/{job_id}/run", json=body, headers=oidc_headers
    )
    assert first.status_code == 200, first.text

    # The first run should have populated `vibecheck_analyses` and brought
    # every slot to `done`. (Note: maybe_finalize_job does not currently
    # flip `vibecheck_jobs.status` to `done` — see TASK-1473 follow-up.)
    after_first = await read_job(db_pool, job_id)
    sections_after_first = await read_sections(db_pool, job_id)
    assert all(
        sections_after_first[slug.value]["state"] == "done"
        for slug in SectionSlug
    )
    assert fake_firecrawl.calls == [target_url]
    assert extract_calls == 1

    # Second delivery — same envelope. The orchestrator's CAS rejects it
    # because the row's attempt_id rotated when the first delivery claimed.
    second = await http_client.post(
        f"/_internal/jobs/{job_id}/run", json=body, headers=oidc_headers
    )
    assert second.status_code == 200, second.text

    # State unchanged: no extra Firecrawl calls, no extra extraction,
    # sections JSONB identical to post-first-run.
    assert fake_firecrawl.calls == [target_url]
    assert extract_calls == 1
    after_second = await read_job(db_pool, job_id)
    assert after_second["status"] == after_first["status"]
    assert after_second["attempt_id"] == after_first["attempt_id"]

    sections_after_second = await read_sections(db_pool, job_id)
    assert sections_after_second == sections_after_first

    # Single cache row in vibecheck_analyses — no double UPSERT.
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1",
            target_url,
        )
    assert rowcount == 1
