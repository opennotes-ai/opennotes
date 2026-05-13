from __future__ import annotations

from src.analyses.safety.recommendation_agent import SafetyRecommendationInputs
from src.analyses.safety.vision_client import FLAG_THRESHOLD


def select_images_for_vision_review(
    inputs: SafetyRecommendationInputs,
    *,
    cap: int,
) -> list[str]:
    """Pick which flagged image URLs to send to Gemini vision review.

    Returns flagged image URLs (preserving input order, truncated to `cap`)
    when any image is flagged. A "flagged image" is one with
    `match.flagged is True` OR `match.max_likelihood >= FLAG_THRESHOLD`
    (mirrors `recommendation_agent._has_guardrail_downgrade_blocker`).

    Returns an empty list when no images are flagged or when `cap <= 0`.
    Other signals (text matches, web risk findings, verified video signals,
    unavailable inputs) do not change the selection — the recommendation
    agent decides discounting downstream.
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

    return flagged_urls[:cap]
