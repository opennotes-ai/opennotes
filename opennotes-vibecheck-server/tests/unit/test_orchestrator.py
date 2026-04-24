"""Unit tests for orchestrator internal logic (TASK-1473.59).

The full pipeline integration is covered by test_worker.py (HTTP surface).
These tests focus on internal helpers that are easier to drive in isolation
without standing up Postgres or the FastAPI app.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

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
