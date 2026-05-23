from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.url_content_scan.analyses.synthesis.weather_report_schemas import (
    OverallDecision,
    OverallVerdict,
    WeatherAxis,
    WeatherReport,
)
from src.url_content_scan.safety_schemas import SafetyLevel, SafetyRecommendation
from src.url_content_scan.schemas import PageKind


def _safe_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.SAFE,
        rationale="No issues found",
        top_signals=["no harmful content detected"],
    )


def _unsafe_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.UNSAFE,
        rationale="Dangerous content",
        top_signals=["malware link detected"],
    )


def _caution_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Some concerns noted",
        top_signals=["mild harmful content"],
    )


def _make_weather_report(
    truth: str = "factual_claims", relevance: str = "on_topic"
) -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis(label=truth, alternatives=[]),
        relevance=WeatherAxis(label=relevance, alternatives=[]),
        sentiment=WeatherAxis(label="neutral", alternatives=[]),
    )


def _base_inputs(*, recommendation: SafetyRecommendation | None = None):
    from src.url_content_scan.analyses.synthesis.overall_recommendation_agent import OverallInputs

    return OverallInputs(
        page_title="Test page",
        page_kind=PageKind.ARTICLE,
        safety_recommendation=recommendation or _safe_recommendation(),
        flashpoint_matches=[],
        weather_report=None,
    )


class StubOverallAgent:
    def __init__(self, output: OverallDecision) -> None:
        self.output = output
        self.calls: list[dict] = []

    async def run(self, user_prompt: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        return SimpleNamespace(output=self.output)


@pytest.mark.asyncio
async def test_evaluate_overall_returns_none_when_no_recommendation(monkeypatch):
    from src.url_content_scan.analyses.synthesis import overall_recommendation_agent as module

    stub = StubOverallAgent(OverallDecision(verdict=OverallVerdict.PASS, reason="safe"))
    monkeypatch.setattr(module, "overall_recommendation_agent", stub)
    monkeypatch.setattr(module, "_default_overall_model", lambda settings: "stub-model")

    inputs_no_rec = module.OverallInputs(
        page_title=None,
        page_kind=PageKind.OTHER,
        safety_recommendation=None,
        flashpoint_matches=[],
        weather_report=None,
    )
    result = await module.evaluate_overall(
        inputs_no_rec,
        settings=object(),
        job_id=UUID("11111111-1111-1111-1111-111111111111"),
    )

    assert result is None
    assert len(stub.calls) == 0


@pytest.mark.asyncio
async def test_evaluate_overall_returns_pass_for_safe_recommendation(monkeypatch):
    from src.url_content_scan.analyses.synthesis import overall_recommendation_agent as module

    stub = StubOverallAgent(
        OverallDecision(verdict=OverallVerdict.PASS, reason="No harmful content detected")
    )
    monkeypatch.setattr(module, "overall_recommendation_agent", stub)
    monkeypatch.setattr(module, "_default_overall_model", lambda settings: "stub-model")

    result = await module.evaluate_overall(
        _base_inputs(recommendation=_safe_recommendation()),
        settings=object(),
        job_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    assert result is not None
    assert result.verdict == OverallVerdict.PASS


@pytest.mark.asyncio
async def test_evaluate_overall_returns_flag_for_unsafe_recommendation(monkeypatch):
    from src.url_content_scan.analyses.synthesis import overall_recommendation_agent as module

    stub = StubOverallAgent(
        OverallDecision(verdict=OverallVerdict.FLAG, reason="malware link detected")
    )
    monkeypatch.setattr(module, "overall_recommendation_agent", stub)
    monkeypatch.setattr(module, "_default_overall_model", lambda settings: "stub-model")

    result = await module.evaluate_overall(
        _base_inputs(recommendation=_unsafe_recommendation()),
        settings=object(),
        job_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    assert result is not None
    assert result.verdict == OverallVerdict.FLAG


@pytest.mark.asyncio
async def test_evaluate_overall_rule_candidate_never_downgrades_flag(monkeypatch):
    from src.url_content_scan.analyses.synthesis import overall_recommendation_agent as module

    agent_returns_pass = OverallDecision(verdict=OverallVerdict.PASS, reason="agent says pass")
    stub = StubOverallAgent(agent_returns_pass)
    monkeypatch.setattr(module, "overall_recommendation_agent", stub)
    monkeypatch.setattr(module, "_default_overall_model", lambda settings: "stub-model")

    result = await module.evaluate_overall(
        _base_inputs(recommendation=_unsafe_recommendation()),
        settings=object(),
        job_id=UUID("44444444-4444-4444-4444-444444444444"),
    )

    assert result is not None
    assert result.verdict == OverallVerdict.FLAG


@pytest.mark.asyncio
async def test_evaluate_overall_serializes_inputs_including_weather(monkeypatch):
    from src.url_content_scan.analyses.synthesis import overall_recommendation_agent as module

    stub = StubOverallAgent(OverallDecision(verdict=OverallVerdict.PASS, reason="fine"))
    monkeypatch.setattr(module, "overall_recommendation_agent", stub)
    monkeypatch.setattr(module, "_default_overall_model", lambda settings: "stub-model")

    weather = _make_weather_report("sourced", "insightful")
    from src.url_content_scan.analyses.synthesis.overall_recommendation_agent import OverallInputs

    inputs = OverallInputs(
        page_title="Weather test",
        page_kind=PageKind.FORUM_THREAD,
        safety_recommendation=_safe_recommendation(),
        flashpoint_matches=[],
        weather_report=weather,
    )

    await module.evaluate_overall(
        inputs,
        settings=object(),
        job_id=UUID("55555555-5555-5555-5555-555555555555"),
    )

    assert len(stub.calls) == 1
    payload = json.loads(stub.calls[0]["user_prompt"])
    assert payload["weather_report"] is not None
    assert payload["weather_report"]["truth"]["label"] == "sourced"
    assert payload["page_title"] == "Weather test"


def test_rule_candidate_flags_misleading_on_topic():
    from src.url_content_scan.analyses.synthesis.overall_recommendation_agent import (
        OverallInputs,
        _rule_candidate,
    )

    weather = _make_weather_report("misleading", "on_topic")
    inputs = OverallInputs(
        page_title=None,
        page_kind=PageKind.OTHER,
        safety_recommendation=SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="",
            top_signals=["no harmful content"],
        ),
        flashpoint_matches=[],
        weather_report=weather,
    )

    candidate = _rule_candidate(inputs)
    assert candidate is not None
    assert candidate.verdict == OverallVerdict.FLAG


def test_rule_candidate_passes_sourced_on_topic():
    from src.url_content_scan.analyses.synthesis.overall_recommendation_agent import (
        OverallInputs,
        _rule_candidate,
    )

    weather = _make_weather_report("sourced", "on_topic")
    inputs = OverallInputs(
        page_title=None,
        page_kind=PageKind.OTHER,
        safety_recommendation=SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="",
            top_signals=["no harmful content"],
        ),
        flashpoint_matches=[],
        weather_report=weather,
    )

    candidate = _rule_candidate(inputs)
    assert candidate is not None
    assert candidate.verdict == OverallVerdict.PASS
