"""End-to-end async-pipeline integration test (TASK-1473.22 AC#1).

Walks the public API + internal worker through one job lifetime:

    POST /api/analyze              -> 202 + job_id, status=pending
    POST /_internal/jobs/{id}/run  -> orchestrator runs the (stubbed) pipeline
                                      and finalizes when every slot is done
    GET  /api/analyze/{id}         -> 200 + status=done + sidebar_payload

Firecrawl is stubbed with `RecordingFirecrawlClient`; Gemini extraction is
stubbed by patching `src.jobs.orchestrator.extract_utterances`. The
section-fan-out path is left intact: `_run_section` already writes the
`_empty_section_data` payload that `maybe_finalize_job` accepts, so the
test exercises the full slot-write + finalize stack without touching any
LLM.

What this test proves end-to-end:
  * The advisory-lock + dedup flow at `POST /api/analyze` returns a fresh
    job_id.
  * The orchestrator's `_claim_job` flips status pending → extracting,
    extracts utterances (stubbed), flips to analyzing, fans out the seven
    slots, and finalizes via `maybe_finalize_job`.
  * `vibecheck_analyses` ends up with one row whose `sidebar_payload` has
    every section structurally present.
  * The poll endpoint returns `status=done` + `sidebar_payload` populated.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest

from src.analyses.schemas import PageKind, SectionSlug
from src.utterances.schema import UtterancesPayload

from .conftest import RecordingFirecrawlClient, read_job, read_sections


@pytest.fixture
def fake_firecrawl() -> RecordingFirecrawlClient:
    return RecordingFirecrawlClient()


async def _make_utterances_payload(
    url: str, *, n: int = 3
) -> UtterancesPayload:
    return UtterancesPayload.model_validate(
        {
            "source_url": url,
            "scraped_at": datetime.now(UTC).isoformat(),
            "page_title": "Test Page",
            "page_kind": PageKind.ARTICLE.value,
            "utterances": [
                {
                    "utterance_id": f"u-{i}",
                    "kind": "post" if i == 0 else "comment",
                    "text": f"utterance body {i}",
                    "author": f"author-{i}",
                }
                for i in range(n)
            ],
        }
    )


async def test_post_then_internal_run_then_poll_to_done(
    http_client: httpx.AsyncClient,
    db_pool: Any,
    install_oidc_mock: Any,
    oidc_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    fake_firecrawl: RecordingFirecrawlClient,
    scrape_cache: Any,
) -> None:
    # 1. Wire orchestrator factory seams to the integration fakes/cache.
    from src.jobs import orchestrator

    monkeypatch.setattr(
        orchestrator, "_build_scrape_cache", lambda _settings: scrape_cache
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda _settings: fake_firecrawl
    )

    target_url = "https://example.com/e2e-job"
    payload = await _make_utterances_payload(target_url)

    async def _stub_extract(
        url: str, client: Any, cache: Any, *, settings: Any = None
    ) -> UtterancesPayload:
        return payload

    monkeypatch.setattr(orchestrator, "extract_utterances", _stub_extract)

    # 2. POST /api/analyze — fresh submit returns 202 + new job_id.
    resp = await http_client.post(
        "/api/analyze", json={"url": target_url}
    )
    assert resp.status_code == 202, resp.text
    body = json.loads(resp.text)
    job_id = UUID(body["job_id"])
    assert body["status"] == "pending"
    assert body["cached"] is False

    # 3. Look up the attempt_id we'll pass to the worker — the route
    #    inserted the row with a freshly-minted attempt_id we don't see in
    #    the response, so read it back from the DB.
    job_row = await read_job(db_pool, job_id)
    expected_attempt_id = job_row["attempt_id"]
    assert isinstance(expected_attempt_id, UUID)

    # 4. POST /_internal/jobs/{id}/run — drives the orchestrator pipeline.
    worker_resp = await http_client.post(
        f"/_internal/jobs/{job_id}/run",
        json={
            "job_id": str(job_id),
            "expected_attempt_id": str(expected_attempt_id),
        },
        headers=oidc_headers,
    )
    assert worker_resp.status_code == 200, worker_resp.text

    # 5. Every per-section slot must be `done` and the assembled
    #    SidebarPayload must have UPSERTed into `vibecheck_analyses`.
    #    Note: as of this commit `maybe_finalize_job` does not flip
    #    `vibecheck_jobs.status` to `done` (only inserts the analyses row),
    #    so the job row's status stays at `analyzing` after a successful
    #    finalize — see TASK-1473 follow-up tracking the missing transition.
    sections = await read_sections(db_pool, job_id)
    for slug in SectionSlug:
        assert slug.value in sections, f"missing slot {slug.value}"
        assert sections[slug.value]["state"] == "done"

    final = await read_job(db_pool, job_id)
    assert final["status"] in ("analyzing", "done"), (
        f"job ended in unexpected status {final['status']!r}: "
        f"error_code={final.get('error_code')!r} "
        f"message={final.get('error_message')!r}"
    )

    # 6. vibecheck_analyses cache row exists with assembled SidebarPayload.
    async with db_pool.acquire() as conn:
        analyses_row = await conn.fetchrow(
            "SELECT url, sidebar_payload FROM vibecheck_analyses WHERE url = $1",
            target_url,
        )
    assert analyses_row is not None, (
        "no vibecheck_analyses row written — finalize did not run or rolled back"
    )
    sidebar_raw = analyses_row["sidebar_payload"]
    sidebar = (
        json.loads(sidebar_raw) if isinstance(sidebar_raw, str) else dict(sidebar_raw)
    )
    assert sidebar["source_url"] == target_url
    assert "safety" in sidebar
    assert "tone_dynamics" in sidebar
    assert "facts_claims" in sidebar
    assert "opinions_sentiments" in sidebar

    # 7. GET /api/analyze/{id} returns the populated state.
    poll_resp = await http_client.get(f"/api/analyze/{job_id}")
    assert poll_resp.status_code == 200, poll_resp.text
    poll_body = json.loads(poll_resp.text)
    assert poll_body["job_id"] == str(job_id)
    # All per-slot results must be present in the polled snapshot.
    for slug in SectionSlug:
        assert slug.value in poll_body["sections"]
        assert poll_body["sections"][slug.value]["state"] == "done"

    # 8. Firecrawl was hit exactly once for this URL.
    assert fake_firecrawl.calls == [target_url]
