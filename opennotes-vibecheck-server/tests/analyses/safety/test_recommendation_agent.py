from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.safety.recommendation_agent import (
    RECOMMENDATION_SYSTEM_PROMPT,
    SafetyRecommendationInputs,
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


async def test_run_safety_recommendation_serializes_inputs_for_agent(monkeypatch):
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="A moderation match was found.",
            top_signals=["topic-match content score 0.62"],
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
            top_signals=["topic-match content score 0.51"],
        )
    )
    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        lambda *args, **kwargs: agent,
    )

    result = await run_safety_recommendation(inputs, settings=Settings())

    assert result.level == SafetyLevel.MILD
    assert result.top_signals == ["topic-match content score 0.51"]


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
