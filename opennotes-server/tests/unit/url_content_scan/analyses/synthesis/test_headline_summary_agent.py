from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.url_content_scan.claims_schemas import ClaimsReport
from src.url_content_scan.opinions_schemas import SentimentScore, SentimentStatsReport
from src.url_content_scan.safety_schemas import SafetyLevel, SafetyRecommendation
from src.url_content_scan.schemas import HeadlineSummary, PageKind
from src.url_content_scan.tone_schemas import SCDReport


class StubAgent:
    def __init__(self, output: HeadlineSummary) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def run(self, user_prompt: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        return SimpleNamespace(output=self.output)


def _empty_inputs():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import HeadlineSummaryInputs

    return HeadlineSummaryInputs(
        safety_recommendation=None,
        harmful_content_matches=[],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        flashpoint_matches=[],
        scd=None,
        claims_report=None,
        known_misinformation=[],
        sentiment_stats=None,
        subjective_claims=[],
        page_title=None,
        page_kind=PageKind.OTHER,
        unavailable_inputs=[],
    )


def _coverage_only_caution() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="partial coverage",
        top_signals=[],
        unavailable_inputs=["web_risk"],
    )


def _real_caution() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="flagged finding",
        top_signals=["flagged harmful-content utterances"],
    )


def _unsafe_signal() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.UNSAFE,
        rationale="unsafe finding",
        top_signals=["web_risk: MALWARE"],
    )


def _insufficient_scd_with_labels() -> SCDReport:
    return SCDReport(
        narrative="",
        speaker_arcs=[],
        summary="insufficient but labeled",
        tone_labels=["heated"],
        per_speaker_notes={},
        insufficient_conversation=True,
    )


def _truly_empty_sentiment() -> SentimentStatsReport:
    return SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=0.0,
        mean_valence=0.0,
    )


@pytest.mark.asyncio
async def test_run_headline_summary_returns_deterministic_stock_phrase_for_all_clear(monkeypatch):
    from src.url_content_scan.analyses.synthesis import headline_summary_agent as module

    exploding_agent = StubAgent(HeadlineSummary(text="unused", kind="synthesized"))

    async def should_not_run(*args, **kwargs):
        raise AssertionError("headline agent should not run on all-clear path")

    exploding_agent.run = should_not_run  # type: ignore[method-assign]
    monkeypatch.setattr(module, "headline_summary_agent", exploding_agent)

    job_id = UUID("11111111-1111-1111-1111-111111111111")

    first = await module.run_headline_summary(_empty_inputs(), settings=object(), job_id=job_id)
    second = await module.run_headline_summary(_empty_inputs(), settings=object(), job_id=job_id)

    assert first == second
    assert first.kind == "stock"
    assert first.text in module._STOCK_PHRASES
    assert first.unavailable_inputs == []


@pytest.mark.asyncio
async def test_run_headline_summary_returns_degraded_stock_phrase_when_coverage_missing(
    monkeypatch,
):
    from src.url_content_scan.analyses.synthesis import headline_summary_agent as module

    exploding_agent = StubAgent(HeadlineSummary(text="unused", kind="synthesized"))

    async def should_not_run(*args, **kwargs):
        raise AssertionError("headline agent should not run on degraded-stock path")

    exploding_agent.run = should_not_run  # type: ignore[method-assign]
    monkeypatch.setattr(module, "headline_summary_agent", exploding_agent)

    inputs = replace(
        _empty_inputs(),
        safety_recommendation=_coverage_only_caution(),
        unavailable_inputs=["web_risk"],
    )

    result = await module.run_headline_summary(
        inputs,
        settings=object(),
        job_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    assert result.kind == "stock"
    assert result.text in module._DEGRADED_STOCK_PHRASES
    assert result.text not in module._STOCK_PHRASES
    assert result.unavailable_inputs == ["web_risk"]


@pytest.mark.asyncio
async def test_run_headline_summary_uses_agent_for_real_signal_and_forces_output_shape(monkeypatch):
    from src.url_content_scan.analyses.synthesis import headline_summary_agent as module

    stub_agent = StubAgent(
        HeadlineSummary(
            text="Model summary",
            kind="stock",
            unavailable_inputs=["model-echo-ignored"],
        )
    )
    monkeypatch.setattr(module, "headline_summary_agent", stub_agent)
    monkeypatch.setattr(module, "_default_headline_model", lambda settings: "vertex-model")

    inputs = replace(
        _empty_inputs(),
        safety_recommendation=_unsafe_signal(),
        sentiment_stats=SentimentStatsReport(
            per_utterance=[SentimentScore(utterance_id="u1", label="neutral", valence=0.0)],
            positive_pct=0.0,
            negative_pct=0.0,
            neutral_pct=100.0,
            mean_valence=0.0,
        ),
        unavailable_inputs=["video_moderation"],
        page_title="Example page",
        page_kind=PageKind.ARTICLE,
    )

    result = await module.run_headline_summary(
        inputs,
        settings=object(),
        job_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    assert result == HeadlineSummary(
        text="Model summary",
        kind="synthesized",
        unavailable_inputs=["video_moderation"],
    )
    assert len(stub_agent.calls) == 1
    call = stub_agent.calls[0]
    assert call["model"] == "vertex-model"
    assert call["instructions"] == module.HEADLINE_SUMMARY_SYSTEM_PROMPT
    payload = json.loads(call["user_prompt"])
    assert payload["page_title"] == "Example page"
    assert payload["page_kind"] == "article"
    assert payload["unavailable_inputs"] == ["video_moderation"]
    assert payload["safety_recommendation"]["level"] == "unsafe"


def test_all_inputs_clear_treats_coverage_only_caution_as_clear():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(
        _empty_inputs(),
        safety_recommendation=_coverage_only_caution(),
        unavailable_inputs=["web_risk"],
    )

    assert all_inputs_clear(inputs) is True


def test_all_inputs_clear_treats_insufficient_scd_with_labels_as_signal():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(_empty_inputs(), scd=_insufficient_scd_with_labels())

    assert all_inputs_clear(inputs) is False


def test_all_inputs_clear_treats_real_caution_signal_as_not_clear():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(_empty_inputs(), safety_recommendation=_real_caution())

    assert all_inputs_clear(inputs) is False


def test_all_inputs_clear_treats_truly_empty_sentiment_as_clear():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(_empty_inputs(), sentiment_stats=_truly_empty_sentiment())

    assert all_inputs_clear(inputs) is True


def test_empty_claims_report_is_not_a_signal():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(
        _empty_inputs(),
        claims_report=ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0),
    )

    assert all_inputs_clear(inputs) is True
