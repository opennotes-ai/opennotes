"""Unit tests for orchestrator internal logic (TASK-1473.59).

The full pipeline integration is covered by test_worker.py (HTTP surface).
These tests focus on internal helpers that are easier to drive in isolation
without standing up Postgres or the FastAPI app.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from src.analyses.safety._schemas import SafetyLevel, SafetyRecommendation
from src.analyses.schemas import ErrorCode, SectionSlug, SectionState
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.firecrawl_client import (
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
    ScrapeMetadata,
    ScrapeResult,
)
from src.jobs.orchestrator import TerminalError, TransientError, _run_section
from src.utterances.errors import UtteranceExtractionError

# ---------------------------------------------------------------------------
# TASK-1473.59 regression — write_slot DB failure must propagate as
# TransientError so Cloud Tasks redelivers.
# ---------------------------------------------------------------------------


async def test_run_section_write_slot_exception_raises_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for TASK-1473.59.

    A write_slot DB failure must propagate as TransientError so Cloud
    Tasks redelivers. Previously the except block swallowed the error and
    the job got stuck in analyzing.
    """
    from src.jobs import orchestrator

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(orchestrator, "write_slot", boom)

    mark_slot_called = []

    async def mock_mark_slot_failed(*args, **kwargs):
        mark_slot_called.append(kwargs)
        return 0

    monkeypatch.setattr(orchestrator, "mark_slot_failed", mock_mark_slot_failed)

    pool = MagicMock()
    job_id = uuid4()
    task_attempt = uuid4()
    slug = SectionSlug.SAFETY_MODERATION
    payload = MagicMock()
    settings = MagicMock()

    with pytest.raises(TransientError, match="write_slot failed"):
        await _run_section(pool, job_id, task_attempt, slug, payload, settings)

    assert len(mark_slot_called) == 1, "mark_slot_failed should have been called once"


async def test_run_section_write_slot_exception_still_raises_when_mark_slot_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both write_slot and mark_slot_failed fail, TransientError still
    propagates (the double-failure is logged and suppressed internally).
    """
    from src.jobs import orchestrator

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(orchestrator, "write_slot", boom)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", boom)

    pool = MagicMock()
    job_id = uuid4()
    task_attempt = uuid4()
    slug = SectionSlug.SAFETY_WEB_RISK
    payload = MagicMock()
    settings = MagicMock()

    with pytest.raises(TransientError, match="write_slot failed"):
        await _run_section(pool, job_id, task_attempt, slug, payload, settings)


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class SafetyRecommendationConn:
    def __init__(self, sections, *, attempt_matches: bool = True) -> None:
        self.sections = sections
        self.attempt_matches = attempt_matches
        self.written = None

    async def fetchrow(self, query, job_id, task_attempt):
        if not self.attempt_matches:
            return None
        return {"sections": self.sections}

    async def execute(self, query, job_id, recommendation_json, task_attempt):
        self.written = {
            "query": query,
            "job_id": job_id,
            "recommendation_json": recommendation_json,
            "task_attempt": task_attempt,
        }
        return "UPDATE 1" if self.attempt_matches else "UPDATE 0"


def _slot(state: SectionState, data=None):
    return {
        "state": state.value,
        "attempt_id": str(uuid4()),
        "data": data,
        "error": None,
        "started_at": None,
        "finished_at": None,
    }


def _sections_for_safety_step(**overrides):
    sections = {
        SectionSlug.SAFETY_MODERATION.value: _slot(
            SectionState.DONE,
            {
                "harmful_content_matches": [
                    {
                        "utterance_id": "u1",
                        "utterance_text": "harmful text",
                        "max_score": 0.91,
                        "categories": {"harassment": True},
                        "scores": {"harassment": 0.91},
                        "flagged_categories": ["harassment"],
                        "source": "openai",
                    }
                ]
            },
        ),
        SectionSlug.SAFETY_WEB_RISK.value: _slot(
            SectionState.DONE,
            {"findings": [{"url": "https://bad.example", "threat_types": ["MALWARE"]}]},
        ),
        SectionSlug.SAFETY_IMAGE_MODERATION.value: _slot(SectionState.DONE, {"matches": []}),
        SectionSlug.SAFETY_VIDEO_MODERATION.value: _slot(SectionState.DONE, {"matches": []}),
    }
    sections.update(overrides)
    return sections


async def test_safety_recommendation_step_writes_serialized_recommendation(monkeypatch):
    from src.jobs import orchestrator

    calls = []

    async def fake_run(inputs, settings):
        calls.append(inputs)
        return SafetyRecommendation(
            level=SafetyLevel.UNSAFE,
            rationale="Verified malware URL and high moderation score.",
            top_signals=["Web Risk MALWARE on https://bad.example"],
        )

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)

    job_id = uuid4()
    task_attempt = uuid4()
    conn = SafetyRecommendationConn(_sections_for_safety_step())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn), job_id, task_attempt, MagicMock()
    )

    assert calls[0].web_risk_findings[0].threat_types == ["MALWARE"]
    assert conn.written is not None
    assert '"level": "unsafe"' in conn.written["recommendation_json"]
    assert conn.written["task_attempt"] == task_attempt


async def test_safety_recommendation_step_marks_failed_slots_unavailable(monkeypatch):
    from src.jobs import orchestrator

    calls = []

    async def fake_run(inputs, settings):
        calls.append(inputs)
        return SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Some inputs were unavailable.",
            unavailable_inputs=inputs.unavailable_inputs,
        )

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)

    conn = SafetyRecommendationConn(
        _sections_for_safety_step(
            **{
                SectionSlug.SAFETY_WEB_RISK.value: _slot(SectionState.FAILED),
                SectionSlug.SAFETY_VIDEO_MODERATION.value: _slot(SectionState.FAILED),
            }
        )
    )

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn), uuid4(), uuid4(), MagicMock()
    )

    assert calls[0].web_risk_findings == []
    assert calls[0].video_moderation_matches == []
    assert calls[0].unavailable_inputs == ["web_risk", "video_moderation"]


async def test_safety_recommendation_step_swallows_agent_exception(monkeypatch):
    from src.jobs import orchestrator

    async def fake_run(inputs, settings):
        raise RuntimeError("agent unavailable")

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    conn = SafetyRecommendationConn(_sections_for_safety_step())

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn), uuid4(), uuid4(), MagicMock()
    )

    assert conn.written is None


async def test_safety_recommendation_step_noops_when_attempt_rotates(monkeypatch):
    from src.jobs import orchestrator

    async def fake_run(inputs, settings):
        raise AssertionError("agent should not run when the attempt row is gone")

    monkeypatch.setattr(orchestrator, "run_safety_recommendation", fake_run)
    conn = SafetyRecommendationConn(_sections_for_safety_step(), attempt_matches=False)

    await orchestrator._run_safety_recommendation_step(
        FakePool(conn), uuid4(), uuid4(), MagicMock()
    )

    assert conn.written is None


# ---------------------------------------------------------------------------
# TASK-1474.23.02 — post-Gemini stage tracking, top-level try/except,
# heartbeat lifecycle logs.
#
# `_set_last_stage` writes (CAS-on-attempt_id) and DB-failure swallowing
# moved to `tests/integration/test_orchestrator_db.py` so the CAS guard
# is exercised against real Postgres (TASK-1474.23.03.12). The
# in-process `_StageRecorderConn` / `_ExecuteFailingConn` fakes had no
# notion of `attempt_id` and could not catch a regression that drops
# the `AND attempt_id = $3` clause.
# ---------------------------------------------------------------------------


def _stub_pre_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit the scrape/extract preamble so tests focus on post-Gemini."""
    from src.jobs import orchestrator

    monkeypatch.setattr(orchestrator, "_build_scrape_cache", lambda s: MagicMock())
    monkeypatch.setattr(orchestrator, "_build_firecrawl_client", lambda s: MagicMock())

    async def stub_scrape_step(*args, **kwargs):
        return MagicMock(metadata=None)

    async def stub_revalidate(*args, **kwargs):
        return None

    async def stub_extract(*args, **kwargs):
        return MagicMock()

    monkeypatch.setattr(orchestrator, "_scrape_step", stub_scrape_step)
    monkeypatch.setattr(orchestrator, "_revalidate_final_url", stub_revalidate)
    monkeypatch.setattr(orchestrator, "extract_utterances", stub_extract)


async def test_run_pipeline_logs_traceback_on_unclassified_post_gemini_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repro the silent-death pattern: a non-classified exception that fires
    after extract_utterances returns must surface as a logged traceback at
    the orchestrator boundary, not silently propagate without a breadcrumb.
    """
    from src.jobs import orchestrator

    _stub_pre_gemini(monkeypatch)

    async def noop_set_last_stage(*args, **kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_set_last_stage", noop_set_last_stage)

    async def boom(*args, **kwargs):
        raise RuntimeError("post-gemini handler exploded")

    monkeypatch.setattr(orchestrator, "persist_utterances", boom)

    caplog.set_level(logging.ERROR, logger="src.jobs.orchestrator")

    with pytest.raises(RuntimeError, match="post-gemini handler exploded"):
        await orchestrator._run_pipeline(
            MagicMock(), uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    crash_records = [
        r for r in caplog.records if "post-gemini handler crashed" in r.message
    ]
    assert len(crash_records) == 1, (
        f"expected exactly one crash log; got {[r.message for r in caplog.records]}"
    )
    assert crash_records[0].exc_info is not None


async def test_run_pipeline_writes_last_stage_breadcrumb_at_persist_utterances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first post-Gemini stage marker is written before persist_utterances
    runs; if persist_utterances raises, the breadcrumb is still in place so
    a DB query can pinpoint where the worker died.
    """
    from src.jobs import orchestrator

    _stub_pre_gemini(monkeypatch)

    stage_calls: list[str] = []

    async def spy_set_last_stage(pool, job_id, task_attempt, stage):
        stage_calls.append(stage)

    monkeypatch.setattr(orchestrator, "_set_last_stage", spy_set_last_stage)

    async def boom(*args, **kwargs):
        raise RuntimeError("stop here")

    monkeypatch.setattr(orchestrator, "persist_utterances", boom)

    with pytest.raises(RuntimeError):
        await orchestrator._run_pipeline(
            MagicMock(), uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    assert "persist_utterances" in stage_calls


async def test_heartbeat_loop_logs_start_and_cancel_lifecycle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Heartbeat task must log its own start/stop so we can distinguish
    a heartbeat-task death from a main-handler death (TASK-1474.23.02 AC4)."""
    from src.jobs import orchestrator

    class HeartbeatConn:
        async def execute(self, *args, **kwargs):
            return "UPDATE 1"

    pool = FakePool(HeartbeatConn())
    job_id = uuid4()
    task_attempt = uuid4()

    caplog.set_level(logging.INFO, logger="src.jobs.orchestrator")

    task = asyncio.create_task(
        orchestrator._heartbeat_loop(pool, job_id, task_attempt, interval_sec=0.01)
    )
    await asyncio.sleep(0.03)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    info_msgs = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any("heartbeat: started" in m for m in info_msgs), info_msgs
    assert any("heartbeat: cancelled" in m for m in info_msgs), info_msgs


# ---------------------------------------------------------------------------
# TASK-1474.23.03.04 — three-arm classification of extract_utterances
# errors + in-row backstop counter (CAS on attempt_id with RETURNING).
# ---------------------------------------------------------------------------


def _stub_extract_arm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit scrape/build/revalidate so the test focuses on the
    extract arm's three-way classification. extract_utterances itself is
    NOT stubbed here — the test sets that per-case to raise the specific
    exception type under test.
    """
    from src.jobs import orchestrator

    monkeypatch.setattr(orchestrator, "_build_scrape_cache", lambda s: MagicMock())
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda s: MagicMock()
    )

    async def stub_scrape_step(*args, **kwargs):
        return MagicMock(metadata=None)

    async def stub_revalidate(*args, **kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_scrape_step", stub_scrape_step)
    monkeypatch.setattr(orchestrator, "_revalidate_final_url", stub_revalidate)


# Migrated tests live in `tests/integration/test_orchestrator_db.py`:
#   - test_run_pipeline_translates_transient_extraction_error_to_transient
#   - test_run_pipeline_backstop_escalates_to_terminal_at_max
# Both exercise the in-row backstop counter against real Postgres so
# the CAS-on-attempt_id guard on `_INCREMENT_EXTRACT_TRANSIENT_SQL` is
# actually verified; the in-process `_IncrementCounterConn` fake had
# no notion of `attempt_id` (TASK-1474.23.03.12).


async def test_run_pipeline_treats_utterance_extraction_error_as_terminal_extraction_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse / no-utterances / output-validation failures classify as
    TerminalError(EXTRACTION_FAILED), NOT UPSTREAM_ERROR, and do NOT
    reach the transient backstop counter (it's a content-shape
    problem, not an upstream flake — only TransientExtractionError
    invokes `_increment_extract_transient_attempts`).
    """
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator
    from src.utterances.errors import UtteranceExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_terminal(*args, **kwargs):
        raise UtteranceExtractionError("agent returned empty utterances")

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_terminal)

    increment_spy = AsyncMock()
    monkeypatch.setattr(
        orchestrator, "_increment_extract_transient_attempts", increment_spy
    )

    pool = MagicMock()
    job_id = uuid4()
    task_attempt = uuid4()

    with pytest.raises(orchestrator.TerminalError) as info:
        await orchestrator._run_pipeline(
            pool, job_id, task_attempt, "https://example.com", MagicMock()
        )

    assert info.value.error_code == ErrorCode.EXTRACTION_FAILED
    assert "agent returned empty utterances" in info.value.error_detail
    increment_spy.assert_not_called()


async def test_run_pipeline_unexpected_exception_falls_through_to_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive catch: anything not classified by the typed arms is
    still terminal (EXTRACTION_FAILED) so the worker can never loop
    forever on an unknown bug. The transient backstop counter is not
    reached — only TransientExtractionError invokes
    `_increment_extract_transient_attempts`.
    """
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator

    _stub_extract_arm_only(monkeypatch)

    async def boom(*args, **kwargs):
        raise RuntimeError("kaboom unknown bug")

    monkeypatch.setattr(orchestrator, "extract_utterances", boom)

    increment_spy = AsyncMock()
    monkeypatch.setattr(
        orchestrator, "_increment_extract_transient_attempts", increment_spy
    )

    pool = MagicMock()
    job_id = uuid4()
    task_attempt = uuid4()

    with pytest.raises(orchestrator.TerminalError) as info:
        await orchestrator._run_pipeline(
            pool, job_id, task_attempt, "https://example.com", MagicMock()
        )

    assert info.value.error_code == ErrorCode.EXTRACTION_FAILED
    assert "kaboom unknown bug" in info.value.error_detail
    increment_spy.assert_not_called()


async def test_run_pipeline_falls_back_to_transient_when_column_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Backward-compat: if the extract_transient_attempts column is missing
    (deploy where the schema migration hasn't run yet), the
    UndefinedColumnError is caught and behavior degrades gracefully to
    TransientError. Cloud Tasks redelivers, and the system behaves
    exactly like it did before the backstop existed — no crash, no
    spurious terminal flips.
    """
    from src.jobs import orchestrator
    from src.utterances.errors import TransientExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_transient(*args, **kwargs):
        raise TransientExtractionError(
            provider="vertex",
            status_code=503,
            status="UNAVAILABLE",
            fallback_message="Vertex 503",
        )

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_transient)

    class _MissingColumnConn:
        async def fetchval(self, sql: str, *args: Any) -> int:
            raise asyncpg.UndefinedColumnError(
                'column "extract_transient_attempts" does not exist'
            )

    pool = FakePool(_MissingColumnConn())
    caplog.set_level(logging.WARNING, logger="src.jobs.orchestrator")

    with pytest.raises(orchestrator.TransientError):
        await orchestrator._run_pipeline(
            pool, uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    # Warning surfaced so operators know the migration hasn't propagated.
    assert any(
        "extract_transient_attempts column missing" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]


async def test_run_pipeline_falls_back_to_transient_when_increment_db_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the increment SQL hits a connection-class transient (asyncpg
    InterfaceError / PostgresConnectionError), the helper returns None
    and the orchestrator classifies as TransientError rather than terminal.
    Best-effort: prefer redelivery > silent loss. AC#4 for TASK-1474.23.03.04.

    Programming bugs (RuntimeError, SQL syntax errors) are NOT swallowed —
    those bubble up to the outer except as TerminalError(EXTRACTION_FAILED)
    so a regression that breaks the increment SQL doesn't silently
    disable the backstop forever. See test_run_pipeline_unexpected_increment_error_terminates.
    """
    import asyncpg

    from src.jobs import orchestrator
    from src.utterances.errors import TransientExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_transient(*args, **kwargs):
        raise TransientExtractionError(
            provider="firecrawl",
            status_code=502,
            status="HTTP_502",
            fallback_message="Firecrawl 502",
        )

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_transient)

    class _DbDownConn:
        async def fetchval(self, sql: str, *args: Any) -> int:
            raise asyncpg.InterfaceError("connection lost")

    pool = FakePool(_DbDownConn())
    caplog.set_level(logging.WARNING, logger="src.jobs.orchestrator")

    with pytest.raises(orchestrator.TransientError):
        await orchestrator._run_pipeline(
            pool, uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    # Warning surfaced so operators see the failure (AC#4 visibility).
    assert any(
        "extract_transient_attempts increment hit DB connection error" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]


@pytest.mark.asyncio
async def test_run_pipeline_unexpected_increment_error_terminates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected exception during increment (programming bug, SQL
    syntax) is wrapped as TerminalError(EXTRACTION_FAILED) at the call
    site so the row flips to failed instead of silently looping. Without
    this wrap, the bare exception would escape `_run_pipeline` and land
    in `run_job`'s unclassified-Exception branch, which resets the row
    to pending and returns 503 — defeating the entire backstop because
    the counter never advances and Cloud Tasks silently exhausts at
    max_attempts=3.
    """
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator
    from src.utterances.errors import TransientExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_transient(*args, **kwargs):
        raise TransientExtractionError(
            provider="vertex",
            status_code=504,
            status="DEADLINE_EXCEEDED",
            fallback_message="Vertex 504",
        )

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_transient)

    class _BuggyConn:
        async def fetchval(self, sql: str, *args: Any) -> int:
            raise RuntimeError("simulated SQL syntax error")

    pool = FakePool(_BuggyConn())

    with pytest.raises(orchestrator.TerminalError) as exc_info:
        await orchestrator._run_pipeline(
            pool, uuid4(), uuid4(), "https://example.com", MagicMock()
        )
    assert exc_info.value.error_code == ErrorCode.EXTRACTION_FAILED
    assert "backstop counter increment failed" in exc_info.value.error_detail


# ---------------------------------------------------------------------------
# TASK-1488.05 — Tiered scrape ladder: /scrape (Tier 1) → /interact (Tier 2).
# ---------------------------------------------------------------------------
#
# These tests drive the new `_scrape_step` policy directly (no FastAPI / DB).
# We mock the FirecrawlClient and SupabaseScrapeCache I/O surfaces only;
# `classify_scrape` is the real Wave 1 implementation so quality routing is
# exercised end-to-end through the public seam.
#
# Key invariants:
#   - AUTH_WALL  + LEGITIMATELY_EMPTY  → terminal pre-Gemini, NO /interact.
#   - INTERSTITIAL + FirecrawlBlocked  → escalate to /interact.
#   - Both tiers fail (any non-OK on Tier 2) → TerminalError(UNSUPPORTED_SITE).
#   - Cache reads/writes use the tier dimension; INTERSTITIAL Tier 1 result
#     IS cached so a retry can skip the cheap-tier classifier.


class _FakeScrapeCache:
    """In-memory `SupabaseScrapeCache` substitute keyed by (url, tier).

    Records every get/put/evict call so tests can assert tier dimension
    is respected. Matches the real cache's `tier` kwarg surface.
    """

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], CachedScrape] = {}
        self.gets: list[tuple[str, str]] = []
        self.puts: list[tuple[str, str]] = []
        self.evicts: list[tuple[str, str | None]] = []

    async def get(
        self, url: str, *, tier: str = "scrape"
    ) -> CachedScrape | None:
        self.gets.append((url, tier))
        return self.store.get((url, tier))

    async def put(
        self, url: str, scrape: ScrapeResult, *, tier: str = "scrape"
    ) -> CachedScrape:
        self.puts.append((url, tier))
        cached = CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=scrape.raw_html,
            screenshot=scrape.screenshot,
            links=scrape.links,
            metadata=scrape.metadata,
            warning=scrape.warning,
            storage_key=f"{tier}-key-{len(self.puts)}",
        )
        self.store[(url, tier)] = cached
        return cached

    async def evict(self, url: str, *, tier: str | None = None) -> None:
        self.evicts.append((url, tier))


class _FakeFirecrawlClient:
    """FirecrawlClient stand-in scripted with per-method results.

    Pass a callable for `scrape_result` / `interact_result` to either
    return a `ScrapeResult` or raise (e.g. `FirecrawlBlocked`). Tracks
    every call so tests can assert call counts and the action list
    handed to /interact.
    """

    def __init__(
        self,
        *,
        scrape_result: Any = None,
        interact_result: Any = None,
    ) -> None:
        self._scrape_result = scrape_result
        self._interact_result = interact_result
        self.scrape_calls: list[tuple[str, dict[str, Any]]] = []
        self.interact_calls: list[tuple[str, dict[str, Any]]] = []

    async def scrape(self, url: str, **kwargs: Any) -> ScrapeResult:
        self.scrape_calls.append((url, kwargs))
        return self._dispatch(self._scrape_result)

    async def interact(
        self, url: str, actions: list[dict[str, Any]], **kwargs: Any
    ) -> ScrapeResult:
        merged = {"actions": actions, **kwargs}
        self.interact_calls.append((url, merged))
        return self._dispatch(self._interact_result)

    @staticmethod
    def _dispatch(result: Any) -> ScrapeResult:
        if callable(result):
            return cast(ScrapeResult, result())
        if result is None:
            raise AssertionError("test did not script a result for this call")
        return cast(ScrapeResult, result)


def _ok_scrape_result(*, body: str = "Substantive article body. " * 20) -> ScrapeResult:
    return ScrapeResult(
        markdown=f"# Real Article\n\n{body}",
        html=f"<html><body><article><h1>Real Article</h1><p>{body}</p></article></body></html>",
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com/post"),
    )


def _interstitial_scrape_result() -> ScrapeResult:
    return ScrapeResult(
        markdown="Just a moment...",
        html=(
            "<html><body><div class='cf-browser-verification'>"
            "Just a moment</div></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com"),
    )


def _auth_wall_scrape_result() -> ScrapeResult:
    return ScrapeResult(
        markdown="Sign in to continue",
        html=(
            "<html><body><form action='/login'>"
            "<input type='password' name='pw'></form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com/post"),
    )


def _legit_empty_scrape_result() -> ScrapeResult:
    return ScrapeResult(
        markdown="Page not found",
        html="<html><body>Page not found</body></html>",
        metadata=ScrapeMetadata(status_code=404, source_url="https://example.com/gone"),
    )


async def _call_scrape_step(
    url: str,
    scrape_client: _FakeFirecrawlClient,
    interact_client: _FakeFirecrawlClient,
    cache: _FakeScrapeCache,
) -> CachedScrape:
    """Type-cast helper around `_scrape_step` so test fakes (which match
    the structural API but not the nominal type) flow through cleanly.
    `object` first so basedpyright's `reportInvalidCast` accepts the cast.
    """
    from src.jobs import orchestrator

    return await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
    )


# AC#1, AC#5 — Tier 1 OK: no escalation, span shows tier_attempted=['scrape'].


async def test_scrape_step_tier1_ok_returns_without_escalation() -> None:
    """OK classification on Tier 1 returns the cached scrape and never
    calls /interact. The Tier 1 cache row is written under tier='scrape'.
    """

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(scrape_result=_ok_scrape_result())
    interact_client = _FakeFirecrawlClient(
        interact_result=lambda: (_ for _ in ()).throw(  # never called
            AssertionError("interact must not run on Tier 1 OK")
        )
    )

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.markdown is not None
    assert "Real Article" in result.markdown
    assert len(scrape_client.scrape_calls) == 1
    assert len(interact_client.interact_calls) == 0
    # Tier 1 result was cached under tier='scrape'.
    assert (url, "scrape") in cache.store
    assert (url, "scrape") in cache.puts


# AC#1, AC#3, AC#4 — FirecrawlBlocked on Tier 1 → escalate; Tier 2 OK returns.


async def test_scrape_step_tier1_blocked_escalates_to_interact_success() -> None:
    """LinkedIn-style refusal on Tier 1 escalates to /interact. The Tier 2
    OK result is what we return, and only the Tier 2 row is cached (since
    the Tier 1 attempt produced no cacheable bundle).
    """

    url = "https://www.linkedin.com/pulse/example"
    cache = _FakeScrapeCache()

    def _blocked() -> ScrapeResult:
        raise FirecrawlBlocked(
            "firecrawl /v2/scrape refused: 403 do not support this site",
            status_code=403,
        )

    scrape_client = _FakeFirecrawlClient(scrape_result=_blocked)
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(body="Tier 2 rendered body. " * 20)
    )

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.markdown is not None
    assert "Tier 2 rendered body" in result.markdown
    assert len(scrape_client.scrape_calls) == 1
    assert len(interact_client.interact_calls) == 1
    # interact was called with a non-empty action list (waits for JS render).
    interact_url, interact_kwargs = interact_client.interact_calls[0]
    assert interact_url == url
    assert isinstance(interact_kwargs["actions"], list)
    assert len(interact_kwargs["actions"]) >= 1
    # Tier 2 row cached; Tier 1 was a refusal (no bundle to cache).
    assert (url, "interact") in cache.store
    assert (url, "interact") in cache.puts
    assert (url, "scrape") not in cache.store


# AC#2, AC#6 — INTERSTITIAL on Tier 1 → escalate; Tier 1 result IS cached.


async def test_scrape_step_tier1_interstitial_caches_then_escalates() -> None:
    """INTERSTITIAL on Tier 1 caches the Tier 1 row (so a retry can skip
    the cheap-tier classifier), then escalates to /interact. Tier 2 OK
    is what we return.
    """

    url = "https://example.com/cf-protected"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_interstitial_scrape_result()
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(body="Real content past CF. " * 20)
    )

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.markdown is not None
    assert "Real content past CF" in result.markdown
    assert len(interact_client.interact_calls) == 1
    # Tier 1 INTERSTITIAL row IS cached so a retry can skip classifier.
    assert (url, "scrape") in cache.store
    assert (url, "interact") in cache.store


# AC#2, AC#6 — AUTH_WALL on Tier 1 → terminal pre-Gemini, NO /interact call.


async def test_scrape_step_tier1_auth_wall_terminates_without_escalation() -> None:
    """AUTH_WALL is a hard ToS line — never escalate. Raises
    TerminalError(EXTRACTION_FAILED) and proves /interact was not called.
    """

    url = "https://members-only.example/article"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_auth_wall_scrape_result()
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=lambda: (_ for _ in ()).throw(
            AssertionError("interact must NOT be called on AUTH_WALL")
        )
    )

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.EXTRACTION_FAILED
    assert "login" in exc_info.value.error_detail.lower() or "auth" in exc_info.value.error_detail.lower()
    # Load-bearing assertion: no /interact call when we hit an auth wall.
    assert len(interact_client.interact_calls) == 0


# AC#2, AC#6 — LEGITIMATELY_EMPTY on Tier 1 → terminal pre-Gemini, no /interact.


async def test_scrape_step_tier1_legitimately_empty_terminates_without_escalation() -> None:
    """LEGITIMATELY_EMPTY (404, deleted, empty) → terminal. No richer fetch
    tier resurrects deleted content; calling /interact would just burn
    Firecrawl quota.
    """

    url = "https://example.com/deleted-post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_legit_empty_scrape_result()
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=lambda: (_ for _ in ()).throw(
            AssertionError("interact must NOT be called on LEGITIMATELY_EMPTY")
        )
    )

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.EXTRACTION_FAILED
    assert "empty" in exc_info.value.error_detail.lower() or "page" in exc_info.value.error_detail.lower()
    assert len(interact_client.interact_calls) == 0


# AC#3 — Both tiers fail → TerminalError(UNSUPPORTED_SITE) with both reasons.


async def test_scrape_step_both_tiers_blocked_raises_unsupported_site() -> None:
    """Tier 1 INTERSTITIAL + Tier 2 still INTERSTITIAL (or any non-OK) →
    TerminalError(UNSUPPORTED_SITE). Both tier reasons surface in the
    error message so operators can see why we gave up.
    """

    url = "https://example.com/cf-everywhere"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_interstitial_scrape_result()
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_interstitial_scrape_result()
    )

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE
    msg = exc_info.value.error_detail.lower()
    # Both tier reasons surface in the message.
    assert "tier 1" in msg or "scrape" in msg
    assert "tier 2" in msg or "interact" in msg


async def test_scrape_step_blocked_then_blocked_raises_unsupported_site() -> None:
    """FirecrawlBlocked on both tiers also yields UNSUPPORTED_SITE."""

    url = "https://hardblocked.example/post"
    cache = _FakeScrapeCache()

    def _blocked_t1() -> ScrapeResult:
        raise FirecrawlBlocked("scrape refused: 403 do not support this site")

    def _blocked_t2() -> ScrapeResult:
        raise FirecrawlBlocked("interact refused: 403 do not support this site")

    scrape_client = _FakeFirecrawlClient(scrape_result=_blocked_t1)
    interact_client = _FakeFirecrawlClient(interact_result=_blocked_t2)

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE


# AC#4 — cache reader honors tier preference (Tier 1 hit short-circuits).


async def test_scrape_step_tier1_cache_hit_skips_firecrawl() -> None:
    """If a Tier 1 cache row exists, return it immediately — no Firecrawl
    call. Asserts the bottom-of-funnel cost-savings property.
    """

    url = "https://example.com/cached-post"
    cache = _FakeScrapeCache()
    cache.store[(url, "scrape")] = CachedScrape(
        markdown="cached body " * 10,
        html="<article>cached body</article>",
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="precached-key",
    )

    def _fail() -> ScrapeResult:
        raise AssertionError("scrape must not be called on Tier 1 cache hit")

    scrape_client = _FakeFirecrawlClient(scrape_result=_fail)
    interact_client = _FakeFirecrawlClient(interact_result=_fail)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.storage_key == "precached-key"
    assert len(scrape_client.scrape_calls) == 0
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier1_cache_hit_with_interstitial_reclassifies_and_escalates() -> None:
    """Codex P1 (TASK-1488 PR #426 review): a Tier 1 cache row classified as
    INTERSTITIAL must NOT short-circuit. The previous run cached the
    degraded bundle so retries can skip the Firecrawl probe — but the
    reclassification on cache hit is what guarantees the ladder still
    escalates to Tier 2 instead of returning the interstitial as if it
    were OK. Without this, every retry of an interstitial-cached URL
    bypasses the Tier 2 escalation that's the whole point of the ladder.
    """

    url = "https://example.com/cf-cached"
    cache = _FakeScrapeCache()
    cache.store[(url, "scrape")] = CachedScrape(
        markdown="Just a moment...",
        html=(
            "<html><body><div class='cf-browser-verification'>"
            "Just a moment</div></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="cached-interstitial-key",
    )

    def _fail_scrape() -> ScrapeResult:
        raise AssertionError("scrape must not run on Tier 1 cache hit")

    scrape_client = _FakeFirecrawlClient(scrape_result=_fail_scrape)
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(body="Real content past CF. " * 20)
    )

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.markdown is not None
    assert "Real content past CF" in result.markdown
    assert len(scrape_client.scrape_calls) == 0
    assert len(interact_client.interact_calls) == 1
    assert (url, "interact") in cache.store


async def test_scrape_step_tier1_cache_hit_with_auth_wall_terminates() -> None:
    """Defense-in-depth: a cached AUTH_WALL Tier 1 row must terminate
    rather than short-circuit. _run_tier1 doesn't currently cache
    AUTH_WALL, but a stale row from an earlier code path or operator
    backfill must not silently bypass the auth-wall ToS guard.
    """

    url = "https://members-only.example/article"
    cache = _FakeScrapeCache()
    cache.store[(url, "scrape")] = CachedScrape(
        markdown="Sign in to continue",
        html=(
            "<html><body><form action='/login'>"
            "<input type='password' name='pw'></form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="cached-auth-wall-key",
    )

    def _fail() -> ScrapeResult:
        raise AssertionError("no Firecrawl call should fire on auth-wall cache hit")

    scrape_client = _FakeFirecrawlClient(scrape_result=_fail)
    interact_client = _FakeFirecrawlClient(interact_result=_fail)

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.EXTRACTION_FAILED
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier2_cache_hit_skips_interact() -> None:
    """If Tier 1 trips escalation but a Tier 2 cache row already exists,
    /interact is not called — the cached interact bundle short-circuits.
    """

    url = "https://example.com/twice-seen"
    cache = _FakeScrapeCache()
    cache.store[(url, "interact")] = CachedScrape(
        markdown="cached interact body " * 10,
        html="<article>cached interact</article>",
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="t2-cached-key",
    )

    def _blocked() -> ScrapeResult:
        raise FirecrawlBlocked("scrape refused: 403 do not support this site")

    def _fail_interact() -> ScrapeResult:
        raise AssertionError(
            "interact must not be called when Tier 2 cache row already exists"
        )

    scrape_client = _FakeFirecrawlClient(scrape_result=_blocked)
    interact_client = _FakeFirecrawlClient(interact_result=_fail_interact)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.storage_key == "t2-cached-key"
    assert len(interact_client.interact_calls) == 0


# AC#5 — Logfire span 'vibecheck.scrape_step' carries the required attributes.


class _RecordingSpan:
    """Captures attribute writes on a fake `logfire.span()` context."""

    def __init__(self) -> None:
        self.attrs: dict[str, Any] = {}

    def __enter__(self) -> _RecordingSpan:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attrs[key] = value

    def set_attributes(self, mapping: dict[str, Any]) -> None:
        self.attrs.update(mapping)


def _install_recording_span(monkeypatch: pytest.MonkeyPatch) -> _RecordingSpan:
    """Replace `logfire.span` with a recorder that returns the same span
    for every call; only the outer `vibecheck.scrape_step` span carries
    the attributes we assert on.
    """
    from src.jobs import orchestrator

    span = _RecordingSpan()

    def _factory(name: str, **kwargs: Any) -> _RecordingSpan:
        # Inline kwargs onto the span so callers that pass attrs as
        # span(...) keyword args still register them.
        span.attrs.update(kwargs)
        return span

    monkeypatch.setattr(orchestrator.logfire, "span", _factory)
    return span


async def test_scrape_step_logfire_span_records_attributes_on_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OK path: span attrs say tier_attempted=['scrape'], tier_success='scrape',
    escalation_reason=None, final_classification='ok'.
    """

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(scrape_result=_ok_scrape_result())
    interact_client = _FakeFirecrawlClient()

    await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("tier_attempted") == ["scrape"]
    assert span.attrs.get("tier_success") == "scrape"
    assert span.attrs.get("escalation_reason") is None
    assert span.attrs.get("final_classification") == "ok"


async def test_scrape_step_logfire_span_records_attributes_on_escalation_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escalation path: tier_attempted=['scrape','interact'],
    tier_success='interact', escalation_reason='firecrawl_blocked',
    final_classification='ok'.
    """

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/refused"
    cache = _FakeScrapeCache()

    def _blocked() -> ScrapeResult:
        raise FirecrawlBlocked("scrape refused: do not support this site")

    scrape_client = _FakeFirecrawlClient(scrape_result=_blocked)
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("tier_attempted") == ["scrape", "interact"]
    assert span.attrs.get("tier_success") == "interact"
    assert span.attrs.get("escalation_reason") == "firecrawl_blocked"
    assert span.attrs.get("final_classification") == "ok"


async def test_scrape_step_logfire_span_records_attributes_on_interstitial_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INTERSTITIAL Tier 1 → escalate: escalation_reason='interstitial'."""

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/cf"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_interstitial_scrape_result()
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("tier_attempted") == ["scrape", "interact"]
    assert span.attrs.get("escalation_reason") == "interstitial"
    assert span.attrs.get("tier_success") == "interact"


async def test_scrape_step_logfire_span_records_attributes_on_terminal_auth_wall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTH_WALL terminal: tier_attempted=['scrape'], tier_success=None,
    final_classification='auth_wall', escalation_reason=None.
    """

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/login"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_auth_wall_scrape_result()
    )
    interact_client = _FakeFirecrawlClient()

    with pytest.raises(TerminalError):
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("tier_attempted") == ["scrape"]
    assert span.attrs.get("tier_success") is None
    assert span.attrs.get("final_classification") == "auth_wall"
    assert span.attrs.get("escalation_reason") is None


async def test_scrape_step_logfire_span_records_attributes_on_unsupported_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both tiers fail: tier_success=None, final_classification reflects
    the Tier 2 quality (e.g. 'interstitial').
    """

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/all-blocked"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_interstitial_scrape_result()
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_interstitial_scrape_result()
    )

    with pytest.raises(TerminalError):
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("tier_attempted") == ["scrape", "interact"]
    assert span.attrs.get("tier_success") is None
    assert span.attrs.get("final_classification") in {"interstitial", "auth_wall", "legitimately_empty"}


# Generic FirecrawlError on Tier 1 (non-blocked): treated as transient, NOT
# silently escalated. Refusal is the only signal that justifies the cheap
# escalation; an upstream 5xx should still go through the normal retry
# budget at run_job.


async def test_scrape_step_tier1_generic_firecrawl_error_raises_transient() -> None:
    """A non-refusal FirecrawlError on Tier 1 surfaces as TransientError
    so Cloud Tasks retries the job (unchanged from pre-1488 behavior).
    """

    url = "https://example.com/upstream-flake"
    cache = _FakeScrapeCache()

    def _boom() -> ScrapeResult:
        raise FirecrawlError("firecrawl /v2/scrape failed: 500 internal", status_code=500)

    scrape_client = _FakeFirecrawlClient(scrape_result=_boom)
    interact_client = _FakeFirecrawlClient()

    with pytest.raises(TransientError):
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert len(interact_client.interact_calls) == 0


# ---------------------------------------------------------------------------
# TASK-1488.06 — `force_tier="interact"` bypass + once-only post-Gemini
# escalation when extract_utterances raises ZeroUtterancesError.
# ---------------------------------------------------------------------------
#
# These tests cover two seams:
#
# 1. `_scrape_step(..., force_tier='interact')` skips Tier 1 entirely. Every
#    Tier 1 side effect (`scrape_client.scrape`, Tier 1 cache reads/writes)
#    must be absent, while Tier 2 runs unchanged.
# 2. `_run_pipeline` catches `ZeroUtterancesError` from the extractor exactly
#    once, re-runs `_scrape_step(force_tier='interact')`, and re-runs
#    extraction. A second 0-utterance result yields
#    `TerminalError(EXTRACTION_FAILED)`. Once-only is enforced by an
#    explicit boolean — there is no recursion or while-loop.


async def test_scrape_step_force_tier_interact_skips_tier1_entirely() -> None:
    """`force_tier='interact'` is the only seam that lets the ladder skip
    Tier 1. The Tier 1 client must be untouched — no scrape call, no Tier 1
    cache read — and Tier 2 runs as if Tier 1 had escalated.
    """
    from src.jobs import orchestrator

    url = "https://example.com/already-knew-tier1-fails"
    cache = _FakeScrapeCache()

    def _fail_tier1() -> ScrapeResult:
        raise AssertionError("scrape must not be called when force_tier='interact'")

    scrape_client = _FakeFirecrawlClient(scrape_result=_fail_tier1)
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    result = await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        force_tier="interact",
    )

    assert result.markdown is not None
    assert "Real Article" in result.markdown
    # Tier 1 client never touched.
    assert len(scrape_client.scrape_calls) == 0
    # Tier 1 cache never read either — the bypass is total.
    assert all(tier == "interact" for _u, tier in cache.gets)
    # Tier 2 ran and the row was cached under tier='interact'.
    assert len(interact_client.interact_calls) == 1
    assert (url, "interact") in cache.store


async def test_scrape_step_force_tier_interact_honors_tier2_cache_hit() -> None:
    """Even with `force_tier='interact'`, an existing Tier 2 cache row
    short-circuits the /interact call. The bypass changes which tier runs,
    not whether the cache is consulted.
    """
    from src.jobs import orchestrator

    url = "https://example.com/cached-tier2"
    cache = _FakeScrapeCache()
    cache.store[(url, "interact")] = CachedScrape(
        markdown="cached interact body " * 10,
        html="<article>cached</article>",
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="t2-precached",
    )

    def _fail() -> ScrapeResult:
        raise AssertionError("no firecrawl call expected on Tier 2 cache hit")

    scrape_client = _FakeFirecrawlClient(scrape_result=_fail)
    interact_client = _FakeFirecrawlClient(interact_result=_fail)

    result = await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        force_tier="interact",
    )

    assert result.storage_key == "t2-precached"
    assert len(scrape_client.scrape_calls) == 0
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_default_call_unchanged_no_force_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default behavior (no `force_tier`) stays identical to 1488.05: Tier 1
    runs, OK classifications return, escalation only fires on the original
    triggers. This is a regression guard against the 1488.06 kwarg leaking
    into the default path.
    """
    from src.jobs import orchestrator

    url = "https://example.com/default-path"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(scrape_result=_ok_scrape_result())
    interact_client = _FakeFirecrawlClient(
        interact_result=lambda: (_ for _ in ()).throw(
            AssertionError("interact must NOT run on Tier 1 OK in default path")
        )
    )

    result = await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
    )

    assert result.markdown is not None
    assert len(scrape_client.scrape_calls) == 1
    assert len(interact_client.interact_calls) == 0


# Pipeline-level escalation tests. Drive `_run_pipeline` directly with the
# pre-Gemini stages stubbed so the assertions are about which scrape/extract
# calls the once-only escalation fires (and how many times).


def _stub_post_gemini_for_escalation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit everything AFTER extract_utterances so the pipeline
    finishes cleanly when extraction succeeds. The escalation logic lives
    BEFORE persist_utterances, so each downstream stage is a no-op here.
    """
    from src.jobs import orchestrator

    async def noop_set_last_stage(*args: Any, **kwargs: Any) -> None:
        return None

    async def noop_persist(*args: Any, **kwargs: Any) -> None:
        return None

    async def noop_set_analyzing(*args: Any, **kwargs: Any) -> None:
        return None

    async def noop_run_sections(*args: Any, **kwargs: Any) -> None:
        return None

    async def noop_safety_rec(*args: Any, **kwargs: Any) -> None:
        return None

    async def noop_finalize(*args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(orchestrator, "_set_last_stage", noop_set_last_stage)
    monkeypatch.setattr(orchestrator, "persist_utterances", noop_persist)
    monkeypatch.setattr(orchestrator, "_set_analyzing", noop_set_analyzing)
    monkeypatch.setattr(orchestrator, "_run_all_sections", noop_run_sections)
    monkeypatch.setattr(
        orchestrator, "_run_safety_recommendation_step", noop_safety_rec
    )
    monkeypatch.setattr(orchestrator, "maybe_finalize_job", noop_finalize)


def _stub_scrape_preamble(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stub `_build_scrape_cache` / clients / `_revalidate_final_url` and
    return a list that records every `_scrape_step` call (with `force_tier`)
    so tests can assert call sequences.
    """
    from src.jobs import orchestrator

    monkeypatch.setattr(orchestrator, "_build_scrape_cache", lambda s: MagicMock())
    monkeypatch.setattr(orchestrator, "_build_firecrawl_client", lambda s: MagicMock())
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
    )

    async def noop_revalidate(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(orchestrator, "_revalidate_final_url", noop_revalidate)

    scrape_calls: list[dict[str, Any]] = []

    async def recording_scrape_step(
        url: str,
        scrape_client: Any,
        interact_client: Any,
        scrape_cache: Any,
        *,
        force_tier: Any = None,
    ) -> Any:
        scrape_calls.append({"url": url, "force_tier": force_tier})
        return MagicMock(metadata=None)

    monkeypatch.setattr(orchestrator, "_scrape_step", recording_scrape_step)
    return scrape_calls


async def test_run_pipeline_first_pass_zero_utterances_escalates_to_interact_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First extract_utterances call raises ZeroUtterancesError; the pipeline
    escalates by re-running `_scrape_step(force_tier='interact')` and a fresh
    extract_utterances. Second call returns a non-empty payload → success.
    """
    from src.jobs import orchestrator
    from src.utterances.extractor import ZeroUtterancesError

    _stub_post_gemini_for_escalation(monkeypatch)
    scrape_calls = _stub_scrape_preamble(monkeypatch)

    extract_calls: list[Any] = []

    async def flaky_extract(*args: Any, **kwargs: Any) -> Any:
        extract_calls.append(args)
        if len(extract_calls) == 1:
            raise ZeroUtterancesError("first pass empty")
        return MagicMock()

    monkeypatch.setattr(orchestrator, "extract_utterances", flaky_extract)

    await orchestrator._run_pipeline(
        MagicMock(), uuid4(), uuid4(), "https://example.com", MagicMock()
    )

    assert len(extract_calls) == 2, "extractor must be retried exactly once"
    assert len(scrape_calls) == 2, "scrape_step must be re-invoked for Tier 2"
    # First call uses default ladder (no force).
    assert scrape_calls[0]["force_tier"] is None
    # Second call MUST force the Tier 2 path.
    assert scrape_calls[1]["force_tier"] == "interact"


async def test_run_pipeline_zero_utterances_twice_raises_terminal_extraction_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the second pass also raises ZeroUtterancesError, the pipeline
    raises TerminalError(EXTRACTION_FAILED) carrying the "0 utterances after
    /interact" detail. The orchestrator MUST NOT escalate a third time.
    """
    from src.jobs import orchestrator
    from src.utterances.extractor import ZeroUtterancesError

    _stub_post_gemini_for_escalation(monkeypatch)
    scrape_calls = _stub_scrape_preamble(monkeypatch)

    extract_calls: list[Any] = []

    async def always_empty(*args: Any, **kwargs: Any) -> Any:
        extract_calls.append(args)
        raise ZeroUtterancesError("still empty")

    monkeypatch.setattr(orchestrator, "extract_utterances", always_empty)

    with pytest.raises(TerminalError) as exc_info:
        await orchestrator._run_pipeline(
            MagicMock(), uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    assert exc_info.value.error_code is ErrorCode.EXTRACTION_FAILED
    assert "0 utterances" in exc_info.value.error_detail
    assert "interact" in exc_info.value.error_detail
    assert len(extract_calls) == 2, (
        "once-only guard: extractor must NOT be called a third time"
    )
    assert len(scrape_calls) == 2, (
        "once-only guard: scrape_step must NOT be re-run a third time"
    )


async def test_run_pipeline_first_pass_success_does_not_escalate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the first extract_utterances call succeeds, no escalation fires:
    exactly one scrape_step call (default `force_tier=None`) and exactly one
    extract_utterances call. This guards against the once-only path
    re-triggering on success.
    """
    from src.jobs import orchestrator

    _stub_post_gemini_for_escalation(monkeypatch)
    scrape_calls = _stub_scrape_preamble(monkeypatch)

    extract_calls: list[Any] = []

    async def good_extract(*args: Any, **kwargs: Any) -> Any:
        extract_calls.append(args)
        return MagicMock()

    monkeypatch.setattr(orchestrator, "extract_utterances", good_extract)

    await orchestrator._run_pipeline(
        MagicMock(), uuid4(), uuid4(), "https://example.com", MagicMock()
    )

    assert len(extract_calls) == 1
    assert len(scrape_calls) == 1
    assert scrape_calls[0]["force_tier"] is None


async def test_run_pipeline_zero_utterances_then_success_logs_escalation_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the once-only escalation fires, the second `_scrape_step` call
    is invoked with `force_tier='interact'` — the explicit signal that
    Tier 1 should be skipped because Gemini reported 0 utterances on the
    first pass. This is the operator-visible breadcrumb (combined with the
    Logfire span attribute set inside `_scrape_step`) that distinguishes
    "Tier 1 returned empty bundle" from "Tier 1 returned content but Gemini
    couldn't parse it".
    """
    from src.jobs import orchestrator
    from src.utterances.extractor import ZeroUtterancesError

    _stub_post_gemini_for_escalation(monkeypatch)
    scrape_calls = _stub_scrape_preamble(monkeypatch)

    extract_count = {"n": 0}

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        extract_count["n"] += 1
        if extract_count["n"] == 1:
            raise ZeroUtterancesError("first pass empty")
        return MagicMock()

    monkeypatch.setattr(orchestrator, "extract_utterances", flaky)

    await orchestrator._run_pipeline(
        MagicMock(), uuid4(), uuid4(), "https://example.com", MagicMock()
    )

    forced_calls = [c for c in scrape_calls if c["force_tier"] == "interact"]
    assert len(forced_calls) == 1


async def test_scrape_step_force_tier_interact_logs_escalation_reason_zero_utterances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Logfire span on the forced Tier 2 invocation must record
    `escalation_reason='zero_utterances'`, distinguishing it from the
    `firecrawl_blocked` / `interstitial` triggers Tier 1 already emits.
    Operators reading the trace should be able to tell at a glance whether
    a /interact call happened because Tier 1 refused, classified as
    interstitial, or because Gemini returned an empty payload.
    """
    from src.jobs import orchestrator

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/forced-interact"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient()  # never called
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        force_tier="interact",
    )

    assert span.attrs.get("escalation_reason") == "zero_utterances"
    # tier_attempted must reflect the bypass: only Tier 2 ran.
    assert span.attrs.get("tier_attempted") == ["interact"]
    assert span.attrs.get("tier_success") == "interact"


# ---------------------------------------------------------------------------
# TASK-1488.11 — `_run_pipeline` must thread the `_scrape_step` result into
# `extract_utterances` so a Tier 2 escalation actually reaches Gemini. Without
# the pass-through, the extractor's `_get_or_scrape` re-reads `tier="scrape"`
# from cache and silently overwrites a fresh Tier 2 bundle with the cached
# Tier 1 INTERSTITIAL — defeating `force_tier`.
# ---------------------------------------------------------------------------


async def test_run_pipeline_threads_scrape_step_result_into_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_scrape_and_extract` must pass the `_scrape_step` result to
    `extract_utterances` as the `scrape=` kwarg. Otherwise the extractor
    re-reads Tier 1 from cache and the Tier 2 escalation is dead code in
    production.
    """
    from src.jobs import orchestrator

    _stub_extract_arm_only(monkeypatch)

    sentinel_scrape = CachedScrape(
        markdown="TIER_2_BUNDLE",
        html="<html>tier 2</html>",
        raw_html=None,
        screenshot=None,
        links=None,
        metadata=ScrapeMetadata(
            title="Tier 2", source_url="https://example.com"
        ),
        warning=None,
        storage_key=None,
    )

    async def stub_scrape_step(*args: Any, **kwargs: Any) -> CachedScrape:
        return sentinel_scrape

    monkeypatch.setattr(orchestrator, "_scrape_step", stub_scrape_step)

    captured: dict[str, Any] = {}

    async def capturing_extract(*args: Any, **kwargs: Any):
        captured["args"] = args
        captured["kwargs"] = kwargs
        # Raise terminal so we don't have to mock the post-Gemini path.
        raise UtteranceExtractionError("stop here")

    monkeypatch.setattr(orchestrator, "extract_utterances", capturing_extract)

    pool = FakePool(MagicMock())
    with pytest.raises(orchestrator.TerminalError):
        await orchestrator._run_pipeline(
            pool, uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    assert captured["kwargs"].get("scrape") is sentinel_scrape
