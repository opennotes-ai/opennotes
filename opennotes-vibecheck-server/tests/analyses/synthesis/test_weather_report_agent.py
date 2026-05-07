from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimsReport, DedupedClaim
from src.analyses.opinions._highlights_schemas import (
    HighlightsThresholdInfo,
    OpinionsHighlight,
    OpinionsHighlightsReport,
)
from src.analyses.opinions._schemas import SentimentScore, SentimentStatsReport, SubjectiveClaim
from src.analyses.opinions._trends_schemas import ClaimTrend, TrendsOppositionsReport
from src.analyses.schemas import PageKind
from src.analyses.synthesis._weather_schemas import (
    RelevanceLabel,
    TruthLabel,
    WeatherAxis,
    WeatherReport,
)
from src.analyses.synthesis.weather_report_agent import (
    WEATHER_SYSTEM_PROMPT,
    WeatherInputs,
    evaluate_weather,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone._scd_schemas import SCDReport
from src.config import Settings


class StubAgent:
    def __init__(self, output: WeatherReport, *, provider_details: Any | None = None) -> None:
        self.output = output
        self.provider_details = provider_details
        self.prompts: list[str] = []

    async def run(self, user_prompt: str):
        self.prompts.append(user_prompt)
        response = SimpleNamespace(provider_details=self.provider_details)
        return SimpleNamespace(output=self.output, response=response)


def _claims_report(*, include_claims: bool = False) -> ClaimsReport:
    if not include_claims:
        return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)
    return ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text="A treatment is being discussed.",
                occurrence_count=1,
                author_count=1,
                utterance_ids=["u1"],
                representative_authors=["author"],
            )
        ],
        total_claims=1,
        total_unique=1,
    )


def _highlights(*, include_highlights: bool = False) -> OpinionsHighlightsReport:
    return OpinionsHighlightsReport(
        highlights=[
            OpinionsHighlight(
                cluster=DedupedClaim(
                    canonical_text="treatment lowered anxiety",
                    occurrence_count=4,
                    author_count=3,
                    utterance_ids=["u1", "u2"],
                    representative_authors=["author"],
                ),
                crossed_scaled_threshold=True,
            )
        ]
        if include_highlights
        else [],
        threshold=HighlightsThresholdInfo(
            total_authors=3,
            total_utterances=3,
            min_authors_required=2,
            min_occurrences_required=2,
        ),
        fallback_engaged=False,
        floor_eligible_count=3,
        total_input_count=3,
    )


def _trends(*, include_trends: bool = False) -> TrendsOppositionsReport:
    return TrendsOppositionsReport(
        trends=[
            ClaimTrend(
                label="same anecdote repeated",
                cluster_texts=[
                    "I got better after using this routine",
                    "I'm not the only one who noticed this",
                ],
                summary="Recurring self-reported pattern.",
            )
        ]
        if include_trends
        else [],
        oppositions=[],
        input_cluster_count=0 if not include_trends else 1,
        skipped_for_cap=0,
    )


def _sentiment(*, positive: float, negative: float) -> SentimentStatsReport:
    neutral = max(0.0, 100.0 - positive - negative)
    per_utterance = (
        [SentimentScore(utterance_id="u1", label="positive", valence=0.6)]
        if positive or negative
        else []
    )
    return SentimentStatsReport(
        per_utterance=per_utterance,
        positive_pct=positive,
        negative_pct=negative,
        neutral_pct=neutral,
        mean_valence=0.2 if positive else -0.1 if negative else 0.0,
    )


def _flashpoint(*, score: int = 40, risk_level: RiskLevel = RiskLevel.LOW_RISK) -> FlashpointMatch:
    return FlashpointMatch(
        utterance_id="u1",
        derailment_score=score,
        risk_level=risk_level,
        reasoning="sample",
        context_messages=2,
    )


def _scd() -> SCDReport:
    return SCDReport(
        narrative="A short sample tone arc.",
        speaker_arcs=[],
        summary="A short sample tone arc.",
        insufficient_conversation=False,
    )


def _subjective() -> list[SubjectiveClaim]:
    return [
        SubjectiveClaim(
            claim_text="This felt safer after trying the routine.",
            utterance_id="u1",
            stance="supports",
        )
    ]


def _report(
    *,
    truth: TruthLabel = "sourced",
    relevance: RelevanceLabel = "on_topic",
    sentiment_label: str = "supportive",
    logprob: float | None = None,
) -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis(label=truth, logprob=logprob),
        relevance=WeatherAxis(label=relevance, logprob=logprob),
        sentiment=WeatherAxis(label=sentiment_label, logprob=logprob),
    )


SELF_REPORTED_TRANSCRIPT = (
    "I was in this situation for two months. "
    "This is my personal recovery routine and it helped me feel calmer."
)
MIXED_TRANSCRIPT = (
    "I stopped waking up at 3am after reading this peer-shared "
    "sleep-study summary (https://example.edu/sleepstudy), and in my "
    "own case it also worked within a week."
)


def _inputs(*, page_title: str = "Example page", transcript_excerpt: str) -> WeatherInputs:
    return WeatherInputs(
        page_title=page_title,
        page_kind=PageKind.FORUM_THREAD,
        transcript_excerpt=transcript_excerpt,
        claims_report=_claims_report(include_claims=True),
        highlights=_highlights(include_highlights=False),
        trends_oppositions=_trends(include_trends=True),
        sentiment_stats=_sentiment(positive=30.0, negative=0.0),
        subjective_claims=_subjective(),
        flashpoint_matches=[_flashpoint()],
        scd=_scd(),
        unavailable_inputs=["trends_oppositions", "highlights"],
    )


async def test_evaluate_weather_builds_weather_agent(monkeypatch):
    agent = StubAgent(_report(truth="self_reported"))
    settings = Settings()
    build_calls: list[tuple[Any, ...]] = []

    def fake_build_agent(settings, *, output_type, system_prompt, name=None, tier="fast", **kwargs):
        build_calls.append((settings, output_type, system_prompt, name, tier, kwargs))
        return agent

    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        fake_build_agent,
    )

    result = await evaluate_weather(
        _inputs(transcript_excerpt="I tried this and felt okay."),
        settings=settings,
        job_id=UUID(int=1),
    )

    assert result.truth.label == "self_reported"
    assert build_calls == [
        (
            settings,
            WeatherReport,
            WEATHER_SYSTEM_PROMPT,
            "vibecheck.weather_report",
            "synthesis",
            {"logprobs": True},
        )
    ]


async def test_evaluate_weather_serializes_enriched_inputs(monkeypatch):
    agent = StubAgent(_report(truth="self_reported", relevance="on_topic"))
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    inputs = WeatherInputs(
        page_title="Layered page",
        page_kind=PageKind.ARTICLE,
        transcript_excerpt="A long transcript excerpt with mixed sources and experiences.",
        claims_report=_claims_report(include_claims=True),
        highlights=_highlights(include_highlights=True),
        trends_oppositions=_trends(include_trends=True),
        sentiment_stats=_sentiment(positive=40.0, negative=12.0),
        subjective_claims=_subjective(),
        flashpoint_matches=[_flashpoint(score=82, risk_level=RiskLevel.HEATED)],
        scd=_scd(),
        unavailable_inputs=["flashpoint_matches"],
    )

    await evaluate_weather(inputs=inputs, settings=Settings(), job_id=uuid4())

    payload = json.loads(agent.prompts[0])
    assert payload["page_title"] == "Layered page"
    assert payload["page_kind"] == "article"
    assert (
        payload["transcript_excerpt"]
        == "A long transcript excerpt with mixed sources and experiences."
    )
    assert payload["claims_report"]["total_claims"] == 1
    assert payload["highlights"]["highlights"][0]["cluster"]["canonical_text"] == "treatment lowered anxiety"
    assert payload["flashpoint_matches"][0]["derailment_score"] == 82
    assert payload["sentiment_stats"]["positive_pct"] == 40.0
    assert payload["sentiment_stats"]["negative_pct"] == 12.0
    assert payload["scd"]["summary"] == "A short sample tone arc."
    assert payload["trends_oppositions"]["input_cluster_count"] == 1
    assert payload["unavailable_inputs"] == ["flashpoint_matches"]


async def test_evaluate_weather_serializes_missing_optional_inputs_as_null(monkeypatch):
    agent = StubAgent(_report())
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    inputs = WeatherInputs(
        page_title="Null inputs page",
        page_kind=PageKind.FORUM_THREAD,
        transcript_excerpt="No claims, no highlights, no trends, no sentiment.",
        claims_report=None,
        highlights=None,
        trends_oppositions=None,
        sentiment_stats=None,
        subjective_claims=[],
        flashpoint_matches=[],
        scd=None,
        unavailable_inputs=["claims_report", "highlights"],
    )
    await evaluate_weather(inputs=inputs, settings=Settings(), job_id=UUID(int=6))

    payload = json.loads(agent.prompts[0])
    assert payload["claims_report"] is None
    assert payload["highlights"] is None
    assert payload["trends_oppositions"] is None
    assert payload["sentiment_stats"] is None
    assert payload["scd"] is None


@pytest.mark.parametrize("transcript", [SELF_REPORTED_TRANSCRIPT, MIXED_TRANSCRIPT])
async def test_eval_weather_prompt_and_payload_preserve_self_reporting_inputs(monkeypatch, transcript: str):
    agent = StubAgent(_report(truth="self_reported"))
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await evaluate_weather(
        _inputs(transcript_excerpt=transcript),
        settings=Settings(),
        job_id=UUID(int=2),
    )

    payload = json.loads(agent.prompts[0])
    assert transcript in payload["transcript_excerpt"]
    assert "self_reported" in WEATHER_SYSTEM_PROMPT
    assert "Self-reporting fixture" in WEATHER_SYSTEM_PROMPT
    assert result.truth.label == "self_reported"


async def test_evaluate_weather_missing_logprobs_returns_none_and_empty_alternatives(monkeypatch):
    report = WeatherReport(
        truth=WeatherAxis(label="self_reported", logprob=0.93),
        relevance=WeatherAxis(label="on_topic", logprob=0.91),
        sentiment=WeatherAxis(label="supportive", logprob=0.75),
    )
    agent = StubAgent(report, provider_details=None)
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await evaluate_weather(
        _inputs(transcript_excerpt="I am reporting experience."),
        settings=Settings(),
        job_id=UUID(int=3),
    )

    assert result.truth.logprob is None
    assert result.relevance.logprob is None
    assert result.sentiment.logprob is None
    assert result.truth.alternatives == []
    assert result.relevance.alternatives == []
    assert result.sentiment.alternatives == []


async def test_evaluate_weather_applies_output_level_avg_logprob(monkeypatch):
    agent = StubAgent(
        _report(truth="self_reported"),
        provider_details={
            "logprobs": {"token_count": 42},
            "avg_logprobs": -0.12,
        },
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await evaluate_weather(
        _inputs(transcript_excerpt="I am reporting experience."),
        settings=Settings(),
        job_id=UUID(int=4),
    )

    assert result.truth.logprob == -0.12
    assert result.relevance.logprob == -0.12
    assert result.sentiment.logprob == -0.12
    assert result.truth.alternatives == []
    assert result.relevance.alternatives == []
    assert result.sentiment.alternatives == []


async def test_evaluate_weather_keeps_alternatives_empty_even_with_top_candidates(monkeypatch):
    agent = StubAgent(
        _report(truth="self_reported"),
        provider_details={
            "logprobs": {
                "top_logprobs": [
                    {"token": "self_reported", "logprob": -0.09},
                    {"token": "sourced", "logprob": -1.2},
                ],
            },
            "avg_logprobs": -0.55,
        },
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await evaluate_weather(
        _inputs(transcript_excerpt="I am reporting experience."),
        settings=Settings(),
        job_id=UUID(int=5),
    )

    assert result.truth.alternatives == []
    assert result.relevance.alternatives == []
    assert result.sentiment.alternatives == []
    assert result.truth.logprob == -0.55


def test_weather_system_prompt_cites_lineage_and_teaches_few_shot_rules():
    lowered = WEATHER_SYSTEM_PROMPT.lower()
    assert "potter 1996" in lowered
    assert "sacks 1972" in lowered
    assert "fisher 1984" in lowered
    assert "goffman 1974" in lowered
    assert "gumperz 1982" in lowered
    assert "biber & finegan 1989" in lowered
    assert "dubois 2007" in lowered
    assert "brown & levinson 1987" in lowered
    assert "self-reporting fixture" in lowered
    assert "mixed sourced + self-reported fixture" in lowered
    assert '"truth": {"label": "self_reported"}' in lowered
