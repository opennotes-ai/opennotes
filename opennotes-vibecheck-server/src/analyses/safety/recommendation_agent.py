"""Aggregate safety recommendation agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, cast

import logfire

from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
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
- Echo the unavailable_inputs list exactly in the output.
- Use the `divergences` field to record how your final verdict differs from the raw
  signals in inputs:
- If you discount a raw signal due to context, add direction="discounted" and include:
  - discounted sensitive-topic signal when the text is a sensitive topic that is the
    page subject or intended educational framing (ex: public-health article),
  - discounted Web Risk URL finding when the flagged URL is the same article/page URL
    under analysis,
  - discounted image/video signal when visual findings are likely instructional,
    educational, documentary, or in-domain context.
- If you escalate beyond the weakest raw signals, add direction="escalated" when
  combined low-signal cues or context justify caution/unsafe.
  - Ex: multiple mild signals together (topic+POTENTIALLY_HARMFUL_APPLICATION+low
    visual concern) producing caution,
  - Ex: weak visual score plus weak textual cues and in-context risk alignment.
- If your final level and rationale align with the raw signals, set `divergences: []`.
- Only emit divergences that are directly supported by inputs. Do not fabricate
  divergences."""


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


_RAW_TEXT_MOD_SCORE_RE = re.compile(
    r"^(?:text\s*:\s*)?[a-z][a-z /-]*\s+(?:score\s+)?\d+\.\d+$",
    re.IGNORECASE,
)
_VISION_FLOAT_RE = re.compile(
    r"(adult|violence|racy|medical|spoof)\s+(max_likelihood|score)\s+\d+\.\d+",
    re.IGNORECASE,
)
_VISION_ENUM_RE = re.compile(
    r"\b(VERY_LIKELY|LIKELY|POSSIBLE|UNLIKELY|VERY_UNLIKELY)\b",
)
_SANITIZER_PLACEHOLDER = "Verified concern requires review"
_PLACEHOLDER_LEVELS = {SafetyLevel.CAUTION, SafetyLevel.UNSAFE}


def _is_raw_signal(value: str) -> bool:
    stripped = value.strip()
    if _RAW_TEXT_MOD_SCORE_RE.match(stripped):
        return True
    if _VISION_FLOAT_RE.search(stripped):
        return True
    return bool(_VISION_ENUM_RE.search(stripped))


def _sanitize_top_signals(recommendation: SafetyRecommendation) -> SafetyRecommendation:
    original = list(recommendation.top_signals)
    kept: list[str] = []
    for entry in original:
        if _is_raw_signal(entry):
            logfire.warning(
                "safety_recommendation_top_signal_stripped",
                level=recommendation.level.value,
                raw_value=entry,
            )
            continue
        kept.append(entry)
    if not kept and original and recommendation.level in _PLACEHOLDER_LEVELS:
        kept = [_SANITIZER_PLACEHOLDER]
    if kept == original:
        return recommendation
    return recommendation.model_copy(
        update={
            "top_signals": kept,
            "divergences": recommendation.divergences,
        }
    )


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
    output = cast(SafetyRecommendation, result.output)
    return _sanitize_top_signals(output)
