"""Unit tests for orchestrator internal logic (TASK-1473.59).

The full pipeline integration is covered by test_worker.py (HTTP surface).
These tests focus on internal helpers that are easier to drive in isolation
without standing up Postgres or the FastAPI app.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import asyncpg
import pytest

from src.analyses.safety._schemas import SafetyLevel, SafetyRecommendation
from src.analyses.schemas import SectionSlug, SectionState
from src.jobs.orchestrator import TransientError, _run_section

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
# ---------------------------------------------------------------------------


class _StageRecorderConn:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def execute(self, *args):
        self.calls.append(args)
        return "UPDATE 1"


class _ExecuteFailingConn:
    async def execute(self, *args):
        raise RuntimeError("db down")


async def test_set_last_stage_writes_breadcrumb_with_attempt_cas() -> None:
    """_set_last_stage writes (last_stage, job_id, attempt_id) via CAS UPDATE."""
    from src.jobs import orchestrator

    conn = _StageRecorderConn()
    job_id = uuid4()
    task_attempt = uuid4()

    await orchestrator._set_last_stage(
        FakePool(conn), job_id, task_attempt, "persist_utterances"
    )

    assert len(conn.calls) == 1
    sql, captured_job_id, captured_stage, captured_attempt = conn.calls[0]
    assert "last_stage" in sql
    assert captured_job_id == job_id
    assert captured_stage == "persist_utterances"
    assert captured_attempt == task_attempt


async def test_set_last_stage_swallows_db_failure(caplog: pytest.LogCaptureFixture) -> None:
    """A DB failure inside the breadcrumb write must not tear down the pipeline."""
    from src.jobs import orchestrator

    caplog.set_level(logging.WARNING, logger="src.jobs.orchestrator")

    await orchestrator._set_last_stage(
        FakePool(_ExecuteFailingConn()),
        uuid4(),
        uuid4(),
        "persist_utterances",
    )

    assert any("set_last_stage" in r.message for r in caplog.records)


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


class _IncrementCounterConn:
    """Stand-in connection that emulates _INCREMENT_EXTRACT_TRANSIENT_SQL.

    Tracks every fetchval invocation and bumps an internal counter by 1
    each time, returning the new value (matching RETURNING semantics).
    Tests set the starting value via `seed`.
    """

    def __init__(self, *, seed: int = 0) -> None:
        self.value = seed
        self.calls: list[tuple[Any, ...]] = []

    async def fetchval(self, sql: str, *args: Any) -> int:
        self.calls.append((sql, *args))
        self.value += 1
        return self.value


async def test_run_pipeline_translates_transient_extraction_error_to_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First TransientExtractionError increments the in-row counter to 1
    (below EXTRACT_TRANSIENT_MAX_ATTEMPTS=2) and surfaces as TransientError
    so run_job's outer arm resets the row to pending and returns 503.
    """
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

    counter = _IncrementCounterConn(seed=0)
    pool = FakePool(counter)
    job_id = uuid4()
    task_attempt = uuid4()

    with pytest.raises(orchestrator.TransientError) as info:
        await orchestrator._run_pipeline(
            pool, job_id, task_attempt, "https://example.com", MagicMock()
        )

    # Counter went from 0 -> 1 (single increment).
    assert counter.value == 1
    assert len(counter.calls) == 1
    # The TransientError message carries the new attempt count + provider
    # info so operators can correlate retries.
    assert "attempt 1" in str(info.value)
    assert "vertex" in str(info.value)
    assert "504" in str(info.value)


async def test_run_pipeline_backstop_escalates_to_terminal_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the in-row counter is already at MAX-1, the next
    TransientExtractionError pushes it to MAX and escalates to
    TerminalError(UPSTREAM_ERROR). Cloud Tasks would otherwise silently
    exhaust at max_attempts=3 and leave the row stuck pending.
    """
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator
    from src.utterances.errors import TransientExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_transient(*args, **kwargs):
        raise TransientExtractionError(
            provider="vertex",
            status_code=429,
            status="RESOURCE_EXHAUSTED",
            fallback_message="Vertex 429",
        )

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_transient)

    # Counter pre-loaded to (MAX - 1); next increment hits MAX.
    counter = _IncrementCounterConn(
        seed=orchestrator.EXTRACT_TRANSIENT_MAX_ATTEMPTS - 1
    )
    pool = FakePool(counter)
    job_id = uuid4()
    task_attempt = uuid4()

    with pytest.raises(orchestrator.TerminalError) as info:
        await orchestrator._run_pipeline(
            pool, job_id, task_attempt, "https://example.com", MagicMock()
        )

    assert info.value.error_code == ErrorCode.UPSTREAM_ERROR
    # Status code from the original TransientExtractionError is preserved
    # in the terminal message so operators can distinguish 504-exhaustion
    # from 429-exhaustion (AC#3 for TASK-1474.23.03.04).
    assert "429" in info.value.error_detail
    assert "vertex" in info.value.error_detail
    assert (
        f"after {orchestrator.EXTRACT_TRANSIENT_MAX_ATTEMPTS} transient"
        in info.value.error_detail
    )
    # Counter was incremented exactly once (not twice).
    assert counter.value == orchestrator.EXTRACT_TRANSIENT_MAX_ATTEMPTS


async def test_run_pipeline_treats_utterance_extraction_error_as_terminal_extraction_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse / no-utterances / output-validation failures classify as
    TerminalError(EXTRACTION_FAILED), NOT UPSTREAM_ERROR, and do NOT
    increment the transient backstop counter (it's a content-shape
    problem, not an upstream flake).
    """
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator
    from src.utterances.errors import UtteranceExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_terminal(*args, **kwargs):
        raise UtteranceExtractionError("agent returned empty utterances")

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_terminal)

    counter = _IncrementCounterConn(seed=0)
    pool = FakePool(counter)
    job_id = uuid4()
    task_attempt = uuid4()

    with pytest.raises(orchestrator.TerminalError) as info:
        await orchestrator._run_pipeline(
            pool, job_id, task_attempt, "https://example.com", MagicMock()
        )

    assert info.value.error_code == ErrorCode.EXTRACTION_FAILED
    assert "agent returned empty utterances" in info.value.error_detail
    # Counter was NOT touched — this is a parse failure, not an upstream
    # flake.
    assert counter.value == 0
    assert counter.calls == []


async def test_run_pipeline_unexpected_exception_falls_through_to_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive catch: anything not classified by the typed arms is
    still terminal (EXTRACTION_FAILED) so the worker can never loop
    forever on an unknown bug. Counter is NOT incremented.
    """
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator

    _stub_extract_arm_only(monkeypatch)

    async def boom(*args, **kwargs):
        raise RuntimeError("kaboom unknown bug")

    monkeypatch.setattr(orchestrator, "extract_utterances", boom)

    counter = _IncrementCounterConn(seed=0)
    pool = FakePool(counter)
    job_id = uuid4()
    task_attempt = uuid4()

    with pytest.raises(orchestrator.TerminalError) as info:
        await orchestrator._run_pipeline(
            pool, job_id, task_attempt, "https://example.com", MagicMock()
        )

    assert info.value.error_code == ErrorCode.EXTRACTION_FAILED
    assert "kaboom unknown bug" in info.value.error_detail
    assert counter.value == 0
    assert counter.calls == []


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
    """If the increment SQL itself fails (DB down, connection blip), the
    helper returns None and the orchestrator classifies as TransientError
    rather than terminal. Best-effort: prefer redelivery > silent loss.
    AC#4 for TASK-1474.23.03.04.
    """
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
            raise RuntimeError("connection refused")

    pool = FakePool(_DbDownConn())
    caplog.set_level(logging.WARNING, logger="src.jobs.orchestrator")

    with pytest.raises(orchestrator.TransientError):
        await orchestrator._run_pipeline(
            pool, uuid4(), uuid4(), "https://example.com", MagicMock()
        )

    # Warning surfaced so operators see the failure (AC#4 visibility).
    assert any(
        "extract_transient_attempts increment failed" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]
