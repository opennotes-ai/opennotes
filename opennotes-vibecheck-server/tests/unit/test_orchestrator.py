"""Unit tests for orchestrator internal logic (TASK-1473.59).

The full pipeline integration is covered by test_worker.py (HTTP surface).
These tests focus on internal helpers that are easier to drive in isolation
without standing up Postgres or the FastAPI app.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import asyncpg
import pytest

from src.analyses.safety._schemas import SafetyLevel, SafetyRecommendation
from src.analyses.schemas import ErrorCode, SectionSlug, SectionState
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.coral import (
    CoralComments,
    CoralFetchError,
    CoralSignal,
    CoralUnsupportedError,
)
from src.firecrawl_client import (
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
    ScrapeMetadata,
    ScrapeResult,
)
from src.jobs.orchestrator import (
    TerminalError,
    TransientError,
    run_section_retry,
    _run_section,
    _run_tier2,
    _tier2_actions_for,
)
from src.utterances.errors import TransientExtractionError, UtteranceExtractionError


def _require_markdown(scrape: ScrapeResult) -> str:
    assert scrape.markdown is not None
    return scrape.markdown

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


async def test_run_all_sections_persists_empty_dedup_dependent_slots_when_dedup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B-C2 regression: dedup failure must not strand the three claim
    enrichment slots or trends/oppositions in unwritten state.

    `maybe_finalize_job` blocks on `len(sections) < len(SectionSlug)`, so
    when dedup fails the orchestrator must write terminal slots for
    FACTS_CLAIMS_EVIDENCE / FACTS_CLAIMS_PREMISES / FACTS_CLAIMS_KNOWN_MISINFO
    / OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS so finalize can proceed.
    """
    from src.jobs import orchestrator

    run_section_calls: list[SectionSlug] = []

    async def fake_run_section(
        pool: object,
        job_id: object,
        task_attempt: object,
        slug: SectionSlug,
        payload: object,
        settings: object,
        *,
        test_fail_slug: str | None = None,
    ) -> SectionState:
        del pool, job_id, task_attempt, payload, settings, test_fail_slug
        run_section_calls.append(slug)
        if slug == SectionSlug.FACTS_CLAIMS_DEDUP:
            return SectionState.FAILED
        return SectionState.DONE

    written: list[tuple[SectionSlug, SectionState, dict[str, Any] | None]] = []

    async def fake_write_slot(pool, job_id, task_attempt, slug, slot):
        del pool, job_id, task_attempt
        written.append((slug, slot.state, slot.data))
        return 1

    monkeypatch.setattr(orchestrator, "_run_section", fake_run_section)
    monkeypatch.setattr(orchestrator, "write_slot", fake_write_slot)

    await orchestrator._run_all_sections(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=object(),
        settings=MagicMock(),
    )

    dependent_slugs = {
        SectionSlug.FACTS_CLAIMS_EVIDENCE,
        SectionSlug.FACTS_CLAIMS_PREMISES,
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
    }
    written_slugs = {slug for slug, _state, _data in written}
    assert dependent_slugs.issubset(written_slugs)
    for slug, state, data in written:
        if slug in dependent_slugs:
            assert state == SectionState.DONE
            assert isinstance(data, dict)
    assert all(
        slug not in run_section_calls for slug in dependent_slugs
    ), "dedup-dependent slots must skip _run_section when dedup fails"


@pytest.mark.asyncio
async def test_run_all_sections_writes_trends_oppositions_after_dedup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FACTS_CLAIMS_DEDUP must complete before trends/oppositions runs."""
    from src.jobs import orchestrator
    from src.analyses.opinions import trends_oppositions_slot

    dedup_done = asyncio.Event()
    run_order: list[str] = []
    trend_payloads: list[Any] = []
    fact_payloads: list[Any] = []

    async def fake_run_section(
        _pool: Any,
        _job_id: UUID,
        _task_attempt: UUID,
        slug: SectionSlug,
        _payload: Any,
        _settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> None:
        if slug == SectionSlug.FACTS_CLAIMS_DEDUP:
            # Simulate a non-trivial slot write path that must finish first.
            run_order.append(slug.value)
            fact_payloads.append(_payload)
            dedup_done.set()
        elif slug == SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS:
            assert dedup_done.is_set()
            trend_payloads.append(_payload)
            run_order.append(slug.value)
        else:
            fact_payloads.append(_payload)
            run_order.append(slug.value)
        return SectionState.DONE

    monkeypatch.setattr(orchestrator, "_run_section", fake_run_section)

    await orchestrator._run_all_sections(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=object(),
        settings=MagicMock(),
    )

    assert (
        run_order[-1]
        == SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS.value
    )
    assert trend_payloads and trend_payloads[-1] is trends_oppositions_slot.FIRST_RUN_DEPENDENCY_PAYLOAD
    assert all(item is not None for item in fact_payloads)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sections_payload",
    [
        {},
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "failed",
                "attempt_id": str(uuid4()),
                "data": {"claims_report": {}},
            }
        },
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "pending",
                "attempt_id": str(uuid4()),
                "data": {"claims_report": {}},
            }
        },
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "running",
                "attempt_id": str(uuid4()),
                "data": {"claims_report": {}},
            }
        },
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "done",
                "attempt_id": str(uuid4()),
                "data": {"claims_report": "malformed"},
            }
        },
    ],
)
async def test_run_all_sections_trends_with_unavailable_dedup_does_not_fail(
    monkeypatch: pytest.MonkeyPatch, sections_payload: dict[str, Any]
) -> None:
    """Transient and unavailable first-run dependent states should not fail trends slot."""
    from src.jobs import orchestrator
    from src.analyses.opinions import trends_oppositions_slot

    class _Conn:
        def __init__(self, row: Any) -> None:
            self.row = row

        async def fetchval(self, *_args: object) -> Any:
            return self.row

    class _Pool:
        def __init__(self, row: Any) -> None:
            self.conn = _Conn(row)

        def acquire(self) -> FakeAcquire:
            return FakeAcquire(self.conn)

    async def no_op_handler(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    mark_slot_failed_calls: list[tuple] = []
    write_slot_calls: list[tuple] = []

    async def fake_write_slot(*args: Any, **kwargs: Any) -> int:
        write_slot_calls.append((args, kwargs))
        return 1

    async def never_failed(*args: Any, **kwargs: Any) -> int:
        mark_slot_failed_calls.append((args, kwargs))
        return 1

    original_handlers = dict(orchestrator._SECTION_HANDLERS)
    handlers = dict(original_handlers)
    for slug in original_handlers:
        handlers[slug] = no_op_handler
    handlers[SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS] = (
        trends_oppositions_slot.run_trends_oppositions
    )
    monkeypatch.setattr(orchestrator, "_SECTION_HANDLERS", handlers)
    monkeypatch.setattr(orchestrator, "write_slot", fake_write_slot)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", never_failed)

    fake_extract = AsyncMock()
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake_extract)

    await orchestrator._run_all_sections(
        pool=_Pool(sections_payload),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=object(),
        settings=MagicMock(),
    )

    assert write_slot_calls
    assert mark_slot_failed_calls == []
    fake_extract.assert_not_called()


@pytest.mark.asyncio
async def test_run_section_retry_trends_dependencies_not_ready_reenqueues_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.opinions import trends_oppositions_slot
    from src.jobs import orchestrator

    task_attempt = uuid4()
    slot_attempt = str(task_attempt)

    async def handler(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise trends_oppositions_slot.TrendsDependenciesNotReadyError("pending deps")

    async def _load(*args: Any, **kwargs: Any) -> tuple[UUID, dict[str, Any]]:
        return task_attempt, {
            "state": "running",
            "attempt_id": slot_attempt,
            "data": None,
        }

    mark_slot_failed_calls: list[tuple] = []
    mark_slot_done_calls: list[tuple] = []

    async def never_done(*args: Any, **kwargs: Any) -> int:
        mark_slot_done_calls.append((args, kwargs))
        return 1

    async def never_failed(*args: Any, **kwargs: Any) -> int:
        mark_slot_failed_calls.append((args, kwargs))
        return 1

    enqueue_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def fake_enqueue_section_retry(*args: Any, **kwargs: Any) -> None:
        enqueue_calls.append((args, kwargs))

    monkeypatch.setattr(orchestrator, "_load_job_attempt_and_slot", _load)
    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS,
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        handler,
    )
    monkeypatch.setattr(orchestrator, "mark_slot_done", never_done)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", never_failed)
    monkeypatch.setattr(orchestrator, "enqueue_section_retry", fake_enqueue_section_retry)

    job_id = uuid4()
    result = await run_section_retry(
        pool=MagicMock(),
        job_id=job_id,
        slug=SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        expected_slot_attempt_id=task_attempt,
        settings=MagicMock(),
    )

    assert result.status_code == 200
    assert len(enqueue_calls) == 1
    enqueue_args, enqueue_kwargs = enqueue_calls[0]
    assert enqueue_args[0] == job_id
    assert enqueue_args[1] == SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS
    assert enqueue_args[2] == task_attempt
    assert enqueue_args[3] is not None
    assert enqueue_kwargs == {
        "task_name": None,
        "use_deterministic_task_name": False,
        "schedule_delay_seconds": orchestrator._SECTION_RETRY_DEPENDENCY_BACKOFF_SECONDS,
    }
    assert mark_slot_failed_calls == []
    assert mark_slot_done_calls == []


@pytest.mark.asyncio
async def test_run_section_retry_trends_dependencies_not_ready_marked_reenqueue_failure_as_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.opinions import trends_oppositions_slot
    from src.jobs import orchestrator

    task_attempt = uuid4()
    slot_attempt = str(task_attempt)

    async def handler(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise trends_oppositions_slot.TrendsDependenciesNotReadyError("pending deps")

    async def _load(*args: Any, **kwargs: Any) -> tuple[UUID, dict[str, Any]]:
        return task_attempt, {
            "state": "running",
            "attempt_id": slot_attempt,
            "data": None,
        }

    mark_slot_failed_calls: list[tuple] = []
    mark_slot_done_calls: list[tuple] = []

    async def never_done(*args: Any, **kwargs: Any) -> int:
        mark_slot_done_calls.append((args, kwargs))
        return 1

    async def never_failed(*args: Any, **kwargs: Any) -> int:
        mark_slot_failed_calls.append((args, kwargs))
        return 1

    async def fake_enqueue_section_retry(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(orchestrator, "_load_job_attempt_and_slot", _load)
    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS,
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        handler,
    )
    monkeypatch.setattr(orchestrator, "mark_slot_done", never_done)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", never_failed)
    monkeypatch.setattr(orchestrator, "enqueue_section_retry", fake_enqueue_section_retry)

    result = await run_section_retry(
        pool=MagicMock(),
        job_id=uuid4(),
        slug=SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        expected_slot_attempt_id=task_attempt,
        settings=MagicMock(),
    )

    assert result.status_code == 503
    assert mark_slot_failed_calls == []
    assert mark_slot_done_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sections_payload",
    [
        {},
        {SectionSlug.FACTS_CLAIMS_DEDUP.value: {"state": "failed", "attempt_id": str(uuid4()), "data": {"claims_report": {"deduped_claims": [], "total_claims": 0, "total_unique": 0}}}},
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "done",
                "attempt_id": str(uuid4()),
                "data": {"claims_report": "malformed"},
            }
        },
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "done",
                "attempt_id": str(uuid4()),
                "data": {
                    "claims_report": {
                        "deduped_claims": [],
                        "total_claims": 0,
                        "total_unique": 0,
                    }
                },
            }
        },
    ],
)
async def test_run_section_retry_trends_with_permanent_dependency_states_settles_empty(
    monkeypatch: pytest.MonkeyPatch, sections_payload: dict[str, Any]
) -> None:
    from src.analyses.opinions import trends_oppositions_slot
    from src.jobs import orchestrator

    task_attempt = uuid4()
    slot_attempt = str(task_attempt)

    class _Conn:
        def __init__(self, row: Any) -> None:
            self.row = row

        async def fetchval(self, *_args: object) -> Any:
            return self.row

    class _Pool:
        def __init__(self, row: Any) -> None:
            self.conn = _Conn(row)

        def acquire(self) -> FakeAcquire:
            return FakeAcquire(self.conn)

    async def _load(*args: Any, **kwargs: Any) -> tuple[UUID, dict[str, Any]]:
        return task_attempt, {
            "state": "running",
            "attempt_id": slot_attempt,
            "data": None,
        }

    mark_slot_failed_calls: list[tuple] = []
    mark_slot_done_calls: list[tuple] = []

    async def fake_done(*args: Any, **kwargs: Any) -> int:
        mark_slot_done_calls.append((args, kwargs))
        return 1

    async def fake_failed(*args: Any, **kwargs: Any) -> int:
        mark_slot_failed_calls.append((args, kwargs))
        return 1

    monkeypatch.setattr(orchestrator, "_load_job_attempt_and_slot", _load)
    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS,
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        trends_oppositions_slot.run_trends_oppositions,
    )
    monkeypatch.setattr(orchestrator, "mark_slot_done", fake_done)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", fake_failed)
    monkeypatch.setattr(orchestrator, "_set_last_stage", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_safety_recommendation_step", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_headline_summary_step", AsyncMock())
    monkeypatch.setattr(orchestrator, "maybe_finalize_job", AsyncMock(return_value=False))

    result = await run_section_retry(
        pool=_Pool(sections_payload),
        job_id=uuid4(),
        slug=SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        expected_slot_attempt_id=task_attempt,
        settings=MagicMock(),
    )

    assert result.status_code == 200
    assert mark_slot_failed_calls == []
    assert mark_slot_done_calls


@pytest.mark.asyncio
async def test_run_section_retry_dedup_refreshes_all_dependent_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    task_attempt = uuid4()
    slot_attempt = uuid4()
    rerun_slugs: list[SectionSlug] = []

    async def _load(*args: Any, **kwargs: Any) -> tuple[UUID, dict[str, Any]]:
        return task_attempt, {
            "state": "running",
            "attempt_id": str(slot_attempt),
            "data": None,
        }

    async def dedup_handler(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"claims_report": {"deduped_claims": [], "total_claims": 0, "total_unique": 0}}

    async def fake_mark_slot_done(*args: Any, **kwargs: Any) -> int:
        return 1

    async def fake_run_section(
        _pool: Any,
        _job_id: UUID,
        _task_attempt: UUID,
        slug: SectionSlug,
        _payload: Any,
        _settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> SectionState:
        del test_fail_slug
        rerun_slugs.append(slug)
        return SectionState.DONE

    monkeypatch.setattr(orchestrator, "_load_job_attempt_and_slot", _load)
    monkeypatch.setitem(
        orchestrator._SECTION_HANDLERS,
        SectionSlug.FACTS_CLAIMS_DEDUP,
        dedup_handler,
    )
    monkeypatch.setattr(orchestrator, "mark_slot_done", fake_mark_slot_done)
    monkeypatch.setattr(orchestrator, "_run_section", fake_run_section)
    monkeypatch.setattr(orchestrator, "_set_last_stage", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_safety_recommendation_step", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_headline_summary_step", AsyncMock())
    monkeypatch.setattr(orchestrator, "maybe_finalize_job", AsyncMock(return_value=False))

    result = await run_section_retry(
        pool=MagicMock(),
        job_id=uuid4(),
        slug=SectionSlug.FACTS_CLAIMS_DEDUP,
        expected_slot_attempt_id=slot_attempt,
        settings=MagicMock(),
    )

    assert result.status_code == 200
    assert rerun_slugs == [
        SectionSlug.FACTS_CLAIMS_EVIDENCE,
        SectionSlug.FACTS_CLAIMS_PREMISES,
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
    ]



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
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
    )

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
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
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


async def test_run_pipeline_pdf_transient_extraction_error_uses_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    monkeypatch.setattr(orchestrator, "_build_scrape_cache", lambda s: MagicMock())
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda s: MagicMock()
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
    )

    async def raise_transient(*args: object, **kwargs: object) -> None:
        raise TransientExtractionError(
            provider="firecrawl",
            status_code=503,
            status="HTTP_503",
            fallback_message="Firecrawl 503",
        )

    monkeypatch.setattr(orchestrator, "pdf_extract_step", raise_transient)

    class _Conn:
        async def fetchval(self, sql: str, *args: Any) -> int:
            return 1

    with pytest.raises(orchestrator.TransientError):
        await orchestrator._run_pipeline(
            FakePool(_Conn()),
            uuid4(),
            uuid4(),
            "22222222-2222-4222-8222-222222222222",
            MagicMock(),
            source_type="pdf",
        )


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
        self.store: dict[tuple[Any, ...], CachedScrape] = {}
        self.gets: list[tuple[str, str, str | None, str | None]] = []
        self.puts: list[tuple[str, str]] = []
        self.evicts: list[tuple[str, str | None]] = []

    async def get(
        self,
        url: str,
        *,
        tier: str = "scrape",
        job_id: UUID | None = None,
        attempt_id: UUID | None = None,
    ) -> CachedScrape | None:
        job_key = str(job_id) if job_id is not None else None
        attempt_key = str(attempt_id) if attempt_id is not None else None
        self.gets.append((url, tier, job_key, attempt_key))

        if job_id is not None and attempt_id is not None:
            by_job = self.store.get((url, tier, job_key, attempt_key))
            if by_job is not None:
                return by_job
        return self.store.get((url, tier))

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        *,
        tier: str = "scrape",
        job_id: UUID | None = None,
        attempt_id: UUID | None = None,
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
        if job_id is not None and attempt_id is not None:
            self.store[(url, tier, str(job_id), str(attempt_id))] = cached
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


def _scrape_results(*results: Any) -> Callable[[], Any]:
    iterator = iter(results)

    def _next() -> Any:
        return cast(Any, next(iterator))

    return _next


def _ok_scrape_result(
    *,
    body: str = "Substantive article body. " * 20,
    html: str | None = None,
    actions: dict[str, Any] | None = None,
) -> ScrapeResult:
    if html is None:
        html = f"<html><body><article><h1>Real Article</h1><p>{body}</p></article></body></html>"
    return ScrapeResult(
        markdown=f"# Real Article\n\n{body}",
        html=html,
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com/post"),
        actions=actions,
    )


def _comment_scrape_result(
    *,
    body: str = "## Comments\n- Great discussion in the comments.",
) -> ScrapeResult:
    return ScrapeResult(
        markdown=body,
        html="<html><body><section>Coral comments iframe</section></body></html>",
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com/coral-comments"),
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


_CORAL_HTML_FIXTURE = """\
<script src="https://assets.coralproject.net/assets/js/embed.js"></script>
<iframe class="coral-talk-stream" src="https://coral.example.com/embed/stream?storyURL=https%3A%2F%2Fexample.com%2Fpost"></iframe>"""

_PARTIAL_CORAL_HTML_FIXTURE = """
<div id="coral_talk_stream">
  <button class="comment-button" data-gtm-class="open-community">2 Kommentare</button>
</div>"""

_LA_TIMES_PS_COMMENTS_FIXTURE = """
<ps-comments
  id="coral_talk_stream"
  data-embed-url="https://latimes.coral.coralproject.net/assets/js/embed.js"
  data-env-url="https://latimes.coral.coralproject.net"
  data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
>Show Comments</ps-comments>"""

_CORAL_DETECTION_HTML_FIXTURE = """
<html>
  <head>
    <link rel="canonical" href="https://www.tagesspiegel.de/2026/04/29/example"/>
    <script src="https://coral.tagesspiegel.de/static/embed.js"></script>
    <div data-hydrate-props="{&amp;escapedquot;talkAssetId&amp;escapedquot;:&amp;escapedquot;15538543&amp;escapedquot;,&amp;escapedquot;communityHostname&amp;escapedquot;:&amp;escapedquot;coral.tagesspiegel.de&amp;escapedquot;,&amp;escapedquot;canonicalUrl&amp;escapedquot;:&amp;escapedquot;https://www.tagesspiegel.de/2026/04/29/example&amp;escapedquot;}" />
    <script>
      window.__INITIAL_STATE__ = {"communityHostname":"coral.tagesspiegel.de"};
    </script>
  </head>
  <body>
    <article>
      <h1>Tagesspiegel Article</h1>
      <p>Visible article body</p>
    </article>
  </body>
</html>"""


def _eval_execute_javascript(
    script: str,
    *,
    match_selectors: list[str] | tuple[str, ...],
    html_fixture: str | None = None,
    shadow_html: str | None = None,
    shadow_states: list[dict[str, Any]] | None = None,
    shadow_host_selector: str = "#coral-shadow-container",
    light_dom_states: list[dict[str, Any]] | None = None,
    light_dom_selector: str = "#comments",
    shadow_closed: bool = False,
) -> tuple[str, str | None, str | None]:
    """Run a generated executeJavascript payload against a stubbed document."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("node.js is required to execute generated executeJavascript payloads")

    driver = r"""
const payload = JSON.parse(process.argv[1]);
const matchingSelectors = new Set(payload.matchingSelectors);
const htmlFixture = payload.htmlFixture || "";
const shadowStates = Array.isArray(payload.shadowStates)
    ? payload.shadowStates
    : [];
const lightDomStates = Array.isArray(payload.lightDomStates)
    ? payload.lightDomStates
    : [];
const lightDomSelector = payload.lightDomSelector || "#comments";
const shadowHostSelector = payload.shadowHostSelector || "#coral-shadow-container";
const hasShadowHtml = payload.shadowHtml !== null && payload.shadowHtml !== undefined;
const shadowHtml = hasShadowHtml ? payload.shadowHtml : "";
const shadowClosed = Boolean(payload.shadowClosed);
const hasShadowSource = hasShadowHtml || shadowStates.length > 0;
let clickedSelector = null;
let markerHtml = null;
let shadowHostCallCount = 0;
let lightDomHostCallCount = 0;

function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
}

function stripTags(value) {
    return String(value || "").replace(/<[^>]*>/g, " ").trim();
}

function normalizeShadowState(state) {
    if (!state) {
        return {text: "", comments: []};
    }
    if (typeof state === "string") {
        return {text: stripTags(state), comments: []};
    }
    if (typeof state !== "object") {
        return {text: "", comments: []};
    }
    const stateText = normalizeText(typeof state.text === "string" ? state.text : "");
    const comments = Array.isArray(state.comments) ? state.comments : [];
    const resolvedComments = comments
        .map((comment) => {
            if (!comment || typeof comment !== "object") {
                return null;
            }
            const author = normalizeText(comment.author);
            const text = normalizeText(comment.text);
            if (!author || !text) {
                return null;
            }
            return {
                author,
                text,
                tagName: normalizeText(comment.tagName || "article"),
                className: normalizeText(comment.className || ""),
                ariaLabel: normalizeText(comment.ariaLabel || ""),
                dataTestId: normalizeText(comment.dataTestId || ""),
            };
        })
        .filter(Boolean);
    return {
        text: stateText,
        comments: resolvedComments,
    };
}

function resolveShadowState() {
    const fallbackStates = hasShadowHtml ? [{text: stripTags(shadowHtml)}] : [{text: ""}];
    const states = shadowStates.length > 0 ? shadowStates : fallbackStates;
    const state = normalizeShadowState(states[Math.min(shadowHostCallCount, states.length - 1)]);
    shadowHostCallCount += 1;
    return state;
}

function resolveLightDomState() {
    const state = normalizeShadowState(lightDomStates[Math.min(lightDomHostCallCount, lightDomStates.length - 1)]);
    lightDomHostCallCount += 1;
    return state;
}

function psCommentsBlock() {
    const match = htmlFixture.match(/<ps-comments\b([^>]*)>([\s\S]*?)<\/ps-comments>/i);
    if (!match) {
        return null;
    }
    if (!/\bid\s*=\s*["']coral_talk_stream["']/i.test(match[1])) {
        return null;
    }
    return { attrs: match[1], body: match[2] };
}

function selectorMatchesFixture(selector) {
    const block = psCommentsBlock();
    if (!block) {
        return false;
    }

    if (selector === "ps-comments#coral_talk_stream") {
        return true;
    }
    if (selector === "ps-comments#coral_talk_stream button") {
        return /<button\b/i.test(block.body);
    }
    return false;
}

function makeElement(tagName, init = {}) {
    const element = {
        tagName: String(tagName || "div"),
        attributes: {},
        children: [],
        textContent: init.textContent || "",
        innerHTML: init.innerHTML || "",
        className: init.className || "",
        setAttribute(name, value) {
            this.attributes[name] = String(value);
            if (name === "class") {
                this.className = String(value);
            }
            if (name === "aria-label") {
                this.ariaLabel = String(value);
            }
            if (name === "data-testid") {
                this.dataTestId = String(value);
            }
        },
        getAttribute(name) {
            return this.attributes[name];
        },
        appendChild(child) {
            this.children.push(child);
            if (child.textContent) {
                const text = this.textContent ? `${this.textContent} ${child.textContent}` : child.textContent;
                this.textContent = normalizeText(text);
            }
            if (child.innerHTML) {
                this.innerHTML = normalizeText(`${this.innerHTML} ${child.innerHTML}`);
            }
            if (this.attributes["data-coral-comments"] === "true") {
                markerHtml = this.innerHTML || this.textContent;
            }
            return child;
        },
        remove() {
            markerHtml = null;
        },
    };
    return element;
}

function makeCommentNode(state) {
    const node = makeElement(state.tagName || "article", {className: state.className || ""});
    if (state.dataTestId) {
        node.setAttribute("data-testid", state.dataTestId);
    }
    if (state.ariaLabel) {
        node.setAttribute("aria-label", state.ariaLabel);
    }
    const headerNode = makeElement("header", {textContent: state.author});
    const bodyNode = makeElement("p", {textContent: state.text});
    const authorNode = makeElement("span", {
        textContent: state.author,
        className: "comment-author",
    });
    node.appendChild(headerNode);
    node.appendChild(bodyNode);
    node.appendChild(authorNode);
    node.querySelector = (selector) => {
        const normalized = String(selector || "");
        if (normalized === "p") {
            return bodyNode;
        }
        if (
            normalized.includes("author")
            || normalized.includes("username")
            || normalized.includes("header")
            || normalized.includes("data-testid*='author'")
            || normalized.includes("class*='author'")
            || normalized.includes("class*='username'")
        ) {
            return authorNode;
        }
        return null;
    };
    node.matchesSelector = (selector) => {
        const normalized = String(selector || "");
        if (normalized.includes("article")) {
            return true;
        }
        if (normalized.includes("Comment_root")) {
            return node.className.includes("Comment_root");
        }
        if (normalized.includes("comment-content")) {
            return node.className.includes("comment-content");
        }
        if (normalized.includes("commentContent")) {
            return node.className.includes("commentContent");
        }
        if (normalized.includes("data-testid='comment'")) {
            return node.dataTestId === "comment";
        }
        if (normalized.includes("aria-label^='Comment from '")) {
            return node.ariaLabel.startsWith("Comment from ");
        }
        if (normalized.includes("aria-label^='Reply from '")) {
            return node.ariaLabel.startsWith("Reply from ");
        }
        return false;
    };
    node.querySelectorAll = (selector) => {
        const normalized = String(selector || "");
        if (normalized === "header" || normalized.includes("author") || normalized.includes("username")) {
            return [authorNode];
        }
        if (normalized === "p") {
            return [bodyNode];
        }
        return [];
    };
    return node;
}

function makeShadowRoot(state) {
    const normalized = normalizeShadowState(state);
    const comments = normalized.comments.map((comment) => makeCommentNode(comment));
    const rootText = normalizeText(
        [normalized.text, ...comments.map((node) => `${node.textContent}`)].join(" ")
    );
    return {
        innerHTML: normalized.text,
        textContent: rootText,
        querySelectorAll(selector) {
            const normalized = String(selector || "");
            if (normalized.includes("button") || normalized.includes("role='button'")) {
                return [];
            }
            if (comments.length === 0) {
                return [];
            }
            return comments.filter((comment) => comment.matchesSelector(selector));
        },
    };
}

const article = makeElement("article");
const body = makeElement("body");
body.appendChild = (child) => {
    if (child.attributes?.["data-coral-comments"] === "true") {
        markerHtml = child.innerHTML || child.textContent;
    }
    return child;
};
article.appendChild = body.appendChild;

global.document = {
    querySelector(selector) {
        if (selector === lightDomSelector && lightDomStates.length > 0) {
            const state = resolveLightDomState();
            const root = makeShadowRoot(state);
            root.dispatchEvent = () => {};
            return root;
        }
        if (selector === "article") {
            return article;
        }
        if (selector === "[data-coral-comments]") {
            return markerHtml === null ? null : { remove() { markerHtml = null; } };
        }
        if (!matchingSelectors.has(selector) && !selectorMatchesFixture(selector)) {
            return null;
        }

        return {
            click() {
                clickedSelector = selector;
            },
        };
    },
    createElement: makeElement,
    querySelectorAll(selector) {
        if (selector === shadowHostSelector && (hasShadowSource || shadowClosed)) {
            return [{
                id: shadowHostSelector.replace(/^#/, ""),
                shadowRoot: shadowClosed ? null : makeShadowRoot(resolveShadowState()),
                dispatchEvent() {},
            }];
        }
        if (selector === "button,[role='button']") {
            return [];
        }
        return [];
    },
    body,
};

global.setTimeout = (callback) => {
    callback();
    return 0;
};

(async () => {
const result = await eval(payload.script);
const output = {
    result: typeof result === "string" ? result : String(result),
    clickedSelector,
    markerHtml,
};
console.log(JSON.stringify(output));
})();
"""

    completed = subprocess.run(
        [
            node,
            "-e",
            driver,
            json.dumps(
                {
                    "script": script,
                    "matchingSelectors": list(match_selectors),
                    "htmlFixture": html_fixture,
                    "shadowHtml": shadow_html,
                    "shadowStates": shadow_states,
                    "shadowHostSelector": shadow_host_selector,
                    "lightDomStates": light_dom_states,
                    "lightDomSelector": light_dom_selector,
                    "shadowClosed": shadow_closed,
                }
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    output = json.loads(completed.stdout.strip())
    return output["result"], output["clickedSelector"], output["markerHtml"]


def _sample_coral_signal() -> CoralSignal:
    return CoralSignal(
        iframe_src=(
            "https://talk.example.com/embed/stream/?storyURL="
            "https://example.com/story"
        ),
        graphql_origin="https://talk.example.com",
        story_url="https://example.com/story",
    )


def _assert_generated_js_contains_selector(script: str, selector: str) -> None:
    assert json.dumps(selector) in script


def test_tier2_actions_for_default_waits_only() -> None:
    """Without a Coral signal, Tier 2 keeps the legacy single 3s wait."""

    assert _tier2_actions_for(None) == [{"type": "wait", "milliseconds": 3000}]


def test_tier2_actions_for_coral_signal_expands_comment_stream() -> None:
    """Coral detection switches Tier 2 actions to stream-expansion steps."""

    actions = _tier2_actions_for(_sample_coral_signal())

    assert actions[0] == {"type": "wait", "milliseconds": 2000}
    assert actions[1] == {"type": "scroll", "direction": "down"}
    assert actions[2]["type"] == "executeJavascript"
    js = actions[2]["script"]
    _assert_generated_js_contains_selector(
        js, 'button[data-testid="comments-show-comments-button"]'
    )
    _assert_generated_js_contains_selector(js, 'button[data-testid="comments-button"]')
    _assert_generated_js_contains_selector(js, 'button[data-qa="comments-btn"]')
    _assert_generated_js_contains_selector(js, 'button[data-gtm-class="open-community"]')
    _assert_generated_js_contains_selector(js, "#coral_talk_stream button")
    _assert_generated_js_contains_selector(js, "#coral_thread button")
    _assert_generated_js_contains_selector(js, "#coral-thread button")
    _assert_generated_js_contains_selector(js, "#coral-display-comments")
    _assert_generated_js_contains_selector(js, "[data-embed-coral] button")
    _assert_generated_js_contains_selector(js, "ps-comments#coral_talk_stream button")
    _assert_generated_js_contains_selector(js, "ps-comments#coral_talk_stream")
    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=["button[data-gtm-class=\"open-community\"]"],
    )
    assert clicked == 'button[data-gtm-class="open-community"]'
    assert returned == 'coral_status:timeout;comments=0'
    assert marker == "Comments"

    returned, clicked, marker = _eval_execute_javascript(js, match_selectors=[])
    assert clicked is None
    assert returned == "coral_status:host_missing;comments=0"
    assert marker == "Comments"
    assert actions[3] == {"type": "wait", "milliseconds": 3000}
    assert actions[4] == {"type": "scroll", "direction": "down"}
    assert len(actions) == 5


def test_tier2_actions_for_coral_signal_expands_generic_mother_jones_shape() -> None:
    """Coral shapes with `#coral_thread` use it as a root and click the opener."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]
    _assert_generated_js_contains_selector(js, "#coral-display-comments")

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=["#coral-display-comments"],
        light_dom_selector="#coral_thread",
        light_dom_states=[
            {"text": ""},
            {
                "comments": [
                    {
                        "tagName": "article",
                        "dataTestId": "comment",
                        "author": "MoJoReader",
                        "text": "This public-land context belongs in the discussion.",
                    }
                ]
            },
        ],
    )

    assert clicked == "#coral-display-comments"
    assert returned.startswith(
        "coral_status:copied;comments=1;clicked=#coral-display-comments"
    )
    assert marker is not None
    assert "MoJoReader" in marker
    assert "This public-land context belongs in the discussion." in marker


def test_tier2_actions_for_coral_signal_expands_la_times_ps_comments() -> None:
    """Coral Tier 2 actions click LA Times `ps-comments` Show Comments controls."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        html_fixture=_LA_TIMES_PS_COMMENTS_FIXTURE,
    )
    assert clicked == "ps-comments#coral_talk_stream"
    assert returned == "coral_status:timeout;comments=0"
    assert marker == "Comments"

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        html_fixture="<div></div>",
    )
    assert clicked is None
    assert returned == "coral_status:host_missing;comments=0"
    assert marker == "Comments"


def test_tier2_actions_for_coral_signal_returns_shell_only_for_guideline_only_shadow_root() -> None:
    """A shadow root with only Coral UI chrome is surfaced as shell-only."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        shadow_states=[
            {
                "text": (
                    "Our comments are moderated and if it is off-topic, it will be removed. "
                    "Let's have a nice conversation. All Comments(172)"
                ),
            },
        ],
    )

    assert clicked is None
    assert returned == "coral_status:shell_only;comments=0"
    assert marker == "Comments"


def test_tier2_actions_for_coral_signal_reports_shadow_failure_statuses() -> None:
    """Host and shadow-root failures remain visible as final action statuses."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        shadow_closed=True,
    )
    assert clicked is None
    assert returned == "coral_status:shadow_closed;comments=0"
    assert marker == "Comments"

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        shadow_html="Loading",
    )
    assert clicked is None
    assert returned == "coral_status:clicked_no_match;comments=0"
    assert marker == "Comments"


def test_tier2_actions_for_coral_signal_copies_shadow_comments_to_light_dom() -> None:
    """Coral Tier 2 only copies real comment rows, not shell chrome."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        shadow_states=[
            {
                "comments": [
                    {
                        "tagName": "article",
                        "dataTestId": "comment",
                        "author": "Like_it_really_matters",
                        "text": "This initiative deserves debate.",
                    },
                    {
                        "tagName": "article",
                        "dataTestId": "comment",
                        "author": "johntomas",
                        "text": "Absolutely agree.",
                    },
                ]
            }
        ],
    )

    assert clicked is None
    assert returned == "coral_status:copied;comments=2"
    assert marker is not None
    assert "Like_it_really_matters" in marker
    assert "johntomas" in marker


def test_tier2_actions_for_coral_signal_copies_text_only_coral_comments() -> None:
    """The LA Times textContent shape is enough when DOM classes are unstable."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        shadow_states=[
            {
                "text": (
                    "Comments Our comments are moderated and if it is off-topic, "
                    "it will be removed. All Comments(172) Sort by Newest "
                    "Comment from Like_it_really_matters 2 days ago"
                    "Like_it_really_matters2 days ago"
                    "Small print on page 26 reveals the real plans."
                    "Respect1email-action-replyReplyShareReport"
                    "Thread Level 1: Reply from johntomas 2 days ago"
                    "johntomas2 days agoemail-action-reply In reply to "
                    "Like_it_really_matters There is nothing unusual about "
                    "that clause."
                ),
            },
        ],
    )

    assert clicked is None
    assert returned == "coral_status:copied;comments=2"
    assert marker is not None
    assert "Like_it_really_matters" in marker
    assert "Small print on page 26 reveals the real plans." in marker
    assert "johntomas" in marker
    assert "There is nothing unusual about that clause." in marker


def test_tier2_actions_for_coral_signal_copies_wapo_light_dom_comments() -> None:
    """Washington Post Coral can render into #comments without a shadow root."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        light_dom_states=[
            {
                "comments": [
                    {
                        "tagName": "article",
                        "dataTestId": "comment",
                        "author": "WapoReader",
                        "text": "The Strait of Hormuz context matters here.",
                    },
                ]
            }
        ],
    )

    assert clicked is None
    assert returned == "coral_status:copied;comments=1"
    assert marker is not None
    assert "WapoReader" in marker
    assert "The Strait of Hormuz context matters here." in marker


def test_tier2_actions_for_coral_signal_copies_generic_shadow_root_comments() -> None:
    """Coral Tier 2 finds live Wapo-style open shadow roots beyond one id."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]
    assert "#coral-shadow-root" in js

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        shadow_host_selector="#coral-shadow-root",
        shadow_states=[
            {
                "text": (
                    "Subscribe to comment and get the full experience. "
                    "453 comments Conversation summary Automatically generated "
                    "from recent comments Comment from LiverpoolFCfan Just now"
                    "LiverpoolFCfanJust nowTrump and Hegseth are playing chicken, "
                    "with our troops as pawns.0 Reactmore_horiz"
                ),
            },
        ],
    )

    assert clicked is None
    assert returned == "coral_status:copied;comments=1"
    assert marker is not None
    assert "LiverpoolFCfan" in marker
    assert "Trump and Hegseth are playing chicken, with our troops as pawns." in marker


def test_tier2_actions_for_coral_signal_waits_for_real_comments_after_click() -> None:
    """Click path keeps polling until hydrated comments are visible."""

    actions = _tier2_actions_for(_sample_coral_signal())
    js = actions[2]["script"]

    returned, clicked, marker = _eval_execute_javascript(
        js,
        match_selectors=[],
        html_fixture=_LA_TIMES_PS_COMMENTS_FIXTURE,
        shadow_states=[
            {
                "text": (
                    "Our comments are moderated and if it is off-topic, it will be removed. "
                    "All Comments(172)"
                ),
            },
            {
                "comments": [
                    {
                        "tagName": "article",
                        "dataTestId": "comment",
                        "author": "Like_it_really_matters",
                        "text": "This initiative deserves debate.",
                    },
                    {
                        "tagName": "article",
                        "dataTestId": "comment",
                        "author": "johntomas",
                        "text": "Absolutely agree.",
                    },
                ],
            },
        ],
    )

    assert clicked == "ps-comments#coral_talk_stream"
    assert returned.startswith("coral_status:copied;comments=2;clicked=ps-comments#coral_talk_stream")
    assert marker is not None
    assert "Like_it_really_matters" in marker
    assert "johntomas" in marker


async def test_run_tier2_default_actions_recorded_without_coral_signal() -> None:
    """`_run_tier2` with no Coral signal sends the legacy default action list."""

    url = "https://example.com/article"
    cache = _FakeScrapeCache()
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    result = await _run_tier2(
        url,
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
    )

    assert result.cached is not None
    assert len(interact_client.interact_calls) == 1
    _, interact_kwargs = interact_client.interact_calls[0]
    assert interact_kwargs["actions"] == [{"type": "wait", "milliseconds": 3000}]
    assert interact_kwargs["only_main_content"] is True


async def test_run_tier2_records_coral_specific_actions() -> None:
    """Passing a Coral signal to `_run_tier2` sends stream-expansion actions."""

    url = "https://example.com/article"
    cache = _FakeScrapeCache()
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    result = await _run_tier2(
        url,
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        coral_signal=_sample_coral_signal(),
    )

    assert result.cached is not None
    assert len(interact_client.interact_calls) == 1
    _, interact_kwargs = interact_client.interact_calls[0]
    actions = interact_kwargs["actions"]
    js_actions = [
        action
        for action in actions
        if action["type"] == "executeJavascript"
    ]
    assert len(js_actions) == 1
    assert interact_kwargs["only_main_content"] is False
    js = js_actions[0]["script"]
    _assert_generated_js_contains_selector(
        js, 'button[data-testid="comments-show-comments-button"]'
    )
    _assert_generated_js_contains_selector(js, 'button[data-testid="comments-button"]')
    _assert_generated_js_contains_selector(js, 'button[data-qa="comments-btn"]')
    _assert_generated_js_contains_selector(js, 'button[data-gtm-class="open-community"]')
    _assert_generated_js_contains_selector(js, "#coral_talk_stream button")
    _assert_generated_js_contains_selector(js, "#coral_thread button")
    _assert_generated_js_contains_selector(js, "#coral-thread button")
    _assert_generated_js_contains_selector(js, "#coral-display-comments")
    _assert_generated_js_contains_selector(js, "[data-embed-coral] button")
    assert sum(1 for action in actions if action["type"] == "wait") >= 2
    assert sum(1 for action in actions if action["type"] == "scroll") >= 2


async def test_run_tier2_records_coral_action_status_from_script_outputs() -> None:
    """Coral action script output is preserved on the Tier 2 outcome."""

    url = "https://example.com/article"
    cache = _FakeScrapeCache()
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(
            actions={
                "javascriptReturns": [
                    {"type": "string", "value": "coral_status:copied;comments=2"}
                ]
            }
        )
    )

    result = await _run_tier2(
        url,
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        coral_signal=_sample_coral_signal(),
    )

    assert result.cached is not None
    assert result.coral_action_status == "copied"


async def test_run_tier2_records_shell_only_action_status_from_script_output() -> None:
    """Coral action status parsing handles the `shell_only` enum."""

    url = "https://example.com/article"
    cache = _FakeScrapeCache()
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(
            actions={
                "javascriptReturns": [
                    {"type": "string", "value": "coral_status:shell_only;comments=0"}
                ]
            }
        )
    )

    result = await _run_tier2(
        url,
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
        coral_signal=_sample_coral_signal(),
    )

    assert result.cached is not None
    assert result.coral_action_status == "shell_only"


async def test_scrape_step_tier1_coral_detection_merges_graphql_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 1 Coral detection + successful GraphQL merge appends a `## Comments`
    section in the returned scrape and caches under `tier='scrape'`.
    """

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_ok_scrape_result(
            body="Substantive article body. " * 20,
            html=(
                "<html><body>"
                f"{_CORAL_HTML_FIXTURE}"
                "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                "</body></html>"
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_ok(origin: str, story_url: str) -> CoralComments:
        assert origin == "https://coral.example.com"
        assert story_url == "https://example.com/post"
        return CoralComments(
            comments_markdown="## Comments\n- Great discussion in the comments.",
            raw_count=1,
            fetched_at=datetime.now(UTC),
        )

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_ok)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "Real Article" in markdown
    assert "Substantive article body." in markdown
    assert "## Comments" in markdown
    assert "Great discussion" in markdown
    assert (url, "scrape") in cache.store
    assert (url, "scrape") in cache.puts
    cached_markdown = _require_markdown(cache.store[(url, "scrape")])
    assert "Real Article" in cached_markdown
    assert "## Comments" in cached_markdown
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_la_times_ps_comments_caches_expanded_result_as_interact_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical LA Times `ps-comments` ladder regression caches expanded output
    at `tier='interact'` and skips `tier='scrape'` caching.

    The route should detect LA Times Coral, run only the interact expansion
    ladder, include both article + comment content in the final result, and
    avoid writing a scrape-tier cache row.
    """

    from src.jobs import orchestrator

    span = _install_recording_span(monkeypatch)
    url = "https://www.latimes.com/example/article"
    cache = _FakeScrapeCache()
    article_markdown = "Real Article\n\nSubstantive article body. " * 5
    comment_markdown = "## Comments\n- Great discussion in the comments."
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_ok_scrape_result(
            body=article_markdown,
            html=(
                "<html><body>"
                f"{_LA_TIMES_PS_COMMENTS_FIXTURE}"
                "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                "</body></html>"
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(
            body=f"{article_markdown}\n\n{comment_markdown}",
            actions={
                "javascriptReturns": [
                    {"type": "string", "value": "coral_status:copied;comments=2"}
                ]
            },
        )
    )

    async def fetch_forbidden(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise AssertionError("fetch_coral_comments should not run for LA Times render-only")

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_forbidden)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "Real Article" in markdown
    assert "Substantive article body." in markdown
    assert "Great discussion in the comments." in markdown
    assert len(scrape_client.scrape_calls) == 1
    assert len(interact_client.interact_calls) == 1
    interact_url, interact_kwargs = interact_client.interact_calls[0]
    assert interact_url == url
    actions = interact_kwargs["actions"]
    execute_js = next(
        action for action in actions if action["type"] == "executeJavascript"
    )
    _assert_generated_js_contains_selector(
        execute_js["script"], "ps-comments#coral_talk_stream"
    )
    _, clicked, marker = _eval_execute_javascript(
        execute_js["script"],
        match_selectors=[],
        html_fixture=_LA_TIMES_PS_COMMENTS_FIXTURE,
    )
    assert clicked == "ps-comments#coral_talk_stream"
    assert marker == "Comments"

    assert (url, "interact") in cache.store
    assert (url, "interact") in cache.puts
    assert (url, "scrape") not in cache.store
    assert (url, "scrape") not in cache.puts
    assert span.attrs.get("coral_action_status") == "copied"


async def test_scrape_step_la_times_partial_coral_routes_to_interact_without_scrape_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LA Times partial Coral evidence escalates when direct HTML detection fails."""

    from src.jobs import orchestrator

    span = _install_recording_span(monkeypatch)
    url = "https://www.latimes.com/california/story/2026-04-26/example"
    cache = _FakeScrapeCache()
    article_markdown = "Real Article\n\nSubstantive article body. " * 5
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_ok_scrape_result(
            body=article_markdown,
            html=(
                "<html><body>"
                f"{_PARTIAL_CORAL_HTML_FIXTURE}"
                "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                "</body></html>"
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(
            body=(
                f"{article_markdown}\n\n"
                "## Comments\n- Like_it_really_matters: This initiative deserves debate."
            )
        )
    )

    async def fetch_detection_blocked(_url: str) -> None:
        return None

    monkeypatch.setattr(
        orchestrator,
        "_fetch_coral_detection_html",
        fetch_detection_blocked,
    )

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "Real Article" in markdown
    assert "Like_it_really_matters" in markdown
    assert len(scrape_client.scrape_calls) == 1
    assert len(interact_client.interact_calls) == 1
    actions = interact_client.interact_calls[0][1]["actions"]
    execute_js = next(
        action for action in actions if action["type"] == "executeJavascript"
    )
    _assert_generated_js_contains_selector(
        execute_js["script"], "ps-comments#coral_talk_stream"
    )

    assert (url, "interact") in cache.store
    assert (url, "interact") in cache.puts
    assert (url, "scrape") not in cache.store
    assert (url, "scrape") not in cache.puts
    assert span.attrs.get("tier_attempted") == ["scrape", "interact"]
    assert span.attrs.get("tier_success") == "interact"
    assert span.attrs.get("coral_detected") is True
    assert span.attrs.get("coral_outcome") == "render_only"
    assert span.attrs.get("escalation_reason") == "coral_graphql_unsupported"


async def test_scrape_step_la_times_non_coral_story_id_stays_tier1() -> None:
    """A generic LA Times `data-story-id` attribute is not Coral evidence."""

    url = "https://www.latimes.com/california/story/2026-04-26/example"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_ok_scrape_result(
            body="Substantive article body. " * 20,
            html=(
                "<html><body>"
                '<article data-story-id="not-coral">'
                "<h1>Real Article</h1><p>Substantive article body.</p>"
                "</article>"
                "</body></html>"
            ),
        )
    )
    interact_client = _FakeFirecrawlClient()

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert "Substantive article body." in _require_markdown(result)
    assert (url, "scrape") in cache.puts
    assert (url, "interact") not in cache.puts
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier1_coral_truncated_marker_stays_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 1 treats capped Coral GraphQL output as a successful partial merge."""

    from src.jobs import orchestrator

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_ok_scrape_result(
            body="Substantive article body. " * 20,
            html=(
                "<html><body>"
                f"{_CORAL_HTML_FIXTURE}"
                "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                "</body></html>"
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_ok(origin: str, story_url: str) -> CoralComments:
        assert origin == "https://coral.example.com"
        assert story_url == "https://example.com/post"
        return CoralComments(
            comments_markdown="## Comments\n- Great discussion.\n[comments truncated]",
            raw_count=1,
            fetched_at=datetime.now(UTC),
        )

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_ok)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "[comments truncated]" in markdown
    cached_markdown = _require_markdown(cache.store[(url, "scrape")])
    assert "[comments truncated]" in cached_markdown
    assert span.attrs.get("coral_outcome") == "merged"
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier1_partial_coral_markers_triggers_direct_html_fetch_for_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tagesspiegel-style partial Coral evidence triggers direct fetch and GraphQL merge."""

    from src.jobs import orchestrator

    url = "https://www.tagesspiegel.de/example/article"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_ok_scrape_result(
            body="Substantive article body. " * 20,
            html=(
                "<html><body>"
                f"{_PARTIAL_CORAL_HTML_FIXTURE}"
                "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                "</body></html>"
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_detection_html(_url: str) -> str:
        return _CORAL_DETECTION_HTML_FIXTURE

    monkeypatch.setattr(
        orchestrator,
        "_fetch_coral_detection_html",
        fetch_detection_html,
    )

    async def fetch_ok(origin: str, story_url: str) -> CoralComments:
        assert origin == "https://coral.tagesspiegel.de"
        assert story_url == "https://www.tagesspiegel.de/2026/04/29/example"
        return CoralComments(
            comments_markdown="## Comments\n- Great discussion in the comments.",
            raw_count=1,
            fetched_at=datetime.now(UTC),
        )

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_ok)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "Real Article" in markdown
    assert "Substantive article body." in markdown
    assert "## Comments" in markdown
    assert "Great discussion in the comments." in markdown
    assert (url, "scrape") in cache.store
    assert (url, "scrape") in cache.puts
    assert "## Comments" in _require_markdown(cache.store[(url, "scrape")])
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier1_coral_iframe_fallback_success_merges_comments_without_tier2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GraphQL failure falls back to iframe scrape, merges comment markdown, and
    returns Tier-1 success."""

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_PARTIAL_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            _comment_scrape_result(
                body="## Comments\n- Great discussion in the iframe comments.",
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=lambda: (_ for _ in ()).throw(
            AssertionError("/interact should not run after iframe fallback merge")
        )
    )

    async def fetch_fails(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise CoralFetchError("temporary coral graphql error")

    async def fetch_detection_html(_url: str) -> str:
        return _CORAL_DETECTION_HTML_FIXTURE

    monkeypatch.setattr(
        orchestrator,
        "_fetch_coral_detection_html",
        fetch_detection_html,
    )
    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_fails)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert "Great discussion in the iframe comments." in _require_markdown(result)
    assert (url, "scrape") in cache.store
    assert (url, "scrape") in cache.puts
    assert (
        "Great discussion in the iframe comments."
        in _require_markdown(cache.store[(url, "scrape")])
    )
    assert len(scrape_client.scrape_calls) == 2
    assert scrape_client.scrape_calls[1][0] == (
        "https://coral.tagesspiegel.de/embed/stream?asset_id=15538543&asset_url="
        "https%3A%2F%2Fwww.tagesspiegel.de%2F2026%2F04%2F29%2Fexample"
    )
    assert scrape_client.scrape_calls[1][1]["formats"] == ["markdown", "html"]
    assert scrape_client.scrape_calls[1][1]["only_main_content"] is False
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier1_coral_iframe_fallback_rejected_source_url_escalates_to_tier2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private iframe redirect targets are treated as SSRF risk and keep
    Coral fallback best-effort."""

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_PARTIAL_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            ScrapeResult(
                markdown="## Comments\n- Should not merge private iframe comments.",
                html="<html><body><section>Coral comments iframe</section></body></html>",
                metadata=ScrapeMetadata(
                    status_code=200,
                    source_url="http://127.0.0.1/comments",
                ),
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(body="## Comments\n- Tier 2 rendered comments.")
    )

    async def fetch_fails(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise CoralFetchError("temporary coral graphql error")

    async def fetch_detection_html(_url: str) -> str:
        return _CORAL_DETECTION_HTML_FIXTURE

    monkeypatch.setattr(
        orchestrator,
        "_fetch_coral_detection_html",
        fetch_detection_html,
    )
    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_fails)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "Should not merge private iframe comments." not in markdown
    assert "Tier 2 rendered comments." in markdown
    assert (url, "scrape") in cache.store
    assert (
        "Should not merge private iframe comments."
        not in _require_markdown(cache.store[(url, "scrape")])
    )
    assert len(scrape_client.scrape_calls) == 2
    assert scrape_client.scrape_calls[1][0] == (
        "https://coral.tagesspiegel.de/embed/stream?asset_id=15538543&asset_url="
        "https%3A%2F%2Fwww.tagesspiegel.de%2F2026%2F04%2F29%2Fexample"
    )
    assert len(interact_client.interact_calls) == 1
    assert interact_client.interact_calls[0][0] == url
    actions = interact_client.interact_calls[0][1]["actions"]
    assert len(actions) == 5
    assert actions[0] == {"type": "wait", "milliseconds": 2000}
    assert actions[1] == {"type": "scroll", "direction": "down"}
    assert actions[3] == {"type": "wait", "milliseconds": 3000}
    assert actions[4] == {"type": "scroll", "direction": "down"}
    assert "executeJavascript" in actions[2]["type"]
    assert "#coral_talk_stream button" in actions[2]["script"]
    assert (url, "interact") in cache.store


async def test_scrape_step_tier1_coral_iframe_fallback_malformed_final_url_escalates_to_tier2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed iframe final URLs are treated as fallback failure and escalate to Tier 2."""

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_PARTIAL_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            ScrapeResult(
                markdown="## Comments\n- Should not merge malformed iframe comments.",
                html="<html><body><section>Coral comments iframe</section></body></html>",
                metadata=ScrapeMetadata(
                    status_code=200,
                    source_url="http://[::1",
                ),
            ),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(body="## Comments\n- Tier 2 rendered comments.")
    )

    async def fetch_fails(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise CoralFetchError("temporary coral graphql error")

    async def fetch_detection_html(_url: str) -> str:
        return _CORAL_DETECTION_HTML_FIXTURE

    monkeypatch.setattr(
        orchestrator,
        "_fetch_coral_detection_html",
        fetch_detection_html,
    )
    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_fails)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    markdown = _require_markdown(result)
    assert "Should not merge malformed iframe comments." not in markdown
    assert "Tier 2 rendered comments." in markdown
    assert (url, "scrape") in cache.store
    assert (
        "Should not merge malformed iframe comments."
        not in _require_markdown(cache.store[(url, "scrape")])
    )
    assert len(interact_client.interact_calls) == 1
    assert interact_client.interact_calls[0][0] == url
    assert (url, "interact") in cache.store


async def test_scrape_step_tier1_coral_graphql_failure_escalates_to_tier2_with_coral_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coral GraphQL fetch failure caches the tier-1 row and escalates to tier2
    with the Coral click selector so the comment stream still has a chance."""

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            _interstitial_scrape_result(),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_ok_scrape_result(body="Tier 2 rendered comments. " * 20)
    )

    async def fetch_fails(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise CoralFetchError("temporary coral graphql error")

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_fails)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert "Tier 2 rendered comments." in _require_markdown(result)
    assert len(scrape_client.scrape_calls) == 2
    assert len(interact_client.interact_calls) == 1
    assert (url, "scrape") in cache.store
    assert (url, "interact") in cache.store
    assert "Tier 2 rendered comments." in _require_markdown(
        cache.store[(url, "interact")]
    )
    assert scrape_client.scrape_calls[1][0].startswith("https://coral.example.com/embed/stream")
    assert scrape_client.scrape_calls[1][1]["formats"] == ["markdown", "html"]
    assert scrape_client.scrape_calls[1][1]["only_main_content"] is False
    _, interact_kwargs = interact_client.interact_calls[0]
    actions = interact_kwargs["actions"]
    assert any(action["type"] == "executeJavascript" for action in actions)


async def test_scrape_step_tier1_coral_graphql_failure_then_tier2_fail_raises_unsupported_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coral GraphQL failure then tier-2 failure is terminal with both-tier reasons."""

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            _interstitial_scrape_result(),
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_interstitial_scrape_result()
    )

    async def fetch_fails(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise CoralFetchError("temporary coral graphql error")

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_fails)

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE
    msg = exc_info.value.error_detail.lower()
    assert "tier 1:" in msg
    assert "coral_graphql_failed" in msg
    assert "temporary coral graphql error" in msg
    assert "tier 2:" in msg
    assert "interstitial" in msg
    assert (url, "interact") not in cache.store
    assert (url, "scrape") in cache.store
    assert len(scrape_client.scrape_calls) == 2
    assert scrape_client.scrape_calls[1][0].startswith("https://coral.example.com/embed/stream")
    assert scrape_client.scrape_calls[1][1]["formats"] == ["markdown", "html"]
    assert scrape_client.scrape_calls[1][1]["only_main_content"] is False
    assert len(interact_client.interact_calls) == 1
    _, interact_kwargs = interact_client.interact_calls[0]
    actions = interact_kwargs["actions"]
    assert any(action["type"] == "executeJavascript" for action in actions)


async def test_scrape_step_tier1_cache_hit_with_merged_coral_comments_skips_graphql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached merged Tier-1 Coral row is reused; no scrape or GraphQL re-fetch."""

    from src.jobs import orchestrator

    url = "https://example.com/cached-coral-post"
    cache = _FakeScrapeCache()
    cache.store[(url, "scrape")] = CachedScrape(
        markdown=(
            "# Real Article\n\nSubstantive article body.\n\n"
            "## Comments\n- Great discussion in the comments."
        ),
        html=(
            "<html><body>"
            f"{_CORAL_HTML_FIXTURE}"
            "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
            "</body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="cached-coral-marked-up",
    )
    scrape_client = _FakeFirecrawlClient(
        scrape_result=lambda: (_ for _ in ()).throw(
            AssertionError("scrape must not run on scrape cache hit")
        )
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_forbidden(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise AssertionError(
            "fetch_coral_comments should not run on scraped-tier cache hit"
        )

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_forbidden)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.storage_key == "cached-coral-marked-up"
    assert "Great discussion in the comments." in _require_markdown(result)
    assert len(scrape_client.scrape_calls) == 0
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_tier1_non_coral_ok_does_not_call_graphql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-Coral pages should never call Coral GraphQL, even with an OK Tier-1
    classification."""

    from src.jobs import orchestrator

    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(scrape_result=_ok_scrape_result())
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_forbidden(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise AssertionError("fetch_coral_comments should not run for non-coral pages")

    async def fetch_not_called(*_url: str) -> str:
        raise AssertionError("direct Coral detection fetch should not run for non-coral pages")

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_forbidden)
    monkeypatch.setattr(orchestrator, "_fetch_coral_detection_html", fetch_not_called)

    result = await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert result.markdown is not None
    assert len(interact_client.interact_calls) == 0


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


# TASK-1488.13 — UNSUPPORTED_SITE raise sites carry detail["error_host"]
# so `_mark_failed` can populate `vibecheck_jobs.error_host` and the FE
# can render host-specific copy ("We can't analyze {host} yet").


async def test_scrape_step_both_tiers_blocked_populates_error_host() -> None:
    """Both-tiers-failed raise (orchestrator.py: fresh Tier 1 → Tier 2 →
    UNSUPPORTED_SITE) carries `detail['error_host']` with the URL hostname.
    """
    url = "https://hardblocked.example/post"
    cache = _FakeScrapeCache()

    def _blocked_t1() -> ScrapeResult:
        raise FirecrawlBlocked("scrape refused: 403")

    def _blocked_t2() -> ScrapeResult:
        raise FirecrawlBlocked("interact refused: 403")

    scrape_client = _FakeFirecrawlClient(scrape_result=_blocked_t1)
    interact_client = _FakeFirecrawlClient(interact_result=_blocked_t2)

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE
    assert exc_info.value.detail.get("error_host") == "hardblocked.example"


async def test_scrape_step_cached_t1_interstitial_t2_failed_populates_error_host() -> None:
    """Cached-Tier-1-INTERSTITIAL → Tier 2 fail raise site also carries
    `detail['error_host']` so the FE renders host-specific copy on
    cached-then-still-blocked retries.
    """
    url = "https://cachedblock.example/post"
    cache = _FakeScrapeCache()
    cache.store[(url, "scrape")] = CachedScrape(
        markdown="Just a moment... checking",
        html="<title>Just a moment...</title>",
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="t1-interstitial-key",
    )
    scrape_client = _FakeFirecrawlClient(
        scrape_result=lambda: (_ for _ in ()).throw(
            AssertionError("scrape must not be called on Tier 1 cache hit")
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_interstitial_scrape_result()
    )

    with pytest.raises(TerminalError) as exc_info:
        await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE
    assert exc_info.value.detail.get("error_host") == "cachedblock.example"


async def test_scrape_step_forced_t2_failed_populates_error_host() -> None:
    """`force_tier='interact'` (the post-Gemini once-only escalation) raise
    site also carries `detail['error_host']` when Tier 2 fails.
    """
    from src.jobs import orchestrator

    url = "https://forced.example/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=lambda: (_ for _ in ()).throw(
            AssertionError("scrape must not run when force_tier='interact'")
        )
    )
    interact_client = _FakeFirecrawlClient(
        interact_result=_interstitial_scrape_result()
    )

    with pytest.raises(TerminalError) as exc_info:
        await orchestrator._scrape_step(
            url,
            cast(FirecrawlClient, cast(object, scrape_client)),
            cast(FirecrawlClient, cast(object, interact_client)),
            cast(SupabaseScrapeCache, cast(object, cache)),
            force_tier="interact",
        )

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE
    assert exc_info.value.detail.get("error_host") == "forced.example"


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


async def test_scrape_step_tier2_cached_auth_wall_is_rejected() -> None:
    """A cached Tier 2 auth-wall result should not be returned as content.

    When `_run_tier2` reads a cached interact-tier row, it must still
    classify and only short-circuit when the row is OK. AUTH_WALL cached
    rows must be surfaced as unsupported-site failures and re-fetch via
    interact must not run.
    """
    from src.jobs import orchestrator

    url = "https://example.com/login-gated"
    cache = _FakeScrapeCache()
    cache.store[(url, "interact")] = CachedScrape(
        markdown="Please sign in",
        html=(
            "<html><body><form action='https://example.com/login'"
            " method='post'><input name='username' /></form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="cached-auth-wall-key",
    )

    def _blocked() -> ScrapeResult:
        raise FirecrawlBlocked("firecrawl /v2/scrape refused: 403 do not support this site")

    scrape_client = _FakeFirecrawlClient(scrape_result=_blocked)
    interact_client = _FakeFirecrawlClient(
        interact_result=lambda: (_ for _ in ()).throw(
            AssertionError("interact must not run when cached Tier 2 auth_wall exists")
        )
    )

    with pytest.raises(TerminalError) as exc_info:
        await orchestrator._scrape_step(
            url,
            cast(FirecrawlClient, cast(object, scrape_client)),
            cast(FirecrawlClient, cast(object, interact_client)),
            cast(SupabaseScrapeCache, cast(object, cache)),
        )

    assert exc_info.value.error_code is ErrorCode.UNSUPPORTED_SITE
    assert "tier 2: auth_wall" in exc_info.value.error_detail
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
    assert span.attrs.get("coral_detected") is False
    assert span.attrs.get("coral_outcome") is None


async def test_scrape_step_logfire_span_records_coral_merge_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coral merge success on Tier 1 sets Coral attributes in the span."""

    from src.jobs import orchestrator

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            _interstitial_scrape_result(),
        )
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_ok(origin: str, story_url: str) -> CoralComments:
        return CoralComments(
            comments_markdown="## Comments\n- Great discussion",
            raw_count=1,
            fetched_at=datetime.now(UTC),
        )

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_ok)

    await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("coral_detected") is True
    assert span.attrs.get("coral_outcome") == "merged"
    assert span.attrs.get("tier_attempted") == ["scrape"]
    assert span.attrs.get("tier_success") == "scrape"
    assert span.attrs.get("escalation_reason") is None


async def test_scrape_step_logfire_span_records_coral_graphql_failed_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coral GraphQL failure path sets `coral_outcome='graphql_failed'`."""

    from src.jobs import orchestrator

    span = _install_recording_span(monkeypatch)
    url = "https://example.com/post"
    cache = _FakeScrapeCache()
    scrape_client = _FakeFirecrawlClient(
        scrape_result=_scrape_results(
            _ok_scrape_result(
                html=(
                    "<html><body>"
                    f"{_CORAL_HTML_FIXTURE}"
                    "<article><h1>Real Article</h1><p>Substantive article body.</p></article>"
                    "</body></html>"
                )
            ),
            _interstitial_scrape_result(),
        )
    )
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    async def fetch_fails(*_args: Any, **_kwargs: Any) -> CoralComments:
        raise CoralUnsupportedError("unsupported comments endpoint")

    monkeypatch.setattr(orchestrator, "fetch_coral_comments", fetch_fails)

    await _call_scrape_step(url, scrape_client, interact_client, cache)

    assert span.attrs.get("coral_detected") is True
    assert span.attrs.get("coral_outcome") == "graphql_failed"
    assert span.attrs.get("tier_attempted") == ["scrape", "interact"]
    assert span.attrs.get("tier_success") == "interact"
    assert span.attrs.get("escalation_reason") == "coral_graphql_failed"
    assert len(scrape_client.scrape_calls) == 2


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
    assert all(entry[1] == "interact" for entry in cache.gets)
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


@pytest.mark.parametrize(
    ("cached_tier", "expected_storage_key", "expected_cache_reads"),
    [
        ("interact", "cached-interact", ["interact"]),
        ("scrape", "cached-scrape", ["interact", "scrape"]),
    ],
)
async def test_scrape_step_default_reuses_successful_cached_scrape_from_firecrawl_tiers(
    cached_tier: str,
    expected_storage_key: str,
    expected_cache_reads: list[str],
) -> None:
    """A retry of a timed-out job should not re-scrape just because the
    prior successful scrape was stored under a richer tier.
    """
    from src.jobs import orchestrator

    url = "https://example.com/retry-cached-page"
    cache = _FakeScrapeCache()
    cache.store[(url, cached_tier)] = CachedScrape(
        markdown="cached article body " * 10,
        html="<article><h1>Cached</h1><p>cached article body</p></article>",
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key=expected_storage_key,
    )

    def _fail() -> ScrapeResult:
        raise AssertionError("retry must reuse the cached scrape without Firecrawl")

    scrape_client = _FakeFirecrawlClient(scrape_result=_fail)
    interact_client = _FakeFirecrawlClient(interact_result=_fail)

    result = await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
    )

    assert result.storage_key == expected_storage_key
    assert [entry[1] for entry in cache.gets] == expected_cache_reads
    assert cache.evicts == []
    assert len(scrape_client.scrape_calls) == 0
    assert len(interact_client.interact_calls) == 0


async def test_scrape_step_default_ignores_url_scoped_browser_html_cache() -> None:
    """Browser-submitted HTML is job-scoped, not reusable by normalized URL."""
    from src.jobs import orchestrator

    url = "https://example.com/retry-cached-page"
    cache = _FakeScrapeCache()
    cache.store[(url, "browser_html")] = CachedScrape(
        markdown="operator captured browser html " * 10,
        html="<article><h1>Operator Capture</h1><p>private page state</p></article>",
        metadata=ScrapeMetadata(status_code=200, source_url=url),
        storage_key="cached-browser-html",
    )

    fresh_scrape = _ok_scrape_result(body="fresh firecrawl article body " * 10)
    scrape_client = _FakeFirecrawlClient(scrape_result=fresh_scrape)
    interact_client = _FakeFirecrawlClient(interact_result=_ok_scrape_result())

    result = await orchestrator._scrape_step(
        url,
        cast(FirecrawlClient, cast(object, scrape_client)),
        cast(FirecrawlClient, cast(object, interact_client)),
        cast(SupabaseScrapeCache, cast(object, cache)),
    )

    assert result.storage_key == "scrape-key-1"
    assert [entry[1] for entry in cache.gets] == ["interact", "scrape"]
    assert cache.puts == [(url, "scrape")]
    assert len(scrape_client.scrape_calls) == 1
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

    async def noop_headline(*args: Any, **kwargs: Any) -> None:
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
    monkeypatch.setattr(
        orchestrator, "_run_headline_summary_step", noop_headline
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


async def test_run_pipeline_uses_browser_html_cache_without_classifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser_html jobs trust the operator-submitted cache row and skip the
    normal Tier 1 quality classifier path, which would reject auth-gated pages.
    """
    from src.jobs import orchestrator

    _stub_extract_arm_only(monkeypatch)

    job_id = uuid4()
    task_attempt = uuid4()
    url = "https://example.com/private"
    cache = _FakeScrapeCache()
    monkeypatch.setattr(orchestrator, "_build_scrape_cache", lambda s: cache)
    monkeypatch.setattr(orchestrator, "_build_firecrawl_client", lambda s: MagicMock())
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
    )

    async def no_scrape_step(*args: Any, **kwargs: Any) -> CachedScrape:
        raise AssertionError("_scrape_step must not run for browser_html jobs")

    async def noop_revalidate(*args: Any, **kwargs: Any) -> None:
        return None

    captured: dict[str, Any] = {}

    async def capturing_extract(*args: Any, **kwargs: Any):
        captured["kwargs"] = kwargs
        raise UtteranceExtractionError("stop here")

    class SourceTypeConn:
        async def fetchval(self, *args: Any, **kwargs: Any) -> str:
            return "browser_html"

        async def fetchrow(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "url": url,
                "final_url": url,
                "page_title": "Private",
                "markdown": "private page",
                "html": "<html><body>private browser html</body></html>",
                "screenshot_storage_key": None,
            }

    monkeypatch.setattr(orchestrator, "_scrape_step", no_scrape_step)
    monkeypatch.setattr(orchestrator, "_revalidate_final_url", noop_revalidate)
    monkeypatch.setattr(orchestrator, "extract_utterances", capturing_extract)

    with pytest.raises(orchestrator.TerminalError):
        await orchestrator._run_pipeline(
            FakePool(SourceTypeConn()),
            job_id,
            task_attempt,
            url,
            MagicMock(),
            source_type="browser_html",
        )

    assert cache.gets == []
    scrape = captured["kwargs"].get("scrape")
    assert scrape.markdown == "private page"
    assert scrape.html == "<html><body>private browser html</body></html>"
    assert scrape.metadata.title == "Private"


# ---------------------------------------------------------------------------
# TASK-1508.04.03 — _STAGE_HEADLINE_SUMMARY between safety_recommendation
# and finalize. Mirrors the safety_recommendation step coverage above:
# success path, agent-failure swallowed, attempt-rotation no-op, and the
# input-aggregation helper for missing slots.
# ---------------------------------------------------------------------------


class HeadlineSummaryConn:
    def __init__(
        self,
        sections,
        *,
        safety_recommendation: Any = None,
        page_title: str | None = None,
        page_kind: str | None = "other",
        attempt_matches: bool = True,
    ) -> None:
        self.sections = sections
        self.safety_recommendation = safety_recommendation
        self.page_title = page_title
        self.page_kind = page_kind
        self.attempt_matches = attempt_matches
        self.written: dict[str, Any] | None = None

    async def fetchrow(self, query, job_id, task_attempt):
        if not self.attempt_matches:
            return None
        return {
            "sections": self.sections,
            "safety_recommendation": self.safety_recommendation,
            "page_title": self.page_title,
            "page_kind": self.page_kind,
        }

    async def execute(self, query, job_id, headline_json, task_attempt):
        self.written = {
            "query": query,
            "job_id": job_id,
            "headline_json": headline_json,
            "task_attempt": task_attempt,
        }
        return "UPDATE 1" if self.attempt_matches else "UPDATE 0"


def _all_sections_done(**overrides):
    """Section dict with all 10 slots in DONE state, populated with empty data."""
    sections = {
        SectionSlug.SAFETY_MODERATION.value: _slot(
            SectionState.DONE, {"harmful_content_matches": []}
        ),
        SectionSlug.SAFETY_WEB_RISK.value: _slot(
            SectionState.DONE, {"findings": []}
        ),
        SectionSlug.SAFETY_IMAGE_MODERATION.value: _slot(
            SectionState.DONE, {"matches": []}
        ),
        SectionSlug.SAFETY_VIDEO_MODERATION.value: _slot(
            SectionState.DONE, {"matches": []}
        ),
        SectionSlug.TONE_DYNAMICS_FLASHPOINT.value: _slot(
            SectionState.DONE, {"flashpoint_matches": []}
        ),
        SectionSlug.TONE_DYNAMICS_SCD.value: _slot(
            SectionState.DONE,
            {
                "scd": {
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                }
            },
        ),
        SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot(
            SectionState.DONE,
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            },
        ),
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO.value: _slot(
            SectionState.DONE, {"known_misinformation": []}
        ),
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value: _slot(
            SectionState.DONE,
            {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                }
            },
        ),
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE.value: _slot(
            SectionState.DONE, {"subjective_claims": []}
        ),
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS.value: _slot(
            SectionState.DONE,
            {
                "trends_oppositions_report": {
                    "trends": [],
                    "oppositions": [],
                    "input_cluster_count": 0,
                    "skipped_for_cap": 0,
                }
            },
        ),
    }
    sections.update(overrides)
    return sections


async def test_headline_summary_step_writes_serialized_summary(monkeypatch):
    from src.analyses.schemas import HeadlineSummary
    from src.jobs import orchestrator

    captured_inputs: list[Any] = []

    async def fake_run(inputs, settings, job_id):
        captured_inputs.append(inputs)
        return HeadlineSummary(
            text="Routine page; little to flag.",
            kind="stock",
            unavailable_inputs=[],
        )

    monkeypatch.setattr(orchestrator, "run_headline_summary", fake_run)

    job_id = uuid4()
    task_attempt = uuid4()
    conn = HeadlineSummaryConn(_all_sections_done(), page_title="Example", page_kind="article")

    await orchestrator._run_headline_summary_step(
        FakePool(conn), job_id, task_attempt, MagicMock()
    )

    assert len(captured_inputs) == 1
    assert captured_inputs[0].page_title == "Example"
    assert captured_inputs[0].page_kind.value == "article"
    assert conn.written is not None
    assert '"text": "Routine page; little to flag."' in conn.written["headline_json"]
    assert '"kind": "stock"' in conn.written["headline_json"]
    assert conn.written["task_attempt"] == task_attempt


async def test_headline_summary_step_marks_failed_slots_unavailable(monkeypatch):
    from src.analyses.schemas import HeadlineSummary
    from src.jobs import orchestrator

    captured_inputs: list[Any] = []

    async def fake_run(inputs, settings, job_id):
        captured_inputs.append(inputs)
        return HeadlineSummary(
            text="Quiet content with nothing to highlight.",
            kind="synthesized",
            unavailable_inputs=inputs.unavailable_inputs,
        )

    monkeypatch.setattr(orchestrator, "run_headline_summary", fake_run)

    conn = HeadlineSummaryConn(
        _all_sections_done(
            **{
                SectionSlug.TONE_DYNAMICS_SCD.value: _slot(SectionState.FAILED),
                SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot(SectionState.FAILED),
            }
        ),
    )

    await orchestrator._run_headline_summary_step(
        FakePool(conn), uuid4(), uuid4(), MagicMock()
    )

    inputs = captured_inputs[0]
    assert inputs.scd is None
    assert inputs.claims_report is None
    assert "scd" in inputs.unavailable_inputs
    assert "claims_dedup" in inputs.unavailable_inputs
    # Missing safety_recommendation should also be tracked as unavailable.
    assert "safety_recommendation" in inputs.unavailable_inputs


async def test_headline_summary_step_swallows_agent_exception(monkeypatch):
    from src.jobs import orchestrator

    async def fake_run(inputs, settings, job_id):
        raise RuntimeError("agent unavailable")

    monkeypatch.setattr(orchestrator, "run_headline_summary", fake_run)
    conn = HeadlineSummaryConn(_all_sections_done())

    await orchestrator._run_headline_summary_step(
        FakePool(conn), uuid4(), uuid4(), MagicMock()
    )

    assert conn.written is None


async def test_headline_summary_step_noops_when_attempt_rotates(monkeypatch):
    from src.jobs import orchestrator

    async def fake_run(inputs, settings, job_id):
        raise AssertionError("agent should not run when the attempt row is gone")

    monkeypatch.setattr(orchestrator, "run_headline_summary", fake_run)
    conn = HeadlineSummaryConn(_all_sections_done(), attempt_matches=False)

    await orchestrator._run_headline_summary_step(
        FakePool(conn), uuid4(), uuid4(), MagicMock()
    )

    assert conn.written is None


def test_build_headline_summary_inputs_propagates_safety_recommendation(monkeypatch):
    from src.jobs import orchestrator

    sections = orchestrator._parse_sections(_all_sections_done())
    inputs = orchestrator._build_headline_summary_inputs(
        sections,
        {
            "level": "caution",
            "rationale": "Some inputs were unavailable.",
            "top_signals": [],
            "unavailable_inputs": [],
        },
        "Title",
        "article",
    )

    assert inputs.safety_recommendation is not None
    assert inputs.safety_recommendation.level == SafetyLevel.CAUTION
    assert "safety_recommendation" not in inputs.unavailable_inputs


def test_build_headline_summary_inputs_marks_safety_unavailable_when_null(monkeypatch):
    from src.jobs import orchestrator

    sections = orchestrator._parse_sections(_all_sections_done())
    inputs = orchestrator._build_headline_summary_inputs(
        sections, None, None, None
    )

    assert inputs.safety_recommendation is None
    assert "safety_recommendation" in inputs.unavailable_inputs
    assert inputs.page_kind.value == "other"
