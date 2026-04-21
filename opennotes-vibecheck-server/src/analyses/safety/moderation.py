"""Harmful-content moderation capability for vibecheck-server.

Ported from opennotes-server/src/bulk_content_scan/capabilities/moderation.py
and adapted to operate on a Firecrawl-extracted `Utterance` (text-only for POC).
The multimodal branch from the server is intentionally removed because
Firecrawl utterances are always text.
"""

from __future__ import annotations

from src.analyses.safety._schemas import HarmfulContentMatch
from src.monitoring import get_logger
from src.services.openai_moderation import OpenAIModerationService
from src.utterances.schema import Utterance

logger = get_logger(__name__)


async def check_content_moderation(
    utterance: Utterance,
    moderation_service: OpenAIModerationService | None,
) -> HarmfulContentMatch | None:
    """Run OpenAI content moderation on a single utterance.

    Args:
        utterance: The Firecrawl-extracted utterance to moderate.
        moderation_service: OpenAIModerationService instance, or None if not configured.

    Returns:
        HarmfulContentMatch if the utterance was flagged, None otherwise.
        Never raises — OpenAI API errors are logged and swallowed.
    """
    if moderation_service is None:
        logger.warning(
            "Moderation service not configured",
            extra={"utterance_id": utterance.utterance_id},
        )
        return None

    try:
        moderation_result = await moderation_service.moderate_text(utterance.text)

        if moderation_result.flagged:
            return HarmfulContentMatch(
                utterance_id=utterance.utterance_id or "",
                max_score=moderation_result.max_score,
                categories=moderation_result.categories,
                scores=moderation_result.scores,
                flagged_categories=moderation_result.flagged_categories,
            )
    except Exception as e:
        logger.warning(
            "Error in content moderation capability",
            extra={
                "utterance_id": utterance.utterance_id,
                "error": str(e),
            },
        )

    return None
