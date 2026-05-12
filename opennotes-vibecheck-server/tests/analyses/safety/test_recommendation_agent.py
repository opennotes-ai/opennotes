from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.analyses.safety._schemas import (
    Divergence,
    HarmfulContentMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.safety.recommendation_agent import (
    RECOMMENDATION_SYSTEM_PROMPT,
    SafetyRecommendationInputs,
    _sanitize_top_signals,
    run_safety_recommendation,
)
from src.config import Settings


class StubAgent:
    def __init__(self, output: SafetyRecommendation) -> None:
        self.output = output
        self.prompts: list[str] = []

    async def run(self, user_prompt: str):
        self.prompts.append(user_prompt)
        return SimpleNamespace(output=self.output)


def test_recommendation_prompt_defines_all_four_levels() -> None:
    assert "- safe: all available inputs are clear." in RECOMMENDATION_SYSTEM_PROMPT
    assert (
        "- mild: one verified low-severity signal" in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert "- caution: partial data" in RECOMMENDATION_SYSTEM_PROMPT
    assert "- unsafe: verified high-risk signals" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_requires_human_readable_top_signals() -> None:
    assert (
        "top_signals entries must be short human-readable noun phrases or sentences"
        in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert (
        "Text moderation flags triggered, but judged to be false positives."
        in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert "Violent topics" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_prioritizes_remaining_concern_after_false_positives() -> None:
    assert "false-positive-heavy caution cases" in RECOMMENDATION_SYSTEM_PROMPT
    assert "do not lead top_signals with dismissed raw moderation scores" in (
        RECOMMENDATION_SYSTEM_PROMPT
    )
    assert "Repeated low-severity toxicity" in RECOMMENDATION_SYSTEM_PROMPT
    assert "Mild violent rhetoric" in RECOMMENDATION_SYSTEM_PROMPT


def test_recommendation_prompt_includes_divergence_guidance() -> None:
    assert "Use the `divergences` field to record how your final verdict differs" in (
        RECOMMENDATION_SYSTEM_PROMPT
    )
    assert (
        "discounted sensitive-topic signal when the text is a sensitive topic"
        in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert (
        "discounted Web Risk URL finding when the flagged URL is the same article/page URL"
        in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert (
        "discounted image/video signal when visual findings are likely instructional"
        in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert (
        "If you escalate beyond the weakest raw signals"
        in RECOMMENDATION_SYSTEM_PROMPT
    )
    assert "set `divergences: []`" in RECOMMENDATION_SYSTEM_PROMPT
    assert "Do not fabricate" in RECOMMENDATION_SYSTEM_PROMPT


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
            top_signals=["inconclusive: https://cdn.example/video.mp4"],
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
    assert payload["video_moderation_matches"][0]["sampling_inconclusive"] is True
    assert result.level != SafetyLevel.UNSAFE
    assert result.top_signals == ["inconclusive: https://cdn.example/video.mp4"]


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
            signal_source="text",
            signal_detail="OpenAI moderation flagged sexual-health keyword match",
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
            signal_source="web_risk",
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
            signal_source="combined",
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
