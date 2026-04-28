from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimsReport, DedupedClaim
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import (
    SentimentScore,
    SentimentStatsReport,
    SubjectiveClaim,
)
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.schemas import HeadlineSummary, PageKind
from src.analyses.synthesis.headline_summary_agent import (
    _STOCK_PHRASES,
    HEADLINE_SUMMARY_SYSTEM_PROMPT,
    HeadlineSummaryInputs,
    all_inputs_clear,
    pick_stock_phrase,
    run_headline_summary,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone._scd_schemas import SCDReport
from src.config import Settings


class StubAgent:
    def __init__(self, output: HeadlineSummary) -> None:
        self.output = output
        self.prompts: list[str] = []

    async def run(self, user_prompt: str):
        self.prompts.append(user_prompt)
        return SimpleNamespace(output=self.output)


class ExplodingAgent:
    async def run(self, user_prompt: str):  # pragma: no cover - must not run
        raise AssertionError("agent.run must not be called on the all-clear path")


def _empty_inputs() -> HeadlineSummaryInputs:
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


def _harmful_match() -> HarmfulContentMatch:
    return HarmfulContentMatch(
        utterance_id="u1",
        utterance_text="bad",
        max_score=0.6,
        categories={"harassment": True},
        scores={"harassment": 0.6},
        flagged_categories=["harassment"],
        source="gcp",
    )


def _web_risk() -> WebRiskFinding:
    return WebRiskFinding(url="https://bad.example/x", threat_types=["MALWARE"])


def _image_match(max_likelihood: float) -> ImageModerationMatch:
    return ImageModerationMatch(
        utterance_id="u1",
        image_url="https://cdn.example/i.png",
        adult=max_likelihood,
        violence=0.0,
        racy=0.0,
        medical=0.0,
        spoof=0.0,
        flagged=max_likelihood > 0.5,
        max_likelihood=max_likelihood,
    )


def _video_match(max_likelihood: float) -> VideoModerationMatch:
    return VideoModerationMatch(
        utterance_id="u1",
        video_url="https://cdn.example/v.mp4",
        frame_findings=[],
        flagged=max_likelihood > 0.5,
        max_likelihood=max_likelihood,
    )


def _flashpoint() -> FlashpointMatch:
    return FlashpointMatch(
        utterance_id="u1",
        derailment_score=82,
        risk_level=RiskLevel.HEATED,
        reasoning="rising temperature",
        context_messages=3,
    )


def _scd(insufficient: bool) -> SCDReport:
    return SCDReport(summary="ok", insufficient_conversation=insufficient)


def _claims_report(empty: bool) -> ClaimsReport:
    if empty:
        return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)
    return ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text="claim",
                occurrence_count=1,
                author_count=1,
                utterance_ids=["u1"],
                representative_authors=["alice"],
            )
        ],
        total_claims=1,
        total_unique=1,
    )


def _factcheck() -> FactCheckMatch:
    return FactCheckMatch(
        claim_text="claim",
        publisher="Snopes",
        review_title="Mostly false",
        review_url="https://snopes.example/x",
        textual_rating="Mostly false",
    )


def _sentiment(positive_pct: float, negative_pct: float) -> SentimentStatsReport:
    neutral_pct = max(0.0, 100.0 - positive_pct - negative_pct)
    return SentimentStatsReport(
        per_utterance=[
            SentimentScore(utterance_id="u1", label="positive", valence=0.5)
        ]
        if positive_pct or negative_pct
        else [],
        positive_pct=positive_pct,
        negative_pct=negative_pct,
        neutral_pct=neutral_pct,
        mean_valence=0.0,
    )


def _subjective() -> SubjectiveClaim:
    return SubjectiveClaim(
        claim_text="this is great",
        utterance_id="u1",
        stance="supports",
    )


def _safe_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(level=SafetyLevel.SAFE, rationale="all clear")


def _unsafe_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.UNSAFE,
        rationale="malware detected",
        top_signals=["web_risk: MALWARE"],
    )


def test_all_inputs_clear_true_for_empty_inputs():
    assert all_inputs_clear(_empty_inputs()) is True


def test_all_inputs_clear_true_when_safety_is_safe_with_no_signals():
    inputs = replace(_empty_inputs(), safety_recommendation=_safe_recommendation())
    assert all_inputs_clear(inputs) is True


def test_all_inputs_clear_true_when_scd_is_insufficient():
    inputs = replace(_empty_inputs(), scd=_scd(insufficient=True))
    assert all_inputs_clear(inputs) is True


def test_all_inputs_clear_true_when_claims_report_is_empty():
    inputs = replace(_empty_inputs(), claims_report=_claims_report(empty=True))
    assert all_inputs_clear(inputs) is True


def test_all_inputs_clear_true_when_sentiment_has_no_scored_utterances():
    inputs = replace(
        _empty_inputs(),
        sentiment_stats=_sentiment(positive_pct=0.0, negative_pct=0.0),
    )
    assert all_inputs_clear(inputs) is True


def test_all_inputs_clear_false_when_any_image_match_present():
    # Sidebar treats any image match as a non-empty section regardless of
    # max_likelihood (SAFETY_EMPTINESS in Sidebar.tsx). The headline path
    # must agree so we never produce a stock "all clear" line above an
    # expanded image-moderation section.
    inputs = replace(
        _empty_inputs(), image_moderation_matches=[_image_match(0.3)]
    )
    assert all_inputs_clear(inputs) is False


def test_all_inputs_clear_false_when_any_video_match_present():
    inputs = replace(
        _empty_inputs(), video_moderation_matches=[_video_match(0.3)]
    )
    assert all_inputs_clear(inputs) is False


def test_all_inputs_clear_false_when_sentiment_has_neutral_only_utterances():
    # OPINIONS_EMPTINESS in Sidebar.tsx renders the section when
    # per_utterance is non-empty even if positive_pct == negative_pct == 0
    # (an all-neutral page). The headline must mirror that so a stock
    # all-clear line doesn't appear above a rendered sentiment section.
    sentiment = SentimentStatsReport(
        per_utterance=[
            SentimentScore(utterance_id="u1", label="neutral", valence=0.0)
        ],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=100.0,
        mean_valence=0.0,
    )
    inputs = replace(_empty_inputs(), sentiment_stats=sentiment)
    assert all_inputs_clear(inputs) is False


def test_all_inputs_clear_false_when_sentiment_mean_valence_nonzero():
    sentiment = SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=100.0,
        mean_valence=0.4,
    )
    inputs = replace(_empty_inputs(), sentiment_stats=sentiment)
    assert all_inputs_clear(inputs) is False


def test_all_inputs_clear_true_when_sentiment_is_truly_empty():
    # The only sentiment shape that should still register as clear is the
    # "extractor produced nothing" shape: empty per_utterance, all zero
    # percents, and mean_valence == 0.
    sentiment = SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=0.0,
        mean_valence=0.0,
    )
    inputs = replace(_empty_inputs(), sentiment_stats=sentiment)
    assert all_inputs_clear(inputs) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("harmful_content_matches", [_harmful_match()]),
        ("web_risk_findings", [_web_risk()]),
        ("image_moderation_matches", [_image_match(0.9)]),
        ("video_moderation_matches", [_video_match(0.9)]),
        ("flashpoint_matches", [_flashpoint()]),
        ("scd", _scd(insufficient=False)),
        ("claims_report", _claims_report(empty=False)),
        ("known_misinformation", [_factcheck()]),
        ("subjective_claims", [_subjective()]),
        ("sentiment_stats", _sentiment(positive_pct=40.0, negative_pct=10.0)),
        ("safety_recommendation", _unsafe_recommendation()),
    ],
)
def test_all_inputs_clear_false_when_signal_present(field, value):
    inputs = replace(_empty_inputs(), **{field: value})
    assert all_inputs_clear(inputs) is False


def test_pick_stock_phrase_deterministic():
    job_id = UUID("01234567-89ab-cdef-0123-456789abcdef")

    first = pick_stock_phrase(job_id)
    second = pick_stock_phrase(job_id)
    third = pick_stock_phrase(job_id)

    assert first == second == third
    assert first in _STOCK_PHRASES


def test_pick_stock_phrase_varies_across_jobs():
    phrases = {pick_stock_phrase(uuid4()) for _ in range(50)}

    assert len(phrases) >= 2
    for phrase in phrases:
        assert phrase in _STOCK_PHRASES


async def test_run_headline_summary_all_clear_returns_stock_kind(monkeypatch):
    def fake_build_agent(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("build_agent must not be called on the all-clear path")

    monkeypatch.setattr(
        "src.analyses.synthesis.headline_summary_agent.build_agent",
        fake_build_agent,
    )
    settings = cast(Settings, cast(object, SimpleNamespace()))
    job_id = UUID("11111111-1111-1111-1111-111111111111")

    result = await run_headline_summary(_empty_inputs(), settings=settings, job_id=job_id)

    assert result.kind == "stock"
    assert result.text in _STOCK_PHRASES
    assert result.unavailable_inputs == []


async def test_run_headline_summary_signal_calls_agent_and_overrides_kind(monkeypatch):
    agent = StubAgent(
        HeadlineSummary(
            text="model said this",
            kind="stock",
            unavailable_inputs=["model_echo_should_be_ignored"],
        )
    )
    build_calls: list[tuple[Any, ...]] = []

    def fake_build_agent(settings, *, output_type, system_prompt, name=None):
        build_calls.append((settings, output_type, system_prompt, name))
        return agent

    monkeypatch.setattr(
        "src.analyses.synthesis.headline_summary_agent.build_agent",
        fake_build_agent,
    )
    settings = cast(Settings, cast(object, SimpleNamespace()))
    inputs = replace(
        _empty_inputs(),
        harmful_content_matches=[_harmful_match()],
        unavailable_inputs=["web_risk"],
    )
    job_id = UUID("22222222-2222-2222-2222-222222222222")

    result = await run_headline_summary(inputs, settings=settings, job_id=job_id)

    assert result.text == "model said this"
    assert result.kind == "synthesized"
    assert result.unavailable_inputs == ["web_risk"]
    assert build_calls == [
        (
            settings,
            HeadlineSummary,
            HEADLINE_SUMMARY_SYSTEM_PROMPT,
            "vibecheck.headline_summary",
        )
    ]


async def test_run_headline_summary_serializes_inputs_for_agent(monkeypatch):
    agent = StubAgent(
        HeadlineSummary(text="ok", kind="synthesized", unavailable_inputs=[])
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.headline_summary_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    inputs = HeadlineSummaryInputs(
        safety_recommendation=_unsafe_recommendation(),
        harmful_content_matches=[_harmful_match()],
        web_risk_findings=[_web_risk()],
        image_moderation_matches=[_image_match(0.9)],
        video_moderation_matches=[_video_match(0.9)],
        flashpoint_matches=[_flashpoint()],
        scd=_scd(insufficient=False),
        claims_report=_claims_report(empty=False),
        known_misinformation=[_factcheck()],
        sentiment_stats=_sentiment(positive_pct=40.0, negative_pct=10.0),
        subjective_claims=[_subjective()],
        page_title="A page",
        page_kind=PageKind.ARTICLE,
        unavailable_inputs=["video_moderation"],
    )
    settings = cast(Settings, cast(object, SimpleNamespace()))
    job_id = UUID("33333333-3333-3333-3333-333333333333")

    await run_headline_summary(inputs, settings=settings, job_id=job_id)

    payload = json.loads(agent.prompts[0])
    assert set(payload.keys()) >= {
        "safety_recommendation",
        "harmful_content_matches",
        "web_risk_findings",
        "image_moderation_matches",
        "video_moderation_matches",
        "flashpoint_matches",
        "scd",
        "claims_report",
        "known_misinformation",
        "sentiment_stats",
        "subjective_claims",
        "page_title",
        "page_kind",
        "unavailable_inputs",
    }
    assert payload["page_title"] == "A page"
    assert payload["page_kind"] == "article"
    assert payload["unavailable_inputs"] == ["video_moderation"]
    assert payload["safety_recommendation"]["level"] == "unsafe"
    assert payload["harmful_content_matches"][0]["source"] == "gcp"
    assert payload["web_risk_findings"][0]["url"] == "https://bad.example/x"
    assert payload["claims_report"]["total_claims"] == 1


async def test_unavailable_inputs_block_stock_path_even_when_signals_clear(monkeypatch):
    # Codex review: a partial-failure job where the available signals
    # happen to be clear must NOT receive a "Nothing of note" stock
    # phrase, since that lies about coverage. Fall through to the agent
    # path so the model can synthesize a coverage-aware line.
    agent = StubAgent(
        HeadlineSummary(
            text="With limited coverage, nothing else flagged.",
            kind="synthesized",
            unavailable_inputs=[],
        )
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.headline_summary_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    inputs = replace(
        _empty_inputs(),
        unavailable_inputs=["web_risk", "video_moderation"],
    )
    settings = cast(Settings, cast(object, SimpleNamespace()))
    job_id = UUID("44444444-4444-4444-4444-444444444444")

    result = await run_headline_summary(inputs, settings=settings, job_id=job_id)

    assert result.kind == "synthesized"
    # Caller forces unavailable_inputs onto the result regardless of model
    # echo so the discriminator stays trustworthy.
    assert result.unavailable_inputs == ["web_risk", "video_moderation"]
    assert agent.prompts, "agent must be called when unavailable_inputs is non-empty"


async def test_unavailable_inputs_empty_takes_stock_path_when_clear(monkeypatch):
    monkeypatch.setattr(
        "src.analyses.synthesis.headline_summary_agent.build_agent",
        lambda *args, **kwargs: ExplodingAgent(),
    )
    inputs = _empty_inputs()  # empty signals, empty unavailable_inputs
    settings = cast(Settings, cast(object, SimpleNamespace()))
    job_id = UUID("44444444-4444-4444-4444-444444444444")

    result = await run_headline_summary(inputs, settings=settings, job_id=job_id)

    assert result.kind == "stock"
    assert result.text in _STOCK_PHRASES
    assert result.unavailable_inputs == []


async def test_unavailable_inputs_preserved_through_synthesized_path(monkeypatch):
    agent = StubAgent(
        HeadlineSummary(
            text="something specific",
            kind="synthesized",
            unavailable_inputs=["model_echo_only"],
        )
    )
    monkeypatch.setattr(
        "src.analyses.synthesis.headline_summary_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    inputs = replace(
        _empty_inputs(),
        flashpoint_matches=[_flashpoint()],
        unavailable_inputs=["web_risk"],
    )
    settings = cast(Settings, cast(object, SimpleNamespace()))
    job_id = UUID("55555555-5555-5555-5555-555555555555")

    result = await run_headline_summary(inputs, settings=settings, job_id=job_id)

    assert result.kind == "synthesized"
    assert result.unavailable_inputs == ["web_risk"]


def test_stock_phrases_do_not_enumerate_signals():
    forbidden_substrings = (
        "missing",
        "unavailable",
        "could not",
        "couldn't",
    )
    for phrase in _STOCK_PHRASES:
        lowered = phrase.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, (
                f"Stock phrase {phrase!r} enumerates a missing signal "
                f"via {forbidden!r}; rewrite it as a neutral nothing-to-flag line."
            )
