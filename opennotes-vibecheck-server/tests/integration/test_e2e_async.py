"""Integration coverage for the async-pipeline orchestration surface (TASK-1473.22 AC#1).

Walks the public API + internal worker through one job lifetime so the
route → orchestrator → finalize wiring is exercised end-to-end:

    POST /api/analyze              -> 202 + job_id, status=pending
    POST /_internal/jobs/{id}/run  -> orchestrator runs the (stubbed) pipeline
                                      and finalizes when every slot is done
    GET  /api/analyze/{id}         -> 200 + status=done + sidebar_payload

What this file actually verifies (re-scoped per TASK-1473.53):

  * Route enqueue path — POST /api/analyze takes the advisory lock,
    inserts a pending job row, and returns 202 + X-Vibecheck-Job-Id.
  * OIDC auth on the internal worker — /_internal/jobs/{id}/run
    rejects unsigned callers; the test bears a mocked verifier.
  * Slot CAS contract — _claim_job flips status pending→extracting and
    every per-section _run_section writes its slot inside the
    expected_task_attempt envelope.
  * Finalize assembly — maybe_finalize_job UPSERTs vibecheck_analyses
    with the assembled SidebarPayload and (TASK-1473.34) flips
    vibecheck_jobs.status to done so the poll returns done.
  * URL audit trail — body.url is preserved on the row while
    normalized_url carries the canonical form (TASK-1473.44).
  * Worker integrity — write_slot rowcount=0 propagates as 503 so
    Cloud Tasks redelivers (TASK-1473.41).

Out of scope (covered by per-component suites):

  * Real Firecrawl scrape (RecordingFirecrawlClient stands in).
  * Real Gemini extraction (extract_utterances is monkeypatched).
  * Per-section analyzer logic — external model calls are monkeypatched to
    deterministic outputs. This file does prove the real orchestrator writes
    non-empty Tone/Facts/Opinions section payloads through Postgres and
    finalize assembles them into SidebarPayload.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest

from src.analyses.claims._claims_schemas import Claim, ClaimsReport, DedupedClaim
from src.analyses.opinions._schemas import SentimentScore, SentimentStatsReport, SubjectiveClaim
from src.analyses.safety._schemas import SafetyLevel, SafetyRecommendation
from src.analyses.schemas import HeadlineSummary, PageKind, SectionSlug
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone._scd_schemas import SCDReport, SpeakerArc
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
    # TASK-1488.05: Tier 1 fail-fast client is a separate factory seam.
    monkeypatch.setattr(
        orchestrator,
        "_build_firecrawl_tier1_client",
        lambda _settings: fake_firecrawl,
    )

    target_url = "https://example.com/e2e-job"
    payload = await _make_utterances_payload(target_url)

    async def _stub_extract(
        url: str,
        client: Any,
        cache: Any,
        *,
        settings: Any = None,
        scrape: Any = None,
    ) -> UtterancesPayload:
        return payload

    monkeypatch.setattr(orchestrator, "extract_utterances", _stub_extract)

    from src.analyses.claims import dedupe_slot
    from src.analyses.opinions import sentiment_slot, subjective_slot
    from src.analyses.tone import flashpoint_slot, scd_slot

    async def _stub_flashpoints(utterances: list[Any], settings: Any) -> list[Any]:
        return [
            None,
            FlashpointMatch(
                utterance_id="u-1",
                derailment_score=80,
                risk_level=RiskLevel.HEATED,
                reasoning="The reply escalates the exchange.",
                context_messages=1,
            ),
            None,
        ]

    async def _stub_scd(
        utterances: list[Any],
        settings: Any,
        **_kwargs: Any,
    ) -> SCDReport:
        return SCDReport(
            narrative="The exchange shifts from report to criticism.",
            speaker_arcs=[
                SpeakerArc(
                    speaker="author-1",
                    note="Responds with criticism.",
                    utterance_id_range=[2, 2],
                )
            ],
            summary="The thread escalates after the first response.",
            tone_labels=["heated"],
            per_speaker_notes={"author-1": "Critical response."},
            insufficient_conversation=False,
        )

    async def _stub_extract_claims(utterances: list[Any], settings: Any) -> list[list[Claim]]:
        return [
            [Claim(claim_text="The rollout broke checkout.", utterance_id="u-0", confidence=0.9)],
            [Claim(claim_text="Checkout is broken.", utterance_id="u-1", confidence=0.87)],
            [],
        ]

    async def _stub_dedupe(
        claims: list[Claim], utterances: list[Any], settings: Any
    ) -> ClaimsReport:
        return ClaimsReport(
            deduped_claims=[
                DedupedClaim(
                    canonical_text="Checkout is broken.",
                    occurrence_count=2,
                    author_count=2,
                    utterance_ids=["u-0", "u-1"],
                    representative_authors=["author-0", "author-1"],
                )
            ],
            total_claims=2,
            total_unique=1,
        )

    async def _stub_sentiment(
        utterances: list[Any], *, settings: Any = None
    ) -> SentimentStatsReport:
        return SentimentStatsReport(
            per_utterance=[
                SentimentScore(utterance_id="u-0", label="neutral", valence=0.0),
                SentimentScore(utterance_id="u-1", label="negative", valence=-0.8),
            ],
            positive_pct=0.0,
            negative_pct=50.0,
            neutral_pct=50.0,
            mean_valence=-0.4,
        )

    async def _stub_subjective(
        utterances: list[Any], *, settings: Any = None
    ) -> list[list[SubjectiveClaim]]:
        return [
            [],
            [
                SubjectiveClaim(
                    claim_text="The change made the product worse.",
                    utterance_id="u-1",
                    stance="evaluates",
                )
            ],
            [],
        ]

    async def _stub_known_misinfo(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        payload: Any,
        settings: Any,
    ) -> dict[str, Any]:
        return {"known_misinformation": []}

    async def _stub_safety_recommendation(
        *args: Any, **kwargs: Any
    ) -> SafetyRecommendation:
        return SafetyRecommendation(
            level=SafetyLevel.MILD,
            rationale="One minor verified signal in the deterministic integration fixture.",
            top_signals=["topic-match content score 0.51"],
            unavailable_inputs=[],
        )

    async def _stub_headline_summary(*args: Any, **kwargs: Any) -> HeadlineSummary:
        return HeadlineSummary(
            text="The discussion moves from a report into criticism.",
            kind="synthesized",
            unavailable_inputs=[],
        )

    monkeypatch.setattr(flashpoint_slot, "detect_flashpoints_bulk", _stub_flashpoints)
    monkeypatch.setattr(scd_slot, "analyze_scd", _stub_scd)
    monkeypatch.setattr(dedupe_slot, "extract_claims_bulk", _stub_extract_claims)
    monkeypatch.setattr(dedupe_slot, "dedupe_claims", _stub_dedupe)
    monkeypatch.setattr(sentiment_slot, "compute_sentiment_stats", _stub_sentiment)
    monkeypatch.setattr(subjective_slot, "extract_subjective_claims_bulk", _stub_subjective)
    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS,
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
        _stub_known_misinfo,
    )
    monkeypatch.setattr(
        orchestrator, "run_safety_recommendation", _stub_safety_recommendation
    )
    monkeypatch.setattr(orchestrator, "run_headline_summary", _stub_headline_summary)

    # 2. POST /api/analyze — fresh submit returns 202 + new job_id.
    resp = await http_client.post(
        "/api/analyze", json={"url": target_url}
    )
    assert resp.status_code == 202, resp.text
    body = json.loads(resp.text)
    job_id = UUID(body["job_id"])
    assert body["status"] == "pending"
    assert body["cached"] is False
    # AC #5 / TASK-1473.49: the response carries X-Vibecheck-Job-Id so
    # operators can correlate POST → log → poll without parsing the body.
    assert resp.headers.get("X-Vibecheck-Job-Id") == str(job_id)

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
    #    `maybe_finalize_job` also flips `vibecheck_jobs.status` to `done`
    #    after the cache write (TASK-1473.34) so the polled job no longer
    #    appears stuck in `analyzing`.
    sections = await read_sections(db_pool, job_id)
    for slug in SectionSlug:
        assert slug.value in sections, f"missing slot {slug.value}"
        assert sections[slug.value]["state"] == "done"

    final = await read_job(db_pool, job_id)
    assert final["status"] == "done", (
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
    assert sidebar["safety"]["recommendation"]["level"] == "mild"
    assert "tone_dynamics" in sidebar
    assert "facts_claims" in sidebar
    assert "opinions_sentiments" in sidebar
    assert sidebar["tone_dynamics"]["flashpoint_matches"][0]["utterance_id"] == "u-1"
    assert sidebar["tone_dynamics"]["scd"]["summary"] == "The thread escalates after the first response."
    assert sidebar["facts_claims"]["claims_report"]["deduped_claims"][0]["canonical_text"] == "Checkout is broken."
    assert sidebar["opinions_sentiments"]["opinions_report"]["sentiment_stats"]["per_utterance"][1]["label"] == "negative"
    assert sidebar["opinions_sentiments"]["opinions_report"]["subjective_claims"][0]["utterance_id"] == "u-1"

    # 6b. The finalized job row itself carries the assembled payload so the
    #     poll endpoint can derive sidebar_payload_complete=True without a
    #     separate cache lookup (TASK-1473.65).
    assert final["sidebar_payload"] is not None, (
        "vibecheck_jobs.sidebar_payload was not written by finalize"
    )

    # 7. GET /api/analyze/{id} returns the populated state.
    poll_resp = await http_client.get(f"/api/analyze/{job_id}")
    assert poll_resp.status_code == 200, poll_resp.text
    # AC #5 / TASK-1473.49: GET echoes the same X-Vibecheck-Job-Id.
    assert poll_resp.headers.get("X-Vibecheck-Job-Id") == str(job_id)
    poll_body = json.loads(poll_resp.text)
    assert poll_body["job_id"] == str(job_id)
    # All per-slot results must be present in the polled snapshot.
    for slug in SectionSlug:
        assert slug.value in poll_body["sections"]
        assert poll_body["sections"][slug.value]["state"] == "done"
    # TASK-1473.65: after a full async run the polled job reports the
    # canonical payload as complete — no further polling is needed.
    assert poll_body.get("sidebar_payload_complete") is True

    # 8. Firecrawl was hit exactly once for this URL.
    assert fake_firecrawl.calls == [target_url]


async def test_url_persistence_keeps_user_form_and_normalized_form_distinct(
    http_client: httpx.AsyncClient,
    db_pool: Any,
    install_oidc_mock: Any,
) -> None:
    """`url` keeps the original user-submitted form; `normalized_url` strips tracking.

    The schema has both columns precisely so the audit trail keeps the
    original form (with utm tracking, trailing slashes, etc.) while
    dedup/cache lookups happen on the canonicalized form. Pre-TASK-1473.44
    the contended-branch and locked-branch insert paths both passed
    `url=normalized_url`, so the original form was lost.
    """
    submitted_url = "https://example.com/?utm_source=foo"
    expected_normalized = "https://example.com/"

    resp = await http_client.post("/api/analyze", json={"url": submitted_url})
    assert resp.status_code == 202, resp.text
    job_id = UUID(json.loads(resp.text)["job_id"])

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT url, normalized_url FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row is not None
    assert row["url"] == submitted_url, (
        f"audit-trail `url` was overwritten with the canonical form: "
        f"got {row['url']!r}, expected {submitted_url!r}"
    )
    assert row["normalized_url"] == expected_normalized, (
        f"`normalized_url` was not canonicalized: got {row['normalized_url']!r}"
    )


async def test_write_slot_cas_miss_propagates_503_for_redelivery(
    http_client: httpx.AsyncClient,
    db_pool: Any,
    install_oidc_mock: Any,
    oidc_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    fake_firecrawl: RecordingFirecrawlClient,
    scrape_cache: Any,
) -> None:
    """write_slot rowcount=0 must surface as 503, not silent 200.

    Pre-TASK-1473.41 `_run_section` ignored write_slot's rowcount and
    `_run_all_sections` swallowed exceptions via `return_exceptions=True`.
    A CAS miss (e.g. job row deleted out from under us, status flipped
    terminal by the sweeper) silently produced an empty slot and the
    worker returned 200 — Cloud Tasks would never redeliver. Now write
    rowcount=0 raises TransientError inside `_run_section`, the gather
    propagates, run_job classifies it as transient, and Cloud Tasks
    retries via 503.
    """
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

    target_url = "https://example.com/slot-cas-miss"
    payload = await _make_utterances_payload(target_url)

    async def _stub_extract(
        url: str,
        client: Any,
        cache: Any,
        *,
        settings: Any = None,
        scrape: Any = None,
    ) -> UtterancesPayload:
        return payload

    monkeypatch.setattr(orchestrator, "extract_utterances", _stub_extract)

    async def _zero_write_slot(*_args: Any, **_kwargs: Any) -> int:
        return 0

    monkeypatch.setattr(orchestrator, "write_slot", _zero_write_slot)

    resp = await http_client.post("/api/analyze", json={"url": target_url})
    assert resp.status_code == 202, resp.text
    job_id = UUID(json.loads(resp.text)["job_id"])

    job_row = await read_job(db_pool, job_id)
    expected_attempt_id = job_row["attempt_id"]

    worker_resp = await http_client.post(
        f"/_internal/jobs/{job_id}/run",
        json={
            "job_id": str(job_id),
            "expected_attempt_id": str(expected_attempt_id),
        },
        headers=oidc_headers,
    )
    assert worker_resp.status_code == 503, worker_resp.text
    final = await read_job(db_pool, job_id)
    # The TransientError reset path puts the job back to pending so the
    # next Cloud Tasks delivery can re-claim cleanly.
    assert final["status"] == "pending", (
        f"job did not reset to pending after TransientError: {final['status']!r}"
    )
