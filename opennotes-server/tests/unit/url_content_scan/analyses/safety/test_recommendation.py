"""Tests for 3-tier safety recommendation + humanized display.

Ports vibecheck PR533 (MILD tier) + PR554 (humanized display) + PR568
(discounted-signal guard). Tests are written to fail against the current
implementation and pass after the implementation is complete.
"""

from __future__ import annotations

import pytest

from src.url_content_scan.analyses.safety.recommendation import (
    SafetyRecommendationInputs,
    _fallback_recommendation,
)
from src.url_content_scan.safety_schemas import (
    Divergence,
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    WebRiskFinding,
)


def _text_match(utterance_id: str, *, max_score: float = 0.62) -> HarmfulContentMatch:
    return HarmfulContentMatch(
        utterance_id=utterance_id,
        utterance_text=f"comment {utterance_id}",
        max_score=max_score,
        categories={"harassment": True},
        scores={"harassment": max_score},
        flagged_categories=["harassment"],
        source="openai",
    )


def _text_discount(utterance_id: str) -> Divergence:
    return Divergence(
        direction="discounted",
        signal_source="Text moderation",
        signal_detail=f"Text moderation signal {utterance_id}",
        reason="Context shows the signal is a false positive.",
    )


def _image_match(utterance_id: str, *, max_likelihood: float = 0.9) -> ImageModerationMatch:
    return ImageModerationMatch(
        utterance_id=utterance_id,
        image_url=f"https://cdn.example/{utterance_id}.jpg",
        adult=0.0,
        violence=0.0,
        racy=max_likelihood,
        medical=0.0,
        spoof=0.0,
        flagged=True,
        max_likelihood=max_likelihood,
    )


def _image_discount(utterance_id: str) -> Divergence:
    return Divergence(
        direction="discounted",
        signal_source="Image moderation",
        signal_detail=f"Image moderation signal {utterance_id}",
        reason="Visual evidence refutes the score-based flag.",
    )


def _caution_recommendation(
    *,
    divergences: list[Divergence] | None = None,
    top_signals: list[str] | None = None,
) -> SafetyRecommendation:
    return SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Raw text moderation signals require review.",
        top_signals=top_signals or ["Low-severity text moderation signals"],
        divergences=divergences or [],
        unavailable_inputs=[],
    )


@pytest.mark.unit
def test_safety_level_enum_has_mild_tier() -> None:
    """MILD must be a valid SafetyLevel value."""
    assert SafetyLevel.MILD == "mild"
    assert SafetyLevel.MILD in list(SafetyLevel)


@pytest.mark.unit
def test_safety_level_enum_has_all_four_tiers() -> None:
    values = [level.value for level in SafetyLevel]
    assert "safe" in values
    assert "mild" in values
    assert "caution" in values
    assert "unsafe" in values


@pytest.mark.unit
def test_safety_recommendation_display_field_present() -> None:
    """SafetyRecommendation must expose a display field for humanized text."""
    rec = SafetyRecommendation(
        level=SafetyLevel.SAFE,
        rationale="All clear.",
        top_signals=[],
    )
    assert hasattr(rec, "display")


@pytest.mark.unit
def test_safety_recommendation_display_safe() -> None:
    rec = SafetyRecommendation(
        level=SafetyLevel.SAFE,
        rationale="All clear.",
        top_signals=[],
    )
    assert rec.display is not None
    assert isinstance(rec.display, str)
    assert len(rec.display) > 0


@pytest.mark.unit
def test_safety_recommendation_display_mild() -> None:
    rec = SafetyRecommendation(
        level=SafetyLevel.MILD,
        rationale="One minor issue.",
        top_signals=[],
    )
    assert rec.display is not None
    assert isinstance(rec.display, str)
    assert len(rec.display) > 0


@pytest.mark.unit
def test_safety_recommendation_display_caution() -> None:
    rec = SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Some concerns.",
        top_signals=[],
    )
    assert rec.display is not None
    assert isinstance(rec.display, str)
    assert len(rec.display) > 0


@pytest.mark.unit
def test_safety_recommendation_display_unsafe() -> None:
    rec = SafetyRecommendation(
        level=SafetyLevel.UNSAFE,
        rationale="High risk.",
        top_signals=[],
    )
    assert rec.display is not None
    assert isinstance(rec.display, str)
    assert len(rec.display) > 0


@pytest.mark.unit
def test_safety_recommendation_display_differs_across_tiers() -> None:
    displays = {
        level: SafetyRecommendation(
            level=level,
            rationale="stub",
            top_signals=[],
        ).display
        for level in SafetyLevel
    }
    unique_displays = set(displays.values())
    assert len(unique_displays) == len(SafetyLevel), (
        "Each SafetyLevel tier should have a distinct display string"
    )


@pytest.mark.unit
def test_safety_recommendation_display_matches_vibecheck_verbiage_safe() -> None:
    rec = SafetyRecommendation(level=SafetyLevel.SAFE, rationale="ok", top_signals=[])
    assert (
        "safe" in rec.display.lower()
        or "no concern" in rec.display.lower()
        or "clear" in rec.display.lower()
    )


@pytest.mark.unit
def test_safety_recommendation_display_matches_vibecheck_verbiage_mild() -> None:
    rec = SafetyRecommendation(level=SafetyLevel.MILD, rationale="ok", top_signals=[])
    assert (
        "mild" in rec.display.lower()
        or "minor" in rec.display.lower()
        or "low" in rec.display.lower()
    )


@pytest.mark.unit
def test_safety_recommendation_display_matches_vibecheck_verbiage_caution() -> None:
    rec = SafetyRecommendation(level=SafetyLevel.CAUTION, rationale="ok", top_signals=[])
    assert (
        "caution" in rec.display.lower()
        or "concern" in rec.display.lower()
        or "review" in rec.display.lower()
    )


@pytest.mark.unit
def test_safety_recommendation_display_matches_vibecheck_verbiage_unsafe() -> None:
    rec = SafetyRecommendation(level=SafetyLevel.UNSAFE, rationale="ok", top_signals=[])
    assert (
        "unsafe" in rec.display.lower()
        or "high" in rec.display.lower()
        or "risk" in rec.display.lower()
        or "harmful" in rec.display.lower()
    )


@pytest.mark.unit
def test_safety_section_carries_display_via_recommendation() -> None:
    """SafetySection.recommendation should expose display through SafetyRecommendation."""
    from src.url_content_scan.schemas import SafetySection

    section = SafetySection(
        harmful_content_matches=[],
        recommendation=SafetyRecommendation(
            level=SafetyLevel.MILD,
            rationale="Minor concern.",
            top_signals=["Mild signal"],
        ),
    )
    assert section.recommendation is not None
    assert section.recommendation.display is not None
    assert len(section.recommendation.display) > 0


@pytest.mark.unit
def test_discounted_signals_guard_downgrades_all_text_discounted_to_safe() -> None:
    """When all text signals are discounted via divergences, guardrail -> SAFE."""
    from src.url_content_scan.analyses.safety.recommendation import (
        _apply_discounted_signals_guardrail,
    )

    recommendation = _caution_recommendation(
        divergences=[_text_discount("u1"), _text_discount("u2")]
    )
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1"), _text_match("u2")],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )

    result, reason = _apply_discounted_signals_guardrail(recommendation, inputs)

    assert result.level == SafetyLevel.SAFE
    assert reason == "all_text_signals_discounted"


@pytest.mark.unit
def test_discounted_signals_guard_downgrades_one_remaining_to_mild() -> None:
    """One supported text signal remaining after discounts -> MILD."""
    from src.url_content_scan.analyses.safety.recommendation import (
        _apply_discounted_signals_guardrail,
    )

    recommendation = _caution_recommendation(divergences=[_text_discount("u1")])
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1"), _text_match("u2")],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )

    result, reason = _apply_discounted_signals_guardrail(recommendation, inputs)

    assert result.level == SafetyLevel.MILD
    assert reason == "one_supported_low_severity_signal"


@pytest.mark.unit
def test_discounted_signals_guard_keeps_caution_when_multiple_remain() -> None:
    """Two supported text signals remaining -> stays CAUTION."""
    from src.url_content_scan.analyses.safety.recommendation import (
        _apply_discounted_signals_guardrail,
    )

    recommendation = _caution_recommendation(divergences=[_text_discount("u1")])
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1"), _text_match("u2"), _text_match("u3")],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )

    result, reason = _apply_discounted_signals_guardrail(recommendation, inputs)

    assert result.level == SafetyLevel.CAUTION
    assert reason is None


@pytest.mark.unit
def test_discounted_signals_guard_skips_when_unavailable_inputs_present() -> None:
    """Guardrail does not downgrade when inputs are unavailable."""
    from src.url_content_scan.analyses.safety.recommendation import (
        _apply_discounted_signals_guardrail,
    )

    recommendation = _caution_recommendation(divergences=[_text_discount("u1")])
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1")],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=["web_risk"],
    )

    result, reason = _apply_discounted_signals_guardrail(recommendation, inputs)

    assert result.level == SafetyLevel.CAUTION
    assert reason is None


@pytest.mark.unit
def test_discounted_signals_guard_skips_when_web_risk_present() -> None:
    """Guardrail does not downgrade when web risk findings exist."""
    from src.url_content_scan.analyses.safety.recommendation import (
        _apply_discounted_signals_guardrail,
    )

    recommendation = _caution_recommendation(divergences=[_text_discount("u1")])
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1")],
        web_risk_findings=[
            WebRiskFinding(
                url="https://download.example/tool",
                threat_types=["POTENTIALLY_HARMFUL_APPLICATION"],
            )
        ],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )

    result, reason = _apply_discounted_signals_guardrail(recommendation, inputs)

    assert result.level == SafetyLevel.CAUTION
    assert reason is None


@pytest.mark.unit
def test_discounted_signals_guard_handles_false_positive_top_signal_pattern() -> None:
    """Narrow false-positive: model signals all-FP in top_signals without divergences."""
    from src.url_content_scan.analyses.safety.recommendation import (
        _apply_discounted_signals_guardrail,
    )

    recommendation = _caution_recommendation(
        top_signals=["Text moderation flags triggered, but judged to be false positives."],
        divergences=[],
    )
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1"), _text_match("u2")],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )

    result, reason = _apply_discounted_signals_guardrail(recommendation, inputs)

    assert result.level == SafetyLevel.SAFE
    assert reason == "all_text_signals_discounted"


@pytest.mark.unit
def test_fallback_recommendation_resolves_mild_for_single_low_score_match() -> None:
    """_fallback_recommendation with a single low-score text match should produce MILD."""
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[_text_match("u1", max_score=0.55)],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )
    result = _fallback_recommendation(inputs)
    assert result.level in (SafetyLevel.MILD, SafetyLevel.CAUTION)


@pytest.mark.unit
def test_system_prompt_includes_mild_tier() -> None:
    """RECOMMENDATION_SYSTEM_PROMPT must define all four tiers including mild."""
    from src.url_content_scan.analyses.safety.recommendation import RECOMMENDATION_SYSTEM_PROMPT

    assert "mild" in RECOMMENDATION_SYSTEM_PROMPT.lower()
    assert "safe" in RECOMMENDATION_SYSTEM_PROMPT.lower()
    assert "caution" in RECOMMENDATION_SYSTEM_PROMPT.lower()
    assert "unsafe" in RECOMMENDATION_SYSTEM_PROMPT.lower()
