from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.analyses.safety._schemas import SafetyLevel, SafetyRecommendation
from src.analyses.schemas import PageKind
from src.analyses.synthesis._overall_schemas import OverallDecision
from src.analyses.synthesis._weather_schemas import WeatherAxis, WeatherReport
from src.analyses.synthesis.overall_recommendation_agent import (
    OVERALL_RECOMMENDATION_SYSTEM_PROMPT,
    OverallInputs,
    evaluate_overall,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.config import Settings


class StubAgent:
    pass


def _recommendation(
    level: SafetyLevel,
    *,
    rationale: str = "No harmful content detected.",
    top_signals: list[str] | None = None,
) -> SafetyRecommendation:
    return SafetyRecommendation(
        level=level,
        rationale=rationale,
        top_signals=top_signals or [],
    )


def _flashpoint(risk_level: RiskLevel) -> FlashpointMatch:
    return FlashpointMatch(
        utterance_id="u1",
        derailment_score=72,
        risk_level=risk_level,
        reasoning="heated exchange",
        context_messages=4,
    )


def _weather(truth: str, relevance: str) -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis(label=truth),
        relevance=WeatherAxis(label=relevance),
        sentiment=WeatherAxis(label="neutral"),
    )


def _inputs(
    *,
    safety_recommendation: SafetyRecommendation | None,
    flashpoint_matches: list[FlashpointMatch] | None = None,
    weather_report: WeatherReport | None = None,
) -> OverallInputs:
    return OverallInputs(
        page_title="Example",
        page_kind=PageKind.ARTICLE,
        safety_recommendation=safety_recommendation,
        flashpoint_matches=flashpoint_matches or [],
        weather_report=weather_report,
    )


async def _evaluate_with_rule_candidate(inputs: OverallInputs, monkeypatch: pytest.MonkeyPatch):
    build_calls: list[tuple[object, type[OverallDecision], str, str | None, str]] = []

    def fake_build_agent(settings, *, output_type, system_prompt, name=None, tier="fast"):
        build_calls.append((settings, output_type, system_prompt, name, tier))
        return StubAgent()

    async def fake_run(_agent, prompt: str):
        payload = json.loads(prompt)
        return SimpleNamespace(
            output=OverallDecision.model_validate(payload["rule_candidate"])
        )

    monkeypatch.setattr(
        "src.analyses.synthesis.overall_recommendation_agent.build_agent",
        fake_build_agent,
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.overall_recommendation_agent.run_vertex_agent_with_retry",
        fake_run,
    )
    settings = Settings()

    result = await evaluate_overall(
        inputs,
        settings,
        job_id=UUID("11111111-1111-1111-1111-111111111111"),
    )

    return result, build_calls


def test_overall_prompt_names_cross_signal_rules() -> None:
    assert "safe or mild safety recommendation => pass" in OVERALL_RECOMMENDATION_SYSTEM_PROMPT
    assert "caution or unsafe safety recommendation => flag" in OVERALL_RECOMMENDATION_SYSTEM_PROMPT
    assert "mild + Heated/Hostile/Dangerous flashpoint => flag" in OVERALL_RECOMMENDATION_SYSTEM_PROMPT
    assert "truth=misleading and relevance=insightful|on_topic => flag" in OVERALL_RECOMMENDATION_SYSTEM_PROMPT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (SafetyLevel.SAFE, "pass"),
        (SafetyLevel.MILD, "pass"),
        (SafetyLevel.CAUTION, "flag"),
        (SafetyLevel.UNSAFE, "flag"),
    ],
)
async def test_safety_level_sets_base_verdict(level, expected, monkeypatch) -> None:
    result, build_calls = await _evaluate_with_rule_candidate(
        _inputs(
            safety_recommendation=_recommendation(
                level,
                top_signals=["human-readable concern"],
            )
        ),
        monkeypatch,
    )

    assert result is not None
    assert result.verdict == expected
    assert result.reason == "human-readable concern"
    assert build_calls[0][1:] == (
        OverallDecision,
        OVERALL_RECOMMENDATION_SYSTEM_PROMPT,
        "vibecheck.overall_recommendation",
        "synthesis",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "risk_level",
    [RiskLevel.HEATED, RiskLevel.HOSTILE, RiskLevel.DANGEROUS],
)
async def test_mild_high_flashpoint_escalates_pass(risk_level, monkeypatch) -> None:
    result, _ = await _evaluate_with_rule_candidate(
        _inputs(
            safety_recommendation=_recommendation(
                SafetyLevel.MILD,
                top_signals=["minor concern"],
            ),
            flashpoint_matches=[_flashpoint(risk_level)],
        ),
        monkeypatch,
    )

    assert result is not None
    assert result.verdict == "flag"
    assert result.reason == f"Conversation flashpoint risk: {risk_level.value}"


@pytest.mark.asyncio
async def test_low_flashpoint_does_not_escalate_mild(monkeypatch) -> None:
    result, _ = await _evaluate_with_rule_candidate(
        _inputs(
            safety_recommendation=_recommendation(
                SafetyLevel.MILD,
                top_signals=["minor concern"],
            ),
            flashpoint_matches=[_flashpoint(RiskLevel.GUARDED)],
        ),
        monkeypatch,
    )

    assert result is not None
    assert result.verdict == "pass"
    assert result.reason == "minor concern"


@pytest.mark.asyncio
async def test_misleading_on_topic_weather_escalates_pass(monkeypatch) -> None:
    result, _ = await _evaluate_with_rule_candidate(
        _inputs(
            safety_recommendation=_recommendation(
                SafetyLevel.SAFE,
                top_signals=["educational context"],
            ),
            weather_report=_weather("misleading", "on_topic"),
        ),
        monkeypatch,
    )

    assert result is not None
    assert result.verdict == "flag"
    assert result.reason == "Misleading framing in on-topic discussion"


@pytest.mark.asyncio
async def test_off_topic_misleading_weather_does_not_escalate_pass(monkeypatch) -> None:
    result, _ = await _evaluate_with_rule_candidate(
        _inputs(
            safety_recommendation=_recommendation(
                SafetyLevel.SAFE,
                top_signals=["educational context"],
            ),
            weather_report=_weather("misleading", "off_topic"),
        ),
        monkeypatch,
    )

    assert result is not None
    assert result.verdict == "pass"
    assert result.reason == "educational context"


@pytest.mark.asyncio
async def test_raw_score_signal_suppressed_when_rationale_flags_false_positive(
    monkeypatch,
) -> None:
    result, _ = await _evaluate_with_rule_candidate(
        _inputs(
            safety_recommendation=_recommendation(
                SafetyLevel.CAUTION,
                top_signals=["text: Legal 1.0"],
                rationale=(
                    "Legal score is judged to be false positive, but "
                    "repeated low-severity toxicity remains."
                ),
            )
        ),
        monkeypatch,
    )

    assert result is not None
    assert result.verdict == "flag"
    assert result.reason == "repeated low-severity toxicity remains"


@pytest.mark.asyncio
async def test_evaluate_overall_bypasses_agent_without_safety_signal(
    monkeypatch,
) -> None:
    def fail_build_agent(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("agent should be bypassed")

    monkeypatch.setattr(
        "src.analyses.synthesis.overall_recommendation_agent.build_agent",
        fail_build_agent,
    )

    result = await evaluate_overall(
        _inputs(safety_recommendation=None),
        Settings(),
        job_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    assert result is None
