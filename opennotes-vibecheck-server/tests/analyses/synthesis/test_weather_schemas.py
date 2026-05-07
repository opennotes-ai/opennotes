from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.analyses.schemas import SidebarPayload
from src.analyses.synthesis._weather_schemas import (
    RelevanceLabel,
    TruthLabel,
    WeatherAxis,
    WeatherAxisAlternative,
    WeatherReport,
)
from src.main import app


def _empty_sidebar_payload_dict() -> dict[str, object]:
    return {
        "source_url": "https://example.com",
        "scraped_at": datetime.now(UTC).isoformat(),
        "safety": {"harmful_content_matches": []},
        "tone_dynamics": {
            "scd": {
                "summary": "",
                "tone_labels": [],
                "per_speaker_notes": {},
                "insufficient_conversation": True,
            },
            "flashpoint_matches": [],
        },
        "facts_claims": {
            "claims_report": {
                "deduped_claims": [],
                "total_claims": 0,
                "total_unique": 0,
            },
            "known_misinformation": [],
        },
        "opinions_sentiments": {
            "opinions_report": {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 100.0,
                    "mean_valence": 0.0,
                },
                "subjective_claims": [],
            }
        },
    }


def _weather_report() -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis[TruthLabel](
            label="sourced",
            logprob=0.87,
            alternatives=[WeatherAxisAlternative[TruthLabel](label="factual_claims", logprob=0.08)],
        ),
        relevance=WeatherAxis[RelevanceLabel](
            label="insightful",
            logprob=0.8,
            alternatives=[WeatherAxisAlternative[RelevanceLabel](label="on_topic", logprob=0.12)],
        ),
        sentiment=WeatherAxis[str](
            label="supportive",
            logprob=0.92,
            alternatives=[WeatherAxisAlternative[str](label="positive", logprob=0.11)],
        ),
    )


def test_weather_report_accepts_generic_axis_instances():
    report = WeatherReport(
        truth=WeatherAxis[TruthLabel](
            label="sourced",
            alternatives=[WeatherAxisAlternative[TruthLabel](label="first_person")],
        ),
        relevance=WeatherAxis[RelevanceLabel](
            label="insightful",
            alternatives=[WeatherAxisAlternative[RelevanceLabel](label="on_topic")],
        ),
        sentiment=WeatherAxis[str](
            label="supportive",
            alternatives=[WeatherAxisAlternative[str](label="positive")],
        ),
    )
    assert report.truth.label == "sourced"
    assert report.relevance.label == "insightful"
    assert report.sentiment.label == "supportive"


def test_weather_report_round_trips_via_sidebar_payload_validation():
    payload = SidebarPayload.model_validate(
        {
            **_empty_sidebar_payload_dict(),
            "weather_report": _weather_report().model_dump(),
        }
    )
    assert payload.weather_report is not None
    assert payload.weather_report.sentiment.label == "supportive"
    dumped = payload.model_dump()
    assert dumped["weather_report"] is not None
    assert dumped["weather_report"]["truth"]["alternatives"][0]["label"] == "factual_claims"


def test_truth_label_contract_has_five_epistemic_stance_values() -> None:
    assert get_args(TruthLabel) == (
        "sourced",
        "factual_claims",
        "first_person",
        "hearsay",
        "misleading",
    )


def test_weather_report_optional_in_sidebar_payload_is_backward_compatible():
    payload = SidebarPayload.model_validate(_empty_sidebar_payload_dict())
    assert payload.weather_report is None
    assert payload.source_url == "https://example.com"


def test_invalid_truth_label_is_rejected():
    payload = _empty_sidebar_payload_dict()
    payload["weather_report"] = {
        "truth": {
            "label": "unverified",
            "alternatives": [],
        },
        "relevance": {"label": "insightful"},
        "sentiment": {"label": "neutral"},
    }
    with pytest.raises(ValidationError):
        SidebarPayload.model_validate(payload)


def test_weather_axis_defaults_alternatives_to_empty_and_round_trips_as_list():
    axis = WeatherAxis[str](label="any")
    assert axis.alternatives == []
    assert axis.model_dump()["alternatives"] == []


def test_weather_report_json_schema_uses_stable_public_schema_names():
    schema = WeatherReport.model_json_schema()
    defs = schema.get("$defs", {})

    assert set(defs) == {
        "WeatherAxisAlternativeRelevance",
        "WeatherAxisAlternativeSentiment",
        "WeatherAxisAlternativeTruth",
        "WeatherAxisRelevance",
        "WeatherAxisSentiment",
        "WeatherAxisTruth",
    }
    assert all(not name.startswith("WeatherAxisAlternative_Literal") for name in defs)
    assert all(not name.startswith("WeatherAxis_Literal") for name in defs)


def test_openapi_json_stable_weather_axis_schema_names() -> None:
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    schemas: dict[str, object] = schema["components"]["schemas"]

    assert "WeatherAxisTruth" in schemas
    assert "WeatherAxisRelevance" in schemas
    assert "WeatherAxisSentiment" in schemas
    assert "WeatherAxisAlternativeTruth" in schemas
    assert "WeatherAxisAlternativeRelevance" in schemas
    assert "WeatherAxisAlternativeSentiment" in schemas

    assert not any(
        name.startswith(("WeatherAxisAlternative_Literal", "WeatherAxis_Literal"))
        for name in schemas
    )
