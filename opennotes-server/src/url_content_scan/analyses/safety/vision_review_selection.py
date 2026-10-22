from __future__ import annotations

from src.url_content_scan.analyses.safety.recommendation import SafetyRecommendationInputs
from src.url_content_scan.analyses.safety.vision import FLAG_THRESHOLD
from src.url_content_scan.safety_schemas import VideoModerationMatch


def _has_verified_video_signal(match: VideoModerationMatch) -> bool:
    return any(
        finding.flagged or finding.max_likelihood >= FLAG_THRESHOLD
        for finding in match.frame_findings
    )


def select_images_for_vision_review(
    inputs: SafetyRecommendationInputs,
    *,
    cap: int,
) -> list[str]:
    """Pick which flagged image URLs to send for Gemini vision re-review.

    Returns flagged image URLs when the image flag is load-bearing for the
    verdict — i.e., images are the sole/dominant escalation, or are part of
    an additive set of low-severity signals. Returns [] when other signals
    (a verified Web Risk finding, a verified video segment) would already
    produce caution/unsafe regardless of image evidence — running vision
    review in that case wastes Vertex calls without changing the outcome.

    A "flagged image" is one with ``match.flagged is True`` OR
    ``match.max_likelihood >= FLAG_THRESHOLD``.
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

    if inputs.web_risk_findings:
        return []
    if any(_has_verified_video_signal(m) for m in inputs.video_moderation_matches):
        return []

    return flagged_urls[:cap]
