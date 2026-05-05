from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.llm_config.constants import get_default_model_for_provider
from src.llm_config.model_id import ModelId
from src.url_content_scan.safety_schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)

_logger = logging.getLogger(__name__)

RECOMMENDATION_SYSTEM_PROMPT = """You synthesize the safety findings for one scanned page.
Inputs are already-filtered safety matches from four analyses: text moderation,
Web Risk, image SafeSearch, and video SafeSearch. Return one SafetyRecommendation.

Use these levels:
- safe: all available inputs are clear.
- caution: partial data, inconclusive sampling, or one isolated flag.
- unsafe: verified high-risk signals such as Web Risk MALWARE, multiple high-score text flags,
  or high image/video max_likelihood scores from real frames.

Important caveats:
- A video match with max_likelihood=1.0 and no frame_findings means sampling was
  inconclusive, not verified unsafe visual content. Treat it as caution unless other
  verified signals justify unsafe, and describe it with an "inconclusive:" top signal.
- Echo the unavailable_inputs list exactly in the output."""


@dataclass(frozen=True)
class SafetyRecommendationInputs:
    harmful_content_matches: list[HarmfulContentMatch]
    web_risk_findings: list[WebRiskFinding]
    image_moderation_matches: list[ImageModerationMatch]
    video_moderation_matches: list[VideoModerationMatch]
    unavailable_inputs: list[str]


RecommendationRunner = Callable[[SafetyRecommendationInputs], Awaitable[SafetyRecommendation]]

recommendation_agent: Agent[None, SafetyRecommendation] = Agent(
    name="url-scan-safety-recommendation",
    output_type=SafetyRecommendation,
    instrument=True,
)


async def run_safety_recommendation(
    inputs: SafetyRecommendationInputs,
    *,
    agent_runner: RecommendationRunner | None = None,
) -> SafetyRecommendation:
    if agent_runner is not None:
        return await agent_runner(inputs)
    try:
        return await _run_default_recommendation_agent(inputs)
    except Exception:
        _logger.warning("Default safety recommendation agent failed; using fallback", exc_info=True)
        return _fallback_recommendation(inputs)


async def _run_default_recommendation_agent(
    inputs: SafetyRecommendationInputs,
) -> SafetyRecommendation:
    result = await recommendation_agent.run(
        _serialize_inputs(inputs),
        model=_default_recommendation_model(),
        instructions=RECOMMENDATION_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )
    return cast(SafetyRecommendation, result.output)


def _default_recommendation_model() -> Any:
    return ModelId.from_pydantic_ai(
        get_default_model_for_provider("vertex_ai")
    ).to_pydantic_ai_model()


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _serialize_inputs(inputs: SafetyRecommendationInputs) -> str:
    video_matches: list[dict[str, Any]] = []
    for match in inputs.video_moderation_matches:
        dumped = cast(dict[str, Any], _model_dump(match))
        dumped["sampling_inconclusive"] = (
            match.max_likelihood == 1.0 and len(match.frame_findings) == 0
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


def _fallback_recommendation(inputs: SafetyRecommendationInputs) -> SafetyRecommendation:
    top_signals: list[str] = []
    unsafe, caution = _collect_web_risk_signals(inputs.web_risk_findings, top_signals)
    unsafe, caution = _collect_text_signals(
        inputs.harmful_content_matches, top_signals, unsafe=unsafe, caution=caution
    )
    unsafe, caution = _collect_image_signals(
        inputs.image_moderation_matches, top_signals, unsafe=unsafe, caution=caution
    )
    unsafe, caution = _collect_video_signals(
        inputs.video_moderation_matches, top_signals, unsafe=unsafe, caution=caution
    )
    caution = caution or bool(inputs.unavailable_inputs)

    if unsafe:
        level = SafetyLevel.UNSAFE
        rationale = "Verified high-risk signals were found in the available safety checks."
    elif caution:
        level = SafetyLevel.CAUTION
        rationale = "Some safety checks were flagged, partial, or inconclusive."
    else:
        level = SafetyLevel.SAFE
        rationale = "All available safety checks were clear."

    return SafetyRecommendation(
        level=level,
        rationale=rationale,
        top_signals=top_signals[:3],
        unavailable_inputs=list(inputs.unavailable_inputs),
    )


def _collect_web_risk_signals(
    findings: list[WebRiskFinding],
    top_signals: list[str],
) -> tuple[bool, bool]:
    unsafe = False
    caution = False
    for finding in findings:
        for threat_type in finding.threat_types:
            top_signals.append(f"{threat_type} on {finding.url}")
            if threat_type in {"MALWARE", "SOCIAL_ENGINEERING"}:
                unsafe = True
            else:
                caution = True
    return unsafe, caution


def _collect_text_signals(
    matches: list[HarmfulContentMatch],
    top_signals: list[str],
    *,
    unsafe: bool,
    caution: bool,
) -> tuple[bool, bool]:
    high_text_matches = [match for match in matches if match.max_score >= 0.9]
    if len(high_text_matches) >= 2:
        top_signals.append("multiple high-confidence harmful-content utterances")
        return True, caution
    if matches:
        top_signals.append("flagged harmful-content utterances")
        return unsafe, True
    return unsafe, caution


def _collect_image_signals(
    matches: list[ImageModerationMatch],
    top_signals: list[str],
    *,
    unsafe: bool,
    caution: bool,
) -> tuple[bool, bool]:
    if any(match.max_likelihood >= 0.9 for match in matches):
        top_signals.append("high-confidence image SafeSearch signals")
        return True, caution
    if any(match.flagged for match in matches):
        top_signals.append("flagged image SafeSearch signals")
        return unsafe, True
    return unsafe, caution


def _collect_video_signals(
    matches: list[VideoModerationMatch],
    top_signals: list[str],
    *,
    unsafe: bool,
    caution: bool,
) -> tuple[bool, bool]:
    if any(match.max_likelihood == 1.0 and not match.frame_findings for match in matches):
        top_signals.append("inconclusive video sampling")
        return unsafe, True
    if any(match.max_likelihood >= 0.9 for match in matches):
        top_signals.append("high-confidence video SafeSearch signals")
        return True, caution
    if any(match.flagged for match in matches):
        top_signals.append("flagged video SafeSearch signals")
        return unsafe, True
    return unsafe, caution
