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
    """Thin single-utterance wrapper over ``check_content_moderation_bulk``."""
    results = await check_content_moderation_bulk([utterance], moderation_service)
    return results[0] if results else None


async def check_content_moderation_bulk(
    utterances: list[Utterance],
    moderation_service: OpenAIModerationService | None,
) -> list[HarmfulContentMatch | None]:
    """Run OpenAI content moderation on all utterances in ONE request.

    OpenAI's moderation API accepts an array input and returns one result per
    input in order. Index-aligned output; `None` in slot i means unflagged (or
    that utterance lacked text / id).
    """
    out: list[HarmfulContentMatch | None] = [None for _ in utterances]
    if not utterances:
        return out
    if moderation_service is None:
        logger.warning("Moderation service not configured")
        return out

    scanable: list[tuple[int, Utterance]] = [
        (i, u) for i, u in enumerate(utterances) if (u.text or "").strip()
    ]
    if not scanable:
        return out

    texts = [u.text for _, u in scanable]
    try:
        results = await moderation_service.moderate_texts(texts)
    except Exception as e:
        logger.warning(
            "Error in bulk content moderation",
            extra={"error": str(e), "batch_size": len(texts)},
        )
        return out

    for (orig_idx, utterance), result in zip(scanable, results, strict=False):
        if result.flagged:
            out[orig_idx] = HarmfulContentMatch(
                source="openai",
                utterance_id=utterance.utterance_id or "",
                max_score=result.max_score,
                categories=result.categories,
                scores=result.scores,
                flagged_categories=result.flagged_categories,
            )
    return out


__all__ = ["check_content_moderation", "check_content_moderation_bulk"]
