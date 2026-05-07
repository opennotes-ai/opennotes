from __future__ import annotations

import json
from dataclasses import dataclass
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
    WeatherAxisAlternative,
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
    truth: TruthLabel = "sourced",
    relevance: RelevanceLabel = "on_topic",
    sentiment_label: str = "supportive",
    logprob: float | None = None,
) -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis(label=truth, logprob=logprob, alternatives=[WeatherAxisAlternative(label="sourced")]),
        relevance=WeatherAxis(label=relevance, logprob=logprob, alternatives=[WeatherAxisAlternative(label="insightful")]),
        sentiment=WeatherAxis(label=sentiment_label, logprob=logprob, alternatives=[WeatherAxisAlternative(label="neutral")]),
    )


def _inputs(*, page_title: str = "Example page") -> WeatherInputs:
    return WeatherInputs(
        page_title=page_title,
        page_kind=PageKind.FORUM_THREAD,
        transcript_excerpt=(
            "UserA: I tried the supplement and felt better. "
            "I am reporting this from my own experience only."
        ),
        claims_report=_claims_report(include_claims=True),
        highlights=_highlights(include_highlights=False),
        trends_oppositions=_trends(include_trends=True),
        sentiment_stats=_sentiment(positive=30.0, negative=0.0),
        subjective_claims=_subjective(),
        flashpoint_matches=[_flashpoint()],
        scd=_scd(),
        unavailable_inputs=["trends_oppositions", "highlights"],
    )


@dataclass
class SelfReportedFixture:
    transcript_excerpt: str
    expected_truth_label: TruthLabel


SELF_REPORTED_FIXTURES = (
    SelfReportedFixture(
        transcript_excerpt=(
            "I was in this situation for two months. "
            "This is my personal recovery routine and it helped me "
            "feel calmer."
        ),
        expected_truth_label="self_reported",
    ),
)

MIXED_FIXTURES = (
    SelfReportedFixture(
        transcript_excerpt=(
            "I stopped waking up at 3am after reading this peer-shared "
            "sleep-study summary (https://example.edu/sleepstudy), and in my "
            "own case it also worked within a week."
        ),
        expected_truth_label="self_reported",
    ),
)


def _base_report() -> WeatherReport:
    return _report(
        truth="self_reported",
        relevance="on_topic",
        sentiment_label="supportive",
        logprob=0.3,
    )


async def test_evaluate_weather_builds_weather_agent(monkeypatch):
    agent = StubAgent(_base_report())
    build_calls: list[tuple[Any, ...]] = []

    def fake_build_agent(settings, *, output_type, system_prompt, name=None, tier="fast", **kwargs):
        build_calls.append((settings, output_type, system_prompt, name, tier, kwargs))
        return agent

    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        fake_build_agent,
    )
    settings = Settings()

    result = await evaluate_weather(_inputs(), settings=settings, job_id=UUID(int=1))

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
    agent = StubAgent(_base_report())
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    settings = Settings()
    inputs = _inputs(page_title="Layered page")
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

    await evaluate_weather(inputs, settings=settings, job_id=uuid4())

    payload = json.loads(agent.prompts[0])
    assert set(payload.keys()) >= {
        "page_title",
        "page_kind",
        "transcript_excerpt",
        "claims_report",
        "highlights",
        "trends_oppositions",
        "sentiment_stats",
        "subjective_claims",
        "flashpoint_matches",
        "scd",
        "unavailable_inputs",
    }
    assert payload["page_title"] == "Layered page"
    assert payload["page_kind"] == "article"
    assert payload["unavailable_inputs"] == ["flashpoint_matches"]
    assert payload["claims_report"]["total_claims"] == 1
    assert payload["trends_oppositions"]["input_cluster_count"] == 1


@pytest.mark.parametrize(("fixture"), SELF_REPORTED_FIXTURES)
async def test_self_reporting_fixture_is_neutral(monkeypatch, fixture: SelfReportedFixture):
    agent = StubAgent(
        WeatherReport(
            truth=WeatherAxis(label=fixture.expected_truth_label),
            relevance=WeatherAxis(label="on_topic"),
            sentiment=WeatherAxis(label="supportive"),
        )
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    result = await evaluate_weather(
        WeatherInputs(
            page_title="Self-reporting page",
            page_kind=PageKind.BLOG_POST,
            transcript_excerpt=fixture.transcript_excerpt,
            claims_report=_claims_report(include_claims=False),
            highlights=_highlights(),
            trends_oppositions=_trends(),
            sentiment_stats=_sentiment(positive=0.0, negative=0.0),
            subjective_claims=_subjective(),
            flashpoint_matches=[],
            scd=_scd(),
            unavailable_inputs=[],
        ),
        settings=Settings(),
        job_id=UUID(int=2),
    )

    assert result.truth.label == "self_reported"


@pytest.mark.parametrize(("fixture"), MIXED_FIXTURES)
async def test_mixed_fixture_preserves_self_reported_truth(monkeypatch, fixture: SelfReportedFixture):
    agent = StubAgent(
        WeatherReport(
            truth=WeatherAxis(label=fixture.expected_truth_label),
            relevance=WeatherAxis(label="on_topic"),
            sentiment=WeatherAxis(label="supportive"),
        )
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    result = await evaluate_weather(
        WeatherInputs(
            page_title="Mixed evidence page",
            page_kind=PageKind.ARTICLE,
            transcript_excerpt=fixture.transcript_excerpt,
            claims_report=_claims_report(include_claims=True),
            highlights=_highlights(),
            trends_oppositions=_trends(),
            sentiment_stats=_sentiment(positive=60.0, negative=0.0),
            subjective_claims=_subjective(),
            flashpoint_matches=[_flashpoint()],
            scd=_scd(),
            unavailable_inputs=["claims"],
        ),
        settings=Settings(),
        job_id=UUID(int=3),
    )

    assert result.truth.label == "self_reported"


async def test_evaluate_weather_missing_logprobs_returns_none_and_empty_alternatives(monkeypatch):
    report = WeatherReport(
        truth=WeatherAxis(label="self_reported", logprob=0.93, alternatives=[WeatherAxisAlternative(label="mostly_factual", logprob=0.11)]),
        relevance=WeatherAxis(label="on_topic", logprob=0.91, alternatives=[WeatherAxisAlternative(label="insightful", logprob=0.22)]),
        sentiment=WeatherAxis(label="supportive", logprob=0.75, alternatives=[WeatherAxisAlternative(label="neutral", logprob=0.12)]),
    )
    agent = StubAgent(report, provider_details=None)
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await evaluate_weather(_inputs(), settings=Settings(), job_id=UUID(int=4))

    assert result.truth.logprob is None
    assert result.relevance.logprob is None
    assert result.sentiment.logprob is None
    assert result.truth.alternatives == []
    assert result.relevance.alternatives == []
    assert result.sentiment.alternatives == []


async def test_evaluate_weather_applies_output_level_avg_logprob(monkeypatch):
    agent = StubAgent(
        _base_report(),
        provider_details={
            "logprobs": {
                "token_count": 42,
            },
            "avg_logprobs": -0.12,
        },
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.weather_report_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await evaluate_weather(_inputs(), settings=Settings(), job_id=UUID(int=5))

    assert result.truth.logprob == -0.12
    assert result.relevance.logprob == -0.12
    assert result.sentiment.logprob == -0.12


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
    assert '"truth": {"label":' in lowered
