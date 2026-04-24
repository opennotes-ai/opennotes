from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import pytest

from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
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


async def test_run_safety_recommendation_serializes_inputs_for_agent(monkeypatch):
    agent = StubAgent(
        SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="A moderation match was found.",
            top_signals=["topic-match content score 0.62"],
        )
    )
    build_calls = []

    def fake_build_agent(settings, *, output_type, system_prompt):
        build_calls.append((settings, output_type, system_prompt))
        return agent

    monkeypatch.setattr(
        "src.analyses.safety.recommendation_agent.build_agent",
        fake_build_agent,
    )
    settings = cast(Settings, cast(object, SimpleNamespace()))

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
    assert build_calls == [(settings, SafetyRecommendation, RECOMMENDATION_SYSTEM_PROMPT)]
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
    settings = cast(Settings, cast(object, SimpleNamespace()))

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[
                VideoModerationMatch(
                    utterance_id="u1",
                    video_url="https://cdn.example/video.mp4",
                    frame_findings=[],
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
        settings=cast(Settings, cast(object, SimpleNamespace())),
    )

    assert result.level == expected
    assert result.unavailable_inputs == inputs.unavailable_inputs
