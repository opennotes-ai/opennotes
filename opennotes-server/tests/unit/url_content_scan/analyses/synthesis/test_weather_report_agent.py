from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.url_content_scan.analyses.synthesis.weather_report_schemas import (
    WeatherAxis,
    WeatherReport,
)
from src.url_content_scan.schemas import PageKind


def _make_weather_report(truth: str = "factual_claims") -> WeatherReport:
    return WeatherReport(
        truth=WeatherAxis(label=truth, alternatives=[]),
        relevance=WeatherAxis(label="on_topic", alternatives=[]),
        sentiment=WeatherAxis(label="neutral", alternatives=[]),
    )


def _empty_inputs():
    from src.url_content_scan.analyses.synthesis.weather_report_agent import WeatherInputs

    return WeatherInputs(
        page_title="Test page",
        page_kind=PageKind.ARTICLE,
        transcript_excerpt="Some discussion text.",
        claims_report=None,
        highlights=None,
        trends_oppositions=None,
        sentiment_stats=None,
        subjective_claims=[],
        flashpoint_matches=[],
        scd=None,
    )


class StubWeatherAgent:
    def __init__(self, output: WeatherReport) -> None:
        self.output = output
        self.calls: list[dict] = []

    async def run(self, user_prompt: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        return SimpleNamespace(output=self.output)


@pytest.mark.asyncio
async def test_evaluate_weather_returns_weather_report(monkeypatch):
    from src.url_content_scan.analyses.synthesis import weather_report_agent as module

    expected = _make_weather_report("sourced")
    stub = StubWeatherAgent(expected)
    monkeypatch.setattr(module, "weather_report_agent", stub)
    monkeypatch.setattr(module, "_default_weather_model", lambda settings: "stub-model")

    result = await module.evaluate_weather(
        _empty_inputs(),
        settings=object(),
        job_id=UUID("11111111-1111-1111-1111-111111111111"),
    )

    assert isinstance(result, WeatherReport)
    assert result.truth.label == "sourced"
    assert result.relevance.label == "on_topic"
    assert result.sentiment.label == "neutral"
    assert len(stub.calls) == 1


@pytest.mark.asyncio
async def test_evaluate_weather_serializes_inputs_as_json(monkeypatch):
    from src.url_content_scan.analyses.synthesis import weather_report_agent as module

    stub = StubWeatherAgent(_make_weather_report())
    monkeypatch.setattr(module, "weather_report_agent", stub)
    monkeypatch.setattr(module, "_default_weather_model", lambda settings: "stub-model")

    await module.evaluate_weather(
        _empty_inputs(),
        settings=object(),
        job_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    assert len(stub.calls) == 1
    user_prompt = stub.calls[0]["user_prompt"]
    payload = json.loads(user_prompt)
    assert payload["page_title"] == "Test page"
    assert payload["page_kind"] == "article"
    assert payload["transcript_excerpt"] == "Some discussion text."


@pytest.mark.asyncio
async def test_evaluate_weather_passes_trends_and_highlights_in_payload(monkeypatch):
    from src.url_content_scan.analyses.synthesis import weather_report_agent as module

    monkeypatch.setattr(module, "_default_weather_model", lambda settings: "stub-model")
    from src.url_content_scan.claims_schemas import DedupedClaim
    from src.url_content_scan.opinions_schemas import (
        ClaimTrend,
        HighlightsThresholdInfo,
        OpinionsHighlight,
        OpinionsHighlightsReport,
        TrendsOppositionsReport,
    )

    stub = StubWeatherAgent(_make_weather_report())
    monkeypatch.setattr(module, "weather_report_agent", stub)

    trends = TrendsOppositionsReport(
        trends=[ClaimTrend(label="safety", cluster_texts=["a", "b"], summary="about safety")],
        oppositions=[],
        input_cluster_count=2,
        skipped_for_cap=0,
    )
    cluster = DedupedClaim(
        canonical_text="Main claim",
        occurrence_count=3,
        author_count=2,
        utterance_ids=["u1", "u2", "u3"],
        representative_authors=["author1"],
    )
    highlights = OpinionsHighlightsReport(
        highlights=[OpinionsHighlight(cluster=cluster, crossed_scaled_threshold=True)],
        threshold=HighlightsThresholdInfo(
            total_authors=5,
            total_utterances=10,
            min_authors_required=2,
            min_occurrences_required=3,
        ),
        fallback_engaged=False,
        floor_eligible_count=1,
        total_input_count=5,
    )

    inputs = replace(_empty_inputs(), trends_oppositions=trends, highlights=highlights)
    await module.evaluate_weather(
        inputs,
        settings=object(),
        job_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    payload = json.loads(stub.calls[0]["user_prompt"])
    assert payload["trends_oppositions"] is not None
    assert payload["highlights"] is not None
    assert payload["trends_oppositions"]["trends"][0]["label"] == "safety"
