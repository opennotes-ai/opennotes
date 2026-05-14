from __future__ import annotations

from src.analyses.safety._schemas import VideoModerationMatch
from src.analyses.safety.recommendation_agent import SafetyRecommendationInputs
from src.analyses.safety.vision_client import FLAG_THRESHOLD


def _has_verified_video_signal(match: VideoModerationMatch) -> bool:
    return any(
        finding.flagged or finding.max_likelihood >= FLAG_THRESHOLD
        for finding in match.segment_findings
    )


def select_images_for_vision_review(
    inputs: SafetyRecommendationInputs,
    *,
    cap: int,
) -> list[str]:
    """Pick which flagged image URLs to send to Gemini vision review.

    Returns flagged image URLs when the image flag is load-bearing for the
    verdict — i.e., images are the sole/dominant escalation, or are part of
    an additive set of low-severity signals. Returns [] when other signals
    (a verified Web Risk finding, a verified video segment) would already
    produce caution/unsafe regardless of image evidence — running vision
    review in that case wastes Vertex calls without changing the outcome.

    A "flagged image" is one with `match.flagged is True` OR
    `match.max_likelihood >= FLAG_THRESHOLD` (mirrors
    `recommendation_agent._has_guardrail_downgrade_blocker`).
    """
    if cap <= 0:
        return []

    flagged_urls = [
        match.image_url
        for match in inputs.image_moderation_matches
        if match.flagged or match.max_likelihood >= FLAG_THRESHOLD
    ]
    if not flagged_urls:
        return []

    # Skip vision review when another verified signal already determines
    # the verdict regardless of image evidence. Web Risk findings (after
    # same-page filtering upstream) and verified video segments are
    # treated as load-bearing on their own.
    if inputs.web_risk_findings:
        return []
    if any(_has_verified_video_signal(m) for m in inputs.video_moderation_matches):
        return []

    return flagged_urls[:cap]
