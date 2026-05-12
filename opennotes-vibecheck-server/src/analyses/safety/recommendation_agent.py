"""Aggregate safety recommendation agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.config import Settings
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot

RECOMMENDATION_SYSTEM_PROMPT = """You synthesize the safety findings for one scraped page.
Inputs are already-filtered safety matches from four analyses: text moderation,
Web Risk, image SafeSearch, and video SafeSearch. Return one SafetyRecommendation.

Use these levels:
- safe: all available inputs are clear.
- mild: one verified low-severity signal, such as a topic-match-only moderation
  hit, one isolated Web Risk POTENTIALLY_HARMFUL_APPLICATION finding, or one
  low image/video max_likelihood score from verified frames.
- caution: partial data, unavailable inputs, inconclusive sampling, or multiple
  low-severity signals together.
- unsafe: verified high-risk signals such as Web Risk MALWARE, multiple high-score text flags,
  or high image/video max_likelihood scores from real frames.

Important caveats:
- top_signals entries must be short human-readable noun phrases or sentences;
  never raw category names, float scores, or enum labels. Prefer concise phrases
  such as "Violent topics", "Adult imagery", or "Phishing link". For
  false-positive moderation, use
  "Text moderation flags triggered, but judged to be false positives."
- In false-positive-heavy caution cases, do not lead top_signals with dismissed raw moderation scores.
  Examples of dismissed raw scores include "text: Legal 1.0", "text: Firearms 0.98", or
  "text: Illicit Drugs 0.93". If caution still applies, top_signals[0] must name
  the remaining verified concern, such as "Repeated low-severity toxicity" or
  "Mild violent rhetoric".
- Keep raw category names and float scores in rationale only when they help
  explain the decision; do not put them in top_signals.
- Vision SafeSearch enum labels are not available downstream. Describe image/video signals
  in rationale with float scores only, such as "adult max_likelihood 0.91";
  never mention enum labels like VERY_LIKELY.
- A video match with max_likelihood=1.0 and no segment_findings means sampling was
  inconclusive, not verified unsafe visual content. Treat it as caution unless other
  verified signals justify unsafe, and describe it with a human-readable top signal
  such as "Video sampling inconclusive."
- Echo the unavailable_inputs list exactly in the output."""


@dataclass
class SafetyRecommendationInputs:
    harmful_content_matches: list[HarmfulContentMatch]
    web_risk_findings: list[WebRiskFinding]
    image_moderation_matches: list[ImageModerationMatch]
    video_moderation_matches: list[VideoModerationMatch]
    unavailable_inputs: list[str]


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _serialize_inputs(inputs: SafetyRecommendationInputs) -> str:
    video_matches: list[dict[str, Any]] = []
    for match in inputs.video_moderation_matches:
        dumped = cast(dict[str, Any], _model_dump(match))
        dumped["sampling_inconclusive"] = (
            match.max_likelihood == 1.0 and len(match.segment_findings) == 0
        )
        video_matches.append(dumped)

    payload = {
        "harmful_content_matches": [_model_dump(match) for match in inputs.harmful_content_matches],
        "web_risk_findings": [_model_dump(finding) for finding in inputs.web_risk_findings],
        "image_moderation_matches": [
            _model_dump(match) for match in inputs.image_moderation_matches
        ],
        "video_moderation_matches": video_matches,
        "unavailable_inputs": list(inputs.unavailable_inputs),
    }
    return json.dumps(payload)


async def run_safety_recommendation(
    inputs: SafetyRecommendationInputs,
    settings: Settings,
) -> SafetyRecommendation:
    agent = cast(
        Any,
        build_agent(
            settings,
            output_type=SafetyRecommendation,
            system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
            name="vibecheck.safety_recommendation",
            tier="synthesis",
        ),
    )
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, _serialize_inputs(inputs))
    return cast(SafetyRecommendation, result.output)
