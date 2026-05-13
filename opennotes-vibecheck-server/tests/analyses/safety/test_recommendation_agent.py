from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.analyses.safety import recommendation_agent
from src.analyses.safety._schemas import (
    Divergence,
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    VideoSegmentFinding,
    WebRiskFinding,
)
from src.analyses.safety.recommendation_agent import (
    RECOMMENDATION_SYSTEM_PROMPT,
    SafetyRecommendationInputs,
    _sanitize_divergences,
    _sanitize_top_signals,
    run_safety_recommendation,
)
from src.analyses.safety.vision_client import FLAG_THRESHOLD
from src.config import Settings


class StubAgent:
    def __init__(self, output: SafetyRecommendation) -> None:
        self.output = output
        self.prompts: list[str] = []
        self.calls: list[tuple[Any, ...]] = []

    async def run(self, *args: Any) -> Any:
        self.calls.append(args)
        if args and isinstance(args[0], str):
            self.prompts.append(args[0])
        return SimpleNamespace(output=self.output)


def _text_match(utterance_id: str, *, max_score: float = 0.62) -> HarmfulContentMatch:
    return HarmfulContentMatch(
        utterance_id=utterance_id,
        utterance_text=f"comment {utterance_id}",
        max_score=max_score,
        categories={"harassment": True},
        scores={"harassment": max_score},
        flagged_categories=["harassment"],
        source="gcp",
    )


def _text_discount(utterance_id: str) -> Divergence:
    return Divergence(
        direction="discounted",
        signal_source="Text moderation",
        signal_detail=f"Text moderation signal {utterance_id}",
        reason="Context shows the signal is a false positive.",
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


def test_recommendation_prompt_defines_all_four_levels() -> None:
    assert "safe:" in RECOMMENDATION_SYSTEM_PROMPT
    assert "mild:" in RECOMMENDATION_SYSTEM_PROMPT
    assert "caution:" in RECOMMENDATION_SYSTEM_PROMPT
    assert "unsafe:" in RECOMMENDATION_SYSTEM_PROMPT
    assert "Web Risk findings for the same URL" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_enforces_divergence_display_readability() -> None:
    assert "divergences" in RECOMMENDATION_SYSTEM_PROMPT
    assert "signal_source" in RECOMMENDATION_SYSTEM_PROMPT
    assert "signal_detail" in RECOMMENDATION_SYSTEM_PROMPT
    assert "human-readable" in RECOMMENDATION_SYSTEM_PROMPT
    assert "never raw category names" in RECOMMENDATION_SYSTEM_PROMPT
    assert "top_signals from raw model output must be sanitized" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_has_divergence_hierarchy_and_sanitization_rules() -> None:
    assert "divergences" in RECOMMENDATION_SYSTEM_PROMPT
    assert "If you discount a raw signal" in RECOMMENDATION_SYSTEM_PROMPT
    assert "If you escalate beyond the weakest raw signals" in RECOMMENDATION_SYSTEM_PROMPT
    assert "directly supported by inputs" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_downgrades_all_discounted_complete_coverage() -> None:
    assert "at least one remains supported after context review" in RECOMMENDATION_SYSTEM_PROMPT
    assert "every raw signal is judged a false positive" in RECOMMENDATION_SYSTEM_PROMPT
    assert "return `safe`" in RECOMMENDATION_SYSTEM_PROMPT
    assert "Exactly one supported low-severity signal can be `mild`" in RECOMMENDATION_SYSTEM_PROMPT
    assert "Multiple supported low-severity signals can still justify `caution`" in RECOMMENDATION_SYSTEM_PROMPT
    assert "MUST emit a corresponding direction=\"discounted\" divergence" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_describes_image_vision_review() -> None:
    assert "Image moderation" in RECOMMENDATION_SYSTEM_PROMPT
    assert "image_vision_review" in RECOMMENDATION_SYSTEM_PROMPT
    assert 'direction="discounted"' in RECOMMENDATION_SYSTEM_PROMPT
    assert "ImageModerationMatch" in RECOMMENDATION_SYSTEM_PROMPT
    assert "contradict" in RECOMMENDATION_SYSTEM_PROMPT
    assert "unavailable_inputs" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_treats_inconclusive_video_as_incomplete_evidence() -> None:
    assert "sampling_inconclusive" in RECOMMENDATION_SYSTEM_PROMPT
    assert "incomplete evidence" in RECOMMENDATION_SYSTEM_PROMPT
    assert "not a supported video safety signal" in RECOMMENDATION_SYSTEM_PROMPT
    assert "must not by itself justify `caution`" in RECOMMENDATION_SYSTEM_PROMPT
    assert "Treat it as caution unless" not in RECOMMENDATION_SYSTEM_PROMPT


async def test_run_safety_recommendation_omits_image_parts_when_no_image_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="No images attached.",
            top_signals=[],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(VIBECHECK_SAFETY_IMAGE_VISION_REVIEW_ENABLED=True),
    )

    assert len(agent.calls) == 1
    assert len(agent.calls[0]) == 1
    assert isinstance(agent.calls[0][0], str)


async def test_run_safety_recommendation_passes_image_urls_as_multimodal_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic_ai.messages import ImageUrl

    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="Image confirmed benign.",
            top_signals=[],
        )
    )
    span: dict[str, Any] = {}

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            span[key] = value

        def set_attributes(self, attributes: dict[str, Any]) -> None:
            span.update(attributes)

    def _fake_span(name: str, **attrs: Any) -> _RecordingSpan:
        span.update(attrs)
        return _RecordingSpan()

    monkeypatch.setattr(recommendation_agent.logfire, "span", _fake_span)
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(VIBECHECK_SAFETY_IMAGE_VISION_REVIEW_ENABLED=True),
        image_urls=["https://a/img.jpg", "https://b/img.png"],
    )

    assert len(agent.calls) == 1
    call = agent.calls[0]
    assert len(call) == 3
    assert isinstance(call[0], str)
    assert isinstance(call[1], ImageUrl)
    assert call[1].url == "https://a/img.jpg"
    assert isinstance(call[2], ImageUrl)
    assert call[2].url == "https://b/img.png"
    assert span["vision_review_image_count"] == 2


async def test_run_safety_recommendation_omits_image_parts_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="Flag disabled.",
            top_signals=[],
        )
    )
    span: dict[str, Any] = {}

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            span[key] = value

        def set_attributes(self, attributes: dict[str, Any]) -> None:
            span.update(attributes)

    def _fake_span(name: str, **attrs: Any) -> _RecordingSpan:
        span.update(attrs)
        return _RecordingSpan()

    monkeypatch.setattr(recommendation_agent.logfire, "span", _fake_span)
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(VIBECHECK_SAFETY_IMAGE_VISION_REVIEW_ENABLED=False),
        image_urls=["https://a/img.jpg"],
    )

    assert len(agent.calls) == 1
    assert len(agent.calls[0]) == 1
    assert isinstance(agent.calls[0][0], str)
    assert span["vision_review_image_count"] == 0


async def test_run_safety_recommendation_logfire_attrs_are_set_for_inputs_and_sanitization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span: dict[str, Any] = {}

    class _RecordingSpan:
        def __enter__(self) -> _RecordingSpan:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def set_attribute(self, key: str, value: Any) -> None:
            span[key] = value

        def set_attributes(self, attributes: dict[str, Any]) -> None:
            span.update(attributes)

    def _fake_span(name: str, **attrs: Any) -> _RecordingSpan:
        span.update(attrs)
        return _RecordingSpan()

    agent = StubAgent(
            SafetyRecommendation(
                level=SafetyLevel.CAUTION,
                rationale="A moderation match was found.",
                top_signals=["Mild harassment topic match"],
                divergences=[
                    Divergence(
                        direction="discounted",
                        signal_source="text_moderation",
                        signal_detail="Possible sexual/minors",
                        reason="discounted: POTENTIALLY_HARMFUL_APPLICATION 0.92",
                    )
                ],
                unavailable_inputs=[],
            )
        )

    monkeypatch.setattr(recommendation_agent.logfire, "span", _fake_span)
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda settings, *, output_type, system_prompt, name=None, tier="fast": agent,
    )

    await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[
                HarmfulContentMatch(
                    utterance_id="u1",
                    utterance_text="heated comment",
                    max_score=0.62,
                    categories={"harassment": True},
                    scores={"harassment": 0.62},
                    flagged_categories=["harassment"],
                    source="gcp",
                )
            ],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=["web_risk", "image_moderation"],
            source_url="https://example.com/page",
        ),
        settings=Settings(),
    )

    assert span["harmful_input_count"] == 1
    assert span["unavailable_input_count"] == 2
    assert span["source_url_present"]
    assert span["divergence_count"] == 1
    assert span["divergence_direction_distribution"] == {
        "discounted": 1,
        "escalated": 0,
    }
    assert span["divergence_source_distribution"]["known"] == {"Text moderation": 1}
    assert span["divergence_source_distribution"]["unknown_count"] == 0
    assert span["divergence_sanitizer_replacement_count"] == 2


async def test_run_safety_recommendation_serializes_inputs_for_agent(monkeypatch):
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="A moderation match was found.",
            top_signals=["Mild harassment topic match"],
        )
    )
    build_calls = []

    def fake_build_agent(settings, *, output_type, system_prompt, name=None, tier="fast"):
        build_calls.append((settings, output_type, system_prompt, name, tier))
        return agent

    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        fake_build_agent,
    )
    settings = Settings()

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[
                HarmfulContentMatch(
                    utterance_id="u1",
                    utterance_text="heated comment",
                    max_score=0.62,
                    categories={"harassment": True},
                    scores={"harassment": 0.62},
                    flagged_categories=["harassment"],
                    source="gcp",
                )
            ],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=["web_risk"],
            source_url="https://example.com/page",
        ),
        settings=settings,
    )

    assert result.level == SafetyLevel.CAUTION
    assert build_calls == [
        (
            settings,
            SafetyRecommendation,
            RECOMMENDATION_SYSTEM_PROMPT,
            "vibecheck.safety_recommendation",
            "synthesis",
        )
    ]
    payload = json.loads(agent.prompts[0])
    assert payload["harmful_content_matches"][0]["source"] == "gcp"
    assert payload["unavailable_inputs"] == ["web_risk"]
    assert payload["source_url"] == "https://example.com/page"
    assert payload["source_url"] is not None


async def test_video_sampling_sentinel_is_marked_inconclusive(monkeypatch):
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Video sampling was inconclusive.",
            top_signals=["Video sampling inconclusive."],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )
    settings = Settings()

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[
                VideoModerationMatch(
                    utterance_id="u1",
                    video_url="https://cdn.example/video.mp4",
                    segment_findings=[],
                    flagged=True,
                    max_likelihood=1.0,
                )
            ],
            unavailable_inputs=[],
        ),
        settings=settings,
    )

    payload = json.loads(agent.prompts[0])
    assert payload["video_moderation_matches"][0]["sampling_inconclusive"]
    assert result.level == SafetyLevel.SAFE
    assert result.top_signals == []
    assert "inconclusive" in result.rationale.lower()


async def test_run_safety_recommendation_defaults_source_url_to_none(monkeypatch):
    agent = StubAgent(
        _recommendation(["No explicit URL context provided"], level=SafetyLevel.CAUTION)
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    payload = json.loads(agent.prompts[0])
    assert payload["source_url"] is None
    assert result.level == SafetyLevel.CAUTION


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        (
            SafetyRecommendationInputs(
                harmful_content_matches=[],
                web_risk_findings=[],
                image_moderation_matches=[],
                video_moderation_matches=[],
                unavailable_inputs=[],
            ),
            SafetyLevel.SAFE,
        ),
        (
            SafetyRecommendationInputs(
                harmful_content_matches=[
                    HarmfulContentMatch(
                        utterance_id="u1",
                        utterance_text="topic hit",
                        max_score=0.51,
                        categories={"toxicity": True},
                        scores={"toxicity": 0.51},
                        flagged_categories=["toxicity"],
                        source="gcp",
                    )
                ],
                web_risk_findings=[],
                image_moderation_matches=[],
                video_moderation_matches=[],
                unavailable_inputs=["web_risk"],
            ),
            SafetyLevel.CAUTION,
        ),
    ],
)
async def test_agent_output_level_is_returned(monkeypatch, inputs, expected):
    agent = StubAgent(
        SafetyRecommendation(
            level=expected,
            rationale="stubbed",
            unavailable_inputs=inputs.unavailable_inputs,
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        inputs,
        settings=Settings(),
    )

    assert result.level == expected
    assert result.unavailable_inputs == inputs.unavailable_inputs


async def test_topic_match_only_output_can_return_mild(monkeypatch):
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[
            HarmfulContentMatch(
                utterance_id="u1",
                utterance_text="topic hit",
                max_score=0.51,
                categories={"toxicity": True},
                scores={"toxicity": 0.51},
                flagged_categories=["toxicity"],
                source="gcp",
            )
        ],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.MILD,
            rationale="One topic-match-only moderation hit.",
            top_signals=["Mild toxicity topic match"],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.level == SafetyLevel.MILD
    assert result.top_signals == ["Mild toxicity topic match"]


async def test_run_safety_recommendation_passes_discounted_sensitive_topic_divergence(
    monkeypatch,
) -> None:
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[
            HarmfulContentMatch(
                utterance_id="u1",
                utterance_text="topic hit",
                max_score=0.9,
                categories={"sex": True},
                scores={"sex": 0.9},
                flagged_categories=["sex"],
                source="gcp",
            )
        ],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )
    expected = [
        Divergence(
            direction="discounted",
            signal_source="Text moderation",
            signal_detail="Text moderation flagged sexual-health keyword match",
            reason="The page is an educational health resource about sexuality.",
        )
    ]
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Context reduced concern despite a sensitive-topic hit.",
            top_signals=["Educational sexual-health context"],
            divergences=expected,
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.divergences == expected


async def test_run_safety_recommendation_passes_discounted_web_risk_divergence(
    monkeypatch,
) -> None:
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[],
        web_risk_findings=[
            WebRiskFinding(
                url="https://vibecheck.opennotes.ai/report",
                threat_types=["POTENTIALLY_HARMFUL_APPLICATION"],
            )
        ],
        source_url="https://vibecheck.opennotes.ai/report",
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )
    expected = [
        Divergence(
            direction="discounted",
            signal_source="Web Risk",
            signal_detail="web risk flagged current article URL",
            reason=(
                "The URL under review is the same page that generated "
                "this analysis, so no external threat was observed."
            ),
        )
    ]
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="No external attack surface detected.",
            top_signals=["No additional risk indicators"],
            divergences=expected,
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.divergences == expected
    assert json.loads(agent.prompts[0])["source_url"] == inputs.source_url


async def test_run_safety_recommendation_passes_escalated_weak_signal_divergence(
    monkeypatch,
) -> None:
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[
            HarmfulContentMatch(
                utterance_id="u1",
                utterance_text="topic hit",
                max_score=0.51,
                categories={"toxicity": True},
                scores={"toxicity": 0.51},
                flagged_categories=["toxicity"],
                source="gcp",
            )
        ],
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
    expected = [
        Divergence(
            direction="escalated",
            signal_source="Combined signals",
            signal_detail="Low toxicity + low web-risk + mild visual silence",
            reason=(
                "Together these low-severity cues indicate potential abuse pattern "
                "despite each signal being weak alone."
            ),
        )
    ]
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Combined weak signals justify a caution level.",
            top_signals=["Combined weak safety cues"],
            divergences=expected,
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.divergences == expected


async def test_run_safety_recommendation_preserves_empty_divergences(monkeypatch) -> None:
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[],
        web_risk_findings=[],
        image_moderation_matches=[],
        video_moderation_matches=[],
        unavailable_inputs=[],
    )
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="No safety concerns found.",
            top_signals=[],
            divergences=[],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.divergences == []


async def test_guardrail_downgrades_all_discounted_text_signals_to_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(
        _caution_recommendation(
            divergences=[_text_discount("u1"), _text_discount("u2")]
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1"), _text_match("u2")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == SafetyLevel.SAFE
    assert result.top_signals == []
    assert result.divergences == [_text_discount("u1"), _text_discount("u2")]


async def test_guardrail_downgrades_one_remaining_text_signal_to_mild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(_caution_recommendation(divergences=[_text_discount("u1")]))
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1"), _text_match("u2")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == SafetyLevel.MILD
    assert result.top_signals == ["Low-severity text moderation signals"]


async def test_guardrail_keeps_caution_when_multiple_text_signals_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(_caution_recommendation(divergences=[_text_discount("u1")]))
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[
                _text_match("u1"),
                _text_match("u2"),
                _text_match("u3"),
            ],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == SafetyLevel.CAUTION


@pytest.mark.parametrize(
    "inputs",
    [
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=["web_risk"],
        ),
        SafetyRecommendationInputs(
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
        ),
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[
                VideoModerationMatch(
                    utterance_id="u-video",
                    video_url="https://cdn.example/video.mp4",
                    segment_findings=[
                        VideoSegmentFinding(
                            start_offset_ms=0,
                            end_offset_ms=1000,
                            adult=0.0,
                            violence=0.8,
                            racy=0.0,
                            medical=0.0,
                            spoof=0.0,
                            flagged=True,
                            max_likelihood=0.8,
                        )
                    ],
                    flagged=True,
                    max_likelihood=0.8,
                )
            ],
            unavailable_inputs=[],
        ),
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[
                ImageModerationMatch(
                    utterance_id="u-image",
                    image_url="https://cdn.example/image.jpg",
                    adult=0.0,
                    violence=FLAG_THRESHOLD,
                    racy=0.0,
                    medical=0.0,
                    spoof=0.0,
                    flagged=False,
                    max_likelihood=FLAG_THRESHOLD,
                )
            ],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
    ],
)
async def test_guardrail_preserves_caution_when_downgrade_blockers_remain(
    inputs: SafetyRecommendationInputs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(_caution_recommendation(divergences=[_text_discount("u1")]))
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.level == SafetyLevel.CAUTION


async def test_guardrail_allows_downgrade_when_video_sampling_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(_caution_recommendation(divergences=[_text_discount("u1")]))
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[
                VideoModerationMatch(
                    utterance_id="u-video",
                    video_url="https://cdn.example/video.mp4",
                    segment_findings=[],
                    flagged=True,
                    max_likelihood=1.0,
                )
            ],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == SafetyLevel.SAFE


async def test_guardrail_preserves_caution_when_divergence_escalates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = StubAgent(
        _caution_recommendation(
            divergences=[
                _text_discount("u1"),
                Divergence(
                    direction="escalated",
                    signal_source="Combined signals",
                    signal_detail="Weak signals align",
                    reason="Combined signals warrant review.",
                ),
            ]
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == SafetyLevel.CAUTION


async def test_guardrail_uses_narrow_missing_divergence_false_positive_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reproduces job 63105466-4d10-4972-a8b9-1926fe1def4a: the model explained
    # that every raw text signal was a false positive but emitted no divergences.
    agent = StubAgent(
        _caution_recommendation(
            top_signals=[
                "Text moderation flags triggered, but judged to be false positives."
            ]
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1"), _text_match("u2")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == SafetyLevel.SAFE


async def test_guardrail_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = StubAgent(_caution_recommendation(divergences=[_text_discount("u1")]))
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(VIBECHECK_SAFETY_RECOMMENDATION_GUARDRAIL_ENABLED=False),
    )

    assert result.level == SafetyLevel.CAUTION


async def test_guardrail_logs_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[str, dict[str, Any]]] = []
    agent = StubAgent(_caution_recommendation(divergences=[_text_discount("u1")]))

    def _warn(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    monkeypatch.setattr(recommendation_agent.logfire, "warning", _warn)
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert warnings == [
        (
            "safety_recommendation_guardrail_downgrade",
            {
                "original_level": "caution",
                "downgraded_level": "safe",
                "reason": "all_text_signals_discounted",
            },
        )
    ]


@pytest.mark.parametrize(
    "level",
    [SafetyLevel.SAFE, SafetyLevel.MILD, SafetyLevel.UNSAFE],
)
async def test_guardrail_only_changes_caution(level, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = StubAgent(
        SafetyRecommendation(
            level=level,
            rationale="Model returned a non-caution level.",
            top_signals=["Model signal"],
            divergences=[_text_discount("u1")],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[_text_match("u1")],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=[],
        ),
        settings=Settings(),
    )

    assert result.level == level


async def test_multiple_low_severity_flags_do_not_return_mild(monkeypatch):
    inputs = SafetyRecommendationInputs(
        harmful_content_matches=[
            HarmfulContentMatch(
                utterance_id="u1",
                utterance_text="topic hit",
                max_score=0.51,
                categories={"toxicity": True},
                scores={"toxicity": 0.51},
                flagged_categories=["toxicity"],
                source="gcp",
            )
        ],
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
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Multiple low-severity signals need attention.",
            top_signals=[
                "topic-match content score 0.51",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.level == SafetyLevel.CAUTION


def test_sanitize_divergences_maps_known_raw_sources_and_replaces_sensitive_tokens() -> None:
    recommendation = SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Context reduced concern.",
        divergences=[
            Divergence(
                direction="discounted",
                signal_source="text_moderation/openai",
                signal_detail="adult/sexual risk",
                reason="discounted: sexual/minors with score 0.95",
            ),
            Divergence(
                direction="escalated",
                signal_source="openai",
                signal_detail="Likely scam",
                reason="escalated: possible coordinated behavior",
            ),
        ],
    )

    sanitized, replacements, directions, source_distribution = _sanitize_divergences(
        recommendation
    )

    assert sanitized.divergences == [
        Divergence(
            direction="discounted",
            signal_source="Text moderation",
            signal_detail="Signal detail adjusted",
            reason="Signal context discounted",
        ),
        Divergence(
            direction="escalated",
            signal_source="Text moderation",
            signal_detail="Likely scam",
            reason="possible coordinated behavior",
        ),
    ]
    assert replacements == 2
    assert directions == {"discounted": 1, "escalated": 1}
    assert source_distribution == {
        "known": {"Text moderation": 2},
        "unknown_count": 0,
    }


def test_sanitize_divergences_preserves_display_ready_divergence_values() -> None:
    recommendation = SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="No sanitization needed.",
        divergences=[
            Divergence(
                direction="discounted",
                signal_source="Web Risk",
                signal_detail="Page appears consistent with health education.",
                reason="Context was reviewed and appears benign.",
            ),
            Divergence(
                direction="escalated",
                signal_source="Combined signals",
                signal_detail="Low but consistent topic signals across sources.",
                reason="Consistent corroborating indicators were observed.",
            ),
        ],
    )

    sanitized, replacements, directions, source_distribution = _sanitize_divergences(
        recommendation
    )

    assert sanitized == recommendation
    assert replacements == 0
    assert directions == {"discounted": 1, "escalated": 1}
    assert source_distribution == {
        "known": {"Web Risk": 1, "Combined signals": 1},
        "unknown_count": 0,
    }


def test_sanitize_divergences_preserves_display_ready_slash_phrases() -> None:
    recommendation = SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Slash phrase is normal prose.",
        divergences=[
            Divergence(
                direction="discounted",
                signal_source="Image moderation",
                signal_detail="Before/after comparison is educational.",
                reason="Before/after context changes the interpretation.",
            )
        ],
    )

    sanitized, replacements, directions, source_distribution = _sanitize_divergences(
        recommendation
    )

    assert sanitized == recommendation
    assert replacements == 0
    assert directions == {"discounted": 1, "escalated": 0}
    assert source_distribution == {
        "known": {"Image moderation": 1},
        "unknown_count": 0,
    }


def test_sanitize_divergences_buckets_unmapped_source_labels_as_unknown() -> None:
    recommendation = SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Unknown source label needs fallback.",
        divergences=[
            Divergence(
                direction="discounted",
                signal_source="moderation/video_gcp/v1",
                signal_detail="likely harmless",
                reason="Signal context discounted.",
            )
        ],
    )

    sanitized, replacements, directions, source_distribution = _sanitize_divergences(
        recommendation
    )

    assert sanitized.divergences == [
        Divergence(
            direction="discounted",
            signal_source="Safety signal",
            signal_detail="likely harmless",
            reason="Signal context discounted.",
        ),
    ]
    assert replacements == 1
    assert directions == {"discounted": 1, "escalated": 0}
    assert source_distribution == {
        "known": {},
        "unknown_count": 1,
    }


def test_sanitize_divergences_logs_when_fallback_fields_are_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[tuple[str, dict[str, Any]]] = []

    def _warn(message: str, **kwargs: Any) -> None:
        warnings.append((message, kwargs))

    monkeypatch.setattr(recommendation_agent.logfire, "warning", _warn)

    recommendation = SafetyRecommendation(
        level=SafetyLevel.CAUTION,
        rationale="Context reduced concern.",
        divergences=[
            Divergence(
                direction="discounted",
                signal_source="openai",
                signal_detail="adult max_likelihood 0.98",
                reason="discounted: POTENTIALLY_HARMFUL_APPLICATION",
            )
        ],
    )

    _sanitize_divergences(recommendation)

    assert warnings == [
        (
            "safety_recommendation_divergence_sanitized",
            {"replacement_count": 2, "divergence_count": 1},
        )
    ]


def _recommendation(
    top_signals: list[str], level: SafetyLevel = SafetyLevel.CAUTION
) -> SafetyRecommendation:
    return SafetyRecommendation(
        level=level,
        rationale="stub",
        top_signals=top_signals,
    )


def test_sanitize_strips_raw_text_moderation_score() -> None:
    result = _sanitize_top_signals(
        _recommendation(["text: Legal 1.0", "Real concern"])
    )
    assert result.top_signals == ["Real concern"]


def test_sanitize_strips_vision_enum_label() -> None:
    result = _sanitize_top_signals(
        _recommendation(["adult VERY_LIKELY", "Mild rhetoric"])
    )
    assert result.top_signals == ["Mild rhetoric"]


def test_sanitize_strips_vision_float_syntax() -> None:
    result = _sanitize_top_signals(
        _recommendation(["adult max_likelihood 0.91", "Verified visual concern"])
    )
    assert result.top_signals == ["Verified visual concern"]


def test_sanitize_keeps_only_valid_entries_in_mixed_list() -> None:
    result = _sanitize_top_signals(
        _recommendation(
            [
                "text: Legal 1.0",
                "Repeated low-severity toxicity",
                "adult max_likelihood 0.85",
            ]
        )
    )
    assert result.top_signals == ["Repeated low-severity toxicity"]


def test_sanitize_falls_back_to_placeholder_when_all_invalid() -> None:
    result = _sanitize_top_signals(
        _recommendation(["text: Legal 1.0", "adult VERY_LIKELY"])
    )
    assert result.top_signals == ["Verified concern requires review"]


def test_sanitize_leaves_empty_list_empty() -> None:
    result = _sanitize_top_signals(_recommendation([]))
    assert result.top_signals == []


def test_sanitize_preserves_benign_integer_suffix_signal() -> None:
    result = _sanitize_top_signals(_recommendation(["Phishing link 1"]))
    assert result.top_signals == ["Phishing link 1"]


def test_sanitize_preserves_prose_with_lowercase_likely() -> None:
    result = _sanitize_top_signals(_recommendation(["Likely scam"]))
    assert result.top_signals == ["Likely scam"]


def test_sanitize_preserves_prose_with_lowercase_possible() -> None:
    result = _sanitize_top_signals(_recommendation(["Possible phishing link"]))
    assert result.top_signals == ["Possible phishing link"]


def test_sanitize_preserves_prose_with_lowercase_unlikely() -> None:
    result = _sanitize_top_signals(_recommendation(["Unlikely false positive"]))
    assert result.top_signals == ["Unlikely false positive"]


def test_sanitize_still_strips_uppercase_vision_enum() -> None:
    result = _sanitize_top_signals(
        _recommendation(["adult VERY_LIKELY", "Real concern"])
    )
    assert result.top_signals == ["Real concern"]


def test_sanitize_omits_placeholder_for_safe_when_all_stripped() -> None:
    result = _sanitize_top_signals(
        _recommendation(
            ["text: Legal 1.0", "adult VERY_LIKELY"], level=SafetyLevel.SAFE
        )
    )
    assert result.top_signals == []


def test_sanitize_omits_placeholder_for_mild_when_all_stripped() -> None:
    result = _sanitize_top_signals(
        _recommendation(
            ["text: Legal 1.0", "adult VERY_LIKELY"], level=SafetyLevel.MILD
        )
    )
    assert result.top_signals == []


def test_sanitize_inserts_placeholder_for_unsafe_when_all_stripped() -> None:
    result = _sanitize_top_signals(
        _recommendation(
            ["text: Legal 1.0", "adult VERY_LIKELY"], level=SafetyLevel.UNSAFE
        )
    )
    assert result.top_signals == ["Verified concern requires review"]
