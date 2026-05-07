"""Weather-report orchestration coverage (TASK-1508.19.05)."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.analyses.schemas import SectionSlug
from src.analyses.synthesis._weather_schemas import WeatherAxis, WeatherReport
from src.jobs import orchestrator


class FakeAcquire:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    async def __aenter__(self) -> Any:
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class FakePool:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


class WeatherReportConnection:
    def __init__(
        self,
        sections: dict[str, Any],
        *,
        safety_recommendation: Any = None,
        page_title: str | None = None,
        page_kind: str | None = "other",
        attempt_matches: bool = True,
        fail_execute: bool = False,
    ) -> None:
        self.sections = sections
        self.safety_recommendation = safety_recommendation
        self.page_title = page_title
        self.page_kind = page_kind
        self.attempt_matches = attempt_matches
        self.fail_execute = fail_execute
        self.written: dict[str, Any] | None = None

    async def fetchrow(self, query: str, _job_id: UUID, task_attempt: UUID) -> dict[str, Any] | None:
        if not self.attempt_matches:
            return None
        del query, task_attempt
        return {
            "sections": self.sections,
            "safety_recommendation": self.safety_recommendation,
            "page_title": self.page_title,
            "page_kind": self.page_kind,
        }

    async def execute(
        self,
        query: str,
        job_id: UUID,
        weather_json: str,
        task_attempt: UUID,
    ) -> str:
        if self.fail_execute:
            raise RuntimeError("weather column unavailable")
        self.written = {
            "query": query,
            "job_id": job_id,
            "weather_json": weather_json,
            "task_attempt": task_attempt,
        }
        return "UPDATE 1" if self.attempt_matches else "UPDATE 0"


def _complete_sections() -> dict[str, Any]:
    return {
        SectionSlug.SAFETY_MODERATION.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"harmful_content_matches": []},
        },
        SectionSlug.SAFETY_WEB_RISK.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"findings": []},
        },
        SectionSlug.SAFETY_IMAGE_MODERATION.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"matches": []},
        },
        SectionSlug.SAFETY_VIDEO_MODERATION.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"matches": []},
        },
        SectionSlug.TONE_DYNAMICS_FLASHPOINT.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"flashpoint_matches": []},
        },
        SectionSlug.TONE_DYNAMICS_SCD.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {
                "scd": {
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                }
            },
        },
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
        },
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"known_misinformation": []},
        },
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                }
            },
        },
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"subjective_claims": []},
        },
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {
                "trends_oppositions_report": {
                    "trends": [],
                    "oppositions": [],
                    "input_cluster_count": 0,
                    "skipped_for_cap": 0,
                }
            },
        },
        SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {
                "highlights_report": {
                    "highlights": [],
                    "threshold": {
                        "total_authors": 0,
                        "total_utterances": 0,
                        "min_authors_required": 2,
                        "min_occurrences_required": 3,
                    },
                    "fallback_engaged": False,
                    "floor_eligible_count": 0,
                    "total_input_count": 0,
                }
            },
        },
    }


def _report_json() -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis(label="sourced", alternatives=[]),
        relevance=WeatherAxis(label="on_topic", alternatives=[]),
        sentiment=WeatherAxis(label="neutral", alternatives=[]),
    )


@pytest.mark.asyncio
async def test_weather_report_step_writes_report_when_agent_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_inputs: list[Any] = []

    async def fake_evaluate_weather(inputs, settings, *, job_id):
        del settings, job_id
        captured_inputs.append(inputs)
        return _report_json()

    monkeypatch.setattr(orchestrator, "evaluate_weather", fake_evaluate_weather)
    conn = WeatherReportConnection(
        _complete_sections(),
        page_title="Example",
        page_kind="article",
    )

    job_id = uuid4()
    task_attempt = uuid4()
    await orchestrator._run_weather_report_step(
        FakePool(conn),
        job_id,
        task_attempt,
        MagicMock(),
    )

    assert captured_inputs
    assert captured_inputs[0].page_title == "Example"
    assert captured_inputs[0].page_kind.value == "article"
    assert conn.written is not None
    assert "weather_report = $2::jsonb" in conn.written["query"]
    assert conn.written["job_id"] == job_id
    assert conn.written["task_attempt"] == task_attempt
    parsed = json.loads(conn.written["weather_json"])
    assert parsed["truth"]["label"] == "sourced"
    assert parsed["relevance"]["label"] == "on_topic"


@pytest.mark.asyncio
async def test_weather_report_step_swallow_agent_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_evaluate_weather(*args: Any, **kwargs: Any) -> WeatherReport:
        del args, kwargs
        raise RuntimeError("weather model unavailable")

    monkeypatch.setattr(orchestrator, "evaluate_weather", fake_evaluate_weather)
    conn = WeatherReportConnection(_complete_sections())

    await orchestrator._run_weather_report_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        MagicMock(),
    )

    assert conn.written is None


@pytest.mark.asyncio
async def test_weather_report_step_swallow_persistence_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_evaluate_weather(*args: Any, **kwargs: Any) -> WeatherReport:
        del args, kwargs
        return _report_json()

    monkeypatch.setattr(orchestrator, "evaluate_weather", fake_evaluate_weather)
    conn = WeatherReportConnection(_complete_sections(), fail_execute=True)

    await orchestrator._run_weather_report_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        MagicMock(),
    )

    assert conn.written is None


@pytest.mark.asyncio
async def test_section_retry_runs_headline_and_weather_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = time.perf_counter
    timeline: dict[str, float] = {}
    test_slug = SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT

    async def fake_run_section(
        *_args: Any, **_kwargs: Any
    ) -> dict[str, Any] | None:
        return None

    async def fake_load(*args: Any, **kwargs: Any) -> tuple[UUID, dict[str, Any]]:
        del args, kwargs
        task_attempt = fixed_task_attempt
        return task_attempt, {
            "state": "running",
            "attempt_id": str(task_attempt),
            "data": None,
        }

    async def fake_run_headline(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        timeline["headline_start"] = now()
        await asyncio.sleep(0.05)
        timeline["headline_end"] = now()

    async def fake_run_weather(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        timeline["weather_start"] = now()
        await asyncio.sleep(0.01)
        timeline["weather_end"] = now()

    async def fake_mark_slot_done(*_args: Any, **_kwargs: Any) -> int:
        return 1

    async def fake_set_last_stage(*_args: Any, **_kwargs: Any) -> None:
        return

    async def fake_finalize(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        timeline["finalize"] = now()
        return True

    fixed_task_attempt = uuid4()
    job_id = uuid4()

    monkeypatch.setattr(orchestrator, "_load_job_attempt_and_slot", fake_load)
    monkeypatch.setitem(orchestrator._SECTION_HANDLERS, test_slug, fake_run_section)
    monkeypatch.setattr(
        orchestrator, "_run_headline_summary_step", fake_run_headline
    )
    monkeypatch.setattr(orchestrator, "mark_slot_done", fake_mark_slot_done)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", AsyncMock())
    monkeypatch.setattr(orchestrator, "_set_last_stage", fake_set_last_stage)
    monkeypatch.setattr(orchestrator, "_run_safety_recommendation_step", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_weather_report_step", fake_run_weather)
    monkeypatch.setattr(orchestrator, "maybe_finalize_job", fake_finalize)

    call_result = await orchestrator.run_section_retry(
        pool=FakePool(WeatherReportConnection(_complete_sections())),
        job_id=job_id,
        slug=test_slug,
        expected_slot_attempt_id=fixed_task_attempt,
        settings=MagicMock(),
    )

    assert call_result.status_code == 200
    assert "headline_start" in timeline
    assert "headline_end" in timeline
    assert "weather_start" in timeline
    assert "weather_end" in timeline
    assert "finalize" in timeline
    # Weather must start before headline finishes to prove parallel execution via
    # asyncio.gather.
    assert timeline["weather_start"] <= timeline["headline_end"]
    assert timeline["finalize"] >= max(
        timeline["headline_end"],
        timeline["weather_end"],
    )


@pytest.mark.asyncio
async def test_weather_failure_does_not_abort_section_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headline_calls: list[str] = []
    weather_calls: list[str] = []
    test_slug = SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT

    async def fake_run_section(
        *_args: Any, **_kwargs: Any
    ) -> dict[str, Any] | None:
        return None

    async def fake_load(*args: Any, **kwargs: Any) -> tuple[UUID, dict[str, Any]]:
        del args, kwargs
        return fixed_task_attempt, {
            "state": "running",
            "attempt_id": str(fixed_task_attempt),
            "data": None,
        }

    async def fake_run_headline(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        headline_calls.append("called")

    async def fake_run_weather(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        weather_calls.append("called")
        raise RuntimeError("weather unavailable")

    async def fake_mark_slot_done(*_args: Any, **_kwargs: Any) -> int:
        return 1

    fake_finalize = AsyncMock(return_value=True)
    fake_mark_slot_failed = AsyncMock()

    fixed_task_attempt = uuid4()

    monkeypatch.setattr(orchestrator, "_load_job_attempt_and_slot", fake_load)
    monkeypatch.setitem(orchestrator._SECTION_HANDLERS, test_slug, fake_run_section)
    monkeypatch.setattr(orchestrator, "mark_slot_done", fake_mark_slot_done)
    monkeypatch.setattr(orchestrator, "mark_slot_failed", fake_mark_slot_failed)
    monkeypatch.setattr(orchestrator, "_set_last_stage", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_safety_recommendation_step", AsyncMock())
    monkeypatch.setattr(orchestrator, "_run_headline_summary_step", fake_run_headline)
    monkeypatch.setattr(orchestrator, "evaluate_weather", fake_run_weather)
    monkeypatch.setattr(orchestrator, "maybe_finalize_job", fake_finalize)

    result = await orchestrator.run_section_retry(
        pool=FakePool(WeatherReportConnection(_complete_sections())),
        job_id=uuid4(),
        slug=test_slug,
        expected_slot_attempt_id=fixed_task_attempt,
        settings=MagicMock(),
    )

    assert result.status_code == 200
    assert headline_calls == ["called"]
    assert weather_calls == ["called"]
    assert not fake_mark_slot_failed.called
    fake_finalize.assert_awaited_once()
