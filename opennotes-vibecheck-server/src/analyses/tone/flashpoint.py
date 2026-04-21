"""Flashpoint detection capability for vibecheck utterances.

Port of ``opennotes-server/src/bulk_content_scan/capabilities/flashpoint.py``
adapted for the vibecheck utterance model.

Behavior:
- Blog-post utterances (empty ``context``, e.g. an ``<article>`` with no
  siblings) short-circuit to ``None`` without invoking the DSPy service:
  there is no conversational context to score.
- Thread/forum comments pass prior-in-time siblings as ``context``.
- Any error from the service returns ``None`` (logged) rather than bubbling.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.monitoring import get_logger
from src.utterances.schema import Utterance

if TYPE_CHECKING:
    from src.analyses.tone._flashpoint_schemas import FlashpointMatch
    from src.services.flashpoint_service import FlashpointDetectionService

logger = get_logger(__name__)


async def detect_flashpoint(
    utterance: Utterance,
    context: list[Utterance],
    service: FlashpointDetectionService | None,
) -> FlashpointMatch | None:
    """Run flashpoint detection on a single utterance.

    Args:
        utterance: The utterance to analyze.
        context: Prior-in-time utterances in the same thread. For blog
            posts this is empty and the function short-circuits to None.
        service: A configured ``FlashpointDetectionService``, or ``None``
            if flashpoint detection is disabled for this deployment.

    Returns:
        ``FlashpointMatch`` when derailment score meets the service
        threshold, otherwise ``None``.
    """
    if service is None:
        logger.debug(
            "Flashpoint service not configured; skipping utterance_id=%s",
            utterance.utterance_id,
        )
        return None

    if not context:
        logger.debug(
            "Empty context (standalone utterance); skipping flashpoint "
            "detection utterance_id=%s kind=%s",
            utterance.utterance_id,
            utterance.kind,
        )
        return None

    try:
        return await service.detect_flashpoint(
            utterance=utterance,
            context=context,
        )
    except Exception as e:
        logger.warning(
            "Error in flashpoint detection capability utterance_id=%s: %s: %s",
            utterance.utterance_id,
            type(e).__name__,
            e,
        )
        return None
