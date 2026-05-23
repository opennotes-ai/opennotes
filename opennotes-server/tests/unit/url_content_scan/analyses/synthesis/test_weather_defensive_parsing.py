"""Tests for defensive WeatherReport parsing in SidebarPayload and recent_query paths.

PR513 salvage: SidebarPayload must not break when weather_report has schema drift.
PR512 salvage: recent_query must defensively parse old WeatherReport rows.
"""

from __future__ import annotations

import pytest

from src.url_content_scan.analyses.synthesis.weather_report_schemas import (
    OverallDecision,
    OverallVerdict,
    WeatherAxis,
    WeatherReport,
)


def _make_valid_weather_report_dict() -> dict:
    return {
        "truth": {"label": "factual_claims", "logprob": None, "alternatives": []},
        "relevance": {"label": "on_topic", "logprob": None, "alternatives": []},
        "sentiment": {"label": "neutral", "logprob": None, "alternatives": []},
    }


def _make_valid_overall_decision_dict() -> dict:
    return {
        "verdict": "pass",
        "reason": "No issues found",
    }


def test_weather_report_round_trips_via_model_validate():
    data = _make_valid_weather_report_dict()
    report = WeatherReport.model_validate(data)
    assert report.truth.label == "factual_claims"
    assert report.relevance.label == "on_topic"
    assert report.sentiment.label == "neutral"
    assert report.truth.alternatives == []


def test_overall_decision_round_trips():
    data = _make_valid_overall_decision_dict()
    decision = OverallDecision.model_validate(data)
    assert decision.verdict == OverallVerdict.PASS
    assert decision.reason == "No issues found"


def test_sidebar_payload_weather_and_overall_optional():
    import pendulum

    from src.url_content_scan.claims_schemas import ClaimsReport
    from src.url_content_scan.opinions_schemas import OpinionsReport, SentimentStatsReport
    from src.url_content_scan.schemas import (
        FactsClaimsSection,
        OpinionsSection,
        SafetySection,
        SidebarPayload,
        ToneDynamicsSection,
    )
    from src.url_content_scan.tone_schemas import SCDReport

    scd = SCDReport(
        narrative="",
        speaker_arcs=[],
        summary="",
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=True,
    )
    claims = ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)
    sentiment = SentimentStatsReport(
        per_utterance=[], positive_pct=0, negative_pct=0, neutral_pct=0, mean_valence=0
    )

    payload = SidebarPayload(
        scraped_at=pendulum.now("UTC"),
        safety=SafetySection(),
        tone_dynamics=ToneDynamicsSection(scd=scd),
        facts_claims=FactsClaimsSection(claims_report=claims),
        opinions_sentiments=OpinionsSection(
            opinions_report=OpinionsReport(sentiment_stats=sentiment, subjective_claims=[])
        ),
    )

    assert payload.weather_report is None
    assert payload.overall_recommendation is None


def test_sidebar_payload_accepts_weather_and_overall():
    import pendulum

    from src.url_content_scan.claims_schemas import ClaimsReport
    from src.url_content_scan.opinions_schemas import OpinionsReport, SentimentStatsReport
    from src.url_content_scan.schemas import (
        FactsClaimsSection,
        OpinionsSection,
        SafetySection,
        SidebarPayload,
        ToneDynamicsSection,
    )
    from src.url_content_scan.tone_schemas import SCDReport

    scd = SCDReport(
        narrative="",
        speaker_arcs=[],
        summary="",
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=True,
    )
    claims = ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)
    sentiment = SentimentStatsReport(
        per_utterance=[], positive_pct=0, negative_pct=0, neutral_pct=0, mean_valence=0
    )

    weather = WeatherReport(
        truth=WeatherAxis(label="sourced", alternatives=[]),
        relevance=WeatherAxis(label="insightful", alternatives=[]),
        sentiment=WeatherAxis(label="supportive", alternatives=[]),
    )
    overall = OverallDecision(verdict=OverallVerdict.PASS, reason="clean")

    payload = SidebarPayload(
        scraped_at=pendulum.now("UTC"),
        safety=SafetySection(),
        tone_dynamics=ToneDynamicsSection(scd=scd),
        facts_claims=FactsClaimsSection(claims_report=claims),
        opinions_sentiments=OpinionsSection(
            opinions_report=OpinionsReport(sentiment_stats=sentiment, subjective_claims=[])
        ),
        weather_report=weather,
        overall_recommendation=overall,
    )

    assert payload.weather_report is not None
    assert payload.weather_report.truth.label == "sourced"
    assert payload.overall_recommendation is not None
    assert payload.overall_recommendation.verdict == OverallVerdict.PASS


def test_sidebar_payload_weather_drift_does_not_raise():
    """PR513: drifted/unknown weather_report label should not blow up SidebarPayload."""
    from src.url_content_scan.schemas import SidebarPayload

    drift_payload = {
        "scraped_at": "2025-01-01T00:00:00+00:00",
        "cached": False,
        "safety": {"harmful_content_matches": [], "recommendation": None},
        "tone_dynamics": {
            "scd": {
                "narrative": "",
                "speaker_arcs": [],
                "summary": "",
                "tone_labels": [],
                "per_speaker_notes": {},
                "insufficient_conversation": True,
            },
            "flashpoint_matches": [],
        },
        "facts_claims": {
            "claims_report": {"deduped_claims": [], "total_claims": 0, "total_unique": 0},
            "known_misinformation": [],
        },
        "opinions_sentiments": {
            "opinions_report": {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0,
                    "negative_pct": 0,
                    "neutral_pct": 0,
                    "mean_valence": 0,
                },
                "subjective_claims": [],
            }
        },
        "weather_report": {
            "truth": {"label": "UNKNOWN_FUTURE_LABEL", "logprob": None, "alternatives": []},
            "relevance": {"label": "on_topic", "logprob": None, "alternatives": []},
            "sentiment": {"label": "neutral", "logprob": None, "alternatives": []},
        },
    }

    payload = SidebarPayload.model_validate(drift_payload)
    assert payload.weather_report is None


def test_weather_report_with_unknown_truth_label_fails_strict_validation():
    """WeatherReport itself rejects unknown truth labels (strict Literal)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WeatherReport.model_validate(
            {
                "truth": {"label": "UNKNOWN", "logprob": None, "alternatives": []},
                "relevance": {"label": "on_topic", "logprob": None, "alternatives": []},
                "sentiment": {"label": "neutral", "logprob": None, "alternatives": []},
            }
        )
