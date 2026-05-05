from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.url_content_scan.safety_schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)


@dataclass(frozen=True)
class SafetyRecommendationInputs:
    harmful_content_matches: list[HarmfulContentMatch]
    web_risk_findings: list[WebRiskFinding]
    image_moderation_matches: list[ImageModerationMatch]
    video_moderation_matches: list[VideoModerationMatch]
    unavailable_inputs: list[str]


RecommendationRunner = Callable[[SafetyRecommendationInputs], Awaitable[SafetyRecommendation]]


async def run_safety_recommendation(
    inputs: SafetyRecommendationInputs,
    *,
    agent_runner: RecommendationRunner | None = None,
) -> SafetyRecommendation:
    if agent_runner is not None:
        return await agent_runner(inputs)
    return _fallback_recommendation(inputs)


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
