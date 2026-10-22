from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from src.url_content_scan.schemas import HeadlineSummary, PageKind


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
        trends_oppositions=None,
        highlights=None,
        page_title=None,
        page_kind=PageKind.OTHER,
        unavailable_inputs=[],
    )


def _make_non_empty_trends():
    from src.url_content_scan.opinions_schemas import ClaimTrend, TrendsOppositionsReport

    return TrendsOppositionsReport(
        trends=[ClaimTrend(label="safety", cluster_texts=["a"], summary="about safety")],
        oppositions=[],
        input_cluster_count=1,
        skipped_for_cap=0,
    )


def _make_non_empty_highlights():
    from src.url_content_scan.claims_schemas import DedupedClaim
    from src.url_content_scan.opinions_schemas import (
        HighlightsThresholdInfo,
        OpinionsHighlight,
        OpinionsHighlightsReport,
    )

    return OpinionsHighlightsReport(
        highlights=[
            OpinionsHighlight(
                cluster=DedupedClaim(
                    canonical_text="Key claim",
                    occurrence_count=3,
                    author_count=2,
                    utterance_ids=["u1"],
                    representative_authors=["author1"],
                ),
                crossed_scaled_threshold=True,
            )
        ],
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


def test_headline_inputs_accepts_trends_and_highlights():
    inputs = _empty_inputs()
    assert inputs.trends_oppositions is None
    assert inputs.highlights is None


def test_headline_all_inputs_clear_treats_trends_as_signal():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(_empty_inputs(), trends_oppositions=_make_non_empty_trends())
    assert all_inputs_clear(inputs) is False


def test_headline_all_inputs_clear_treats_highlights_as_signal():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear

    inputs = replace(_empty_inputs(), highlights=_make_non_empty_highlights())
    assert all_inputs_clear(inputs) is False


def test_headline_all_inputs_clear_treats_empty_trends_as_clear():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear
    from src.url_content_scan.opinions_schemas import TrendsOppositionsReport

    empty_trends = TrendsOppositionsReport(
        trends=[], oppositions=[], input_cluster_count=0, skipped_for_cap=0
    )
    inputs = replace(_empty_inputs(), trends_oppositions=empty_trends)
    assert all_inputs_clear(inputs) is True


def test_headline_all_inputs_clear_treats_empty_highlights_as_clear():
    from src.url_content_scan.analyses.synthesis.headline_summary_agent import all_inputs_clear
    from src.url_content_scan.opinions_schemas import (
        HighlightsThresholdInfo,
        OpinionsHighlightsReport,
    )

    empty_highlights = OpinionsHighlightsReport(
        highlights=[],
        threshold=HighlightsThresholdInfo(
            total_authors=0,
            total_utterances=0,
            min_authors_required=2,
            min_occurrences_required=3,
        ),
        fallback_engaged=False,
        floor_eligible_count=0,
        total_input_count=0,
    )
    inputs = replace(_empty_inputs(), highlights=empty_highlights)
    assert all_inputs_clear(inputs) is True


@pytest.mark.asyncio
async def test_run_headline_summary_includes_trends_in_serialized_payload(monkeypatch):
    import json
    from types import SimpleNamespace

    from src.url_content_scan.analyses.synthesis import headline_summary_agent as module
    from src.url_content_scan.safety_schemas import SafetyLevel, SafetyRecommendation

    stub_calls: list[dict] = []

    class StubAgent:
        async def run(self, user_prompt: str, **kwargs: object) -> SimpleNamespace:
            stub_calls.append({"user_prompt": user_prompt})
            return SimpleNamespace(output=HeadlineSummary(text="With trends", kind="synthesized"))

    monkeypatch.setattr(module, "headline_summary_agent", StubAgent())
    monkeypatch.setattr(module, "_default_headline_model", lambda settings: "model")

    inputs = replace(
        _empty_inputs(),
        safety_recommendation=SafetyRecommendation(
            level=SafetyLevel.UNSAFE,
            rationale="risk",
            top_signals=["risk signal"],
        ),
        trends_oppositions=_make_non_empty_trends(),
        highlights=_make_non_empty_highlights(),
    )

    result = await module.run_headline_summary(
        inputs,
        settings=object(),
        job_id=UUID("66666666-6666-6666-6666-666666666666"),
    )

    assert result.kind == "synthesized"
    assert len(stub_calls) == 1
    payload = json.loads(stub_calls[0]["user_prompt"])
    assert payload["trends_oppositions"] is not None
    assert payload["highlights"] is not None
