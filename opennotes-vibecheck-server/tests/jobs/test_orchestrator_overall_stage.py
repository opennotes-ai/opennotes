from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from src.analyses.synthesis._overall_schemas import OverallDecision, OverallVerdict
from src.jobs import orchestrator
from tests.jobs.test_orchestrator_weather_stage import FakePool, _complete_sections


class OverallDecisionConnection:
    def __init__(
        self,
        sections: dict[str, Any],
        *,
        safety_recommendation: Any = None,
        weather_report: Any = None,
        page_title: str | None = None,
        page_kind: str | None = "other",
        attempt_matches: bool = True,
        fail_execute: bool = False,
    ) -> None:
        self.sections = sections
        self.safety_recommendation = safety_recommendation
        self.weather_report = weather_report
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
            "weather_report": self.weather_report,
            "page_title": self.page_title,
            "page_kind": self.page_kind,
        }

    async def execute(
        self,
        query: str,
        job_id: UUID,
        overall_json: str,
        task_attempt: UUID,
    ) -> str:
        if self.fail_execute:
            raise RuntimeError("overall column unavailable")
        self.written = {
            "query": query,
            "job_id": job_id,
            "overall_json": overall_json,
            "task_attempt": task_attempt,
        }
        return "UPDATE 1" if self.attempt_matches else "UPDATE 0"


def _safety_json() -> dict[str, Any]:
    return {
        "level": "mild",
        "rationale": "Minor concern.",
        "top_signals": ["minor concern"],
        "unavailable_inputs": [],
    }


def _weather_json() -> dict[str, Any]:
    return {
        "truth": {"label": "sourced", "alternatives": [], "logprob": None},
        "relevance": {"label": "on_topic", "alternatives": [], "logprob": None},
        "sentiment": {"label": "neutral", "alternatives": [], "logprob": None},
    }


@pytest.mark.asyncio
async def test_overall_recommendation_step_writes_decision_when_agent_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_inputs: list[Any] = []

    async def fake_evaluate_overall(inputs, settings, *, job_id):
        del settings, job_id
        captured_inputs.append(inputs)
        return OverallDecision(verdict=OverallVerdict.PASS, reason="Server synthesis")

    monkeypatch.setattr(orchestrator, "evaluate_overall", fake_evaluate_overall)
    conn = OverallDecisionConnection(
        _complete_sections(),
        safety_recommendation=_safety_json(),
        weather_report=_weather_json(),
        page_title="Example",
        page_kind="article",
    )

    job_id = uuid4()
    task_attempt = uuid4()
    await orchestrator._run_overall_recommendation_step(
        FakePool(conn),
        job_id,
        task_attempt,
        MagicMock(),
    )

    assert captured_inputs
    assert captured_inputs[0].page_title == "Example"
    assert captured_inputs[0].page_kind.value == "article"
    assert captured_inputs[0].safety_recommendation.level == "mild"
    assert captured_inputs[0].weather_report is not None
    assert conn.written is not None
    assert "overall_decision = $2::jsonb" in conn.written["query"]
    assert conn.written["job_id"] == job_id
    assert conn.written["task_attempt"] == task_attempt
    parsed = json.loads(conn.written["overall_json"])
    assert parsed == {"verdict": "pass", "reason": "Server synthesis"}


@pytest.mark.asyncio
async def test_overall_recommendation_step_leaves_column_null_when_agent_bypasses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_evaluate_overall(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    monkeypatch.setattr(orchestrator, "evaluate_overall", fake_evaluate_overall)
    conn = OverallDecisionConnection(_complete_sections(), safety_recommendation=None)

    await orchestrator._run_overall_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        MagicMock(),
    )

    assert conn.written is None


@pytest.mark.asyncio
async def test_overall_recommendation_step_swallow_agent_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_evaluate_overall(*args: Any, **kwargs: Any) -> OverallDecision:
        del args, kwargs
        raise RuntimeError("overall model unavailable")

    monkeypatch.setattr(orchestrator, "evaluate_overall", fake_evaluate_overall)
    conn = OverallDecisionConnection(_complete_sections(), safety_recommendation=_safety_json())

    await orchestrator._run_overall_recommendation_step(
        FakePool(conn),
        uuid4(),
        uuid4(),
        MagicMock(),
    )

    assert conn.written is None
