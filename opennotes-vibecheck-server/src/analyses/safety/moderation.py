"""Harmful-content moderation capability for vibecheck-server.

Ported from opennotes-server/src/bulk_content_scan/capabilities/moderation.py
and adapted to operate on a Firecrawl-extracted `Utterance` (text-only for POC).
The multimodal branch from the server is intentionally removed because
Firecrawl utterances are always text.
"""

from __future__ import annotations

from collections import defaultdict

from src.analyses.safety._schemas import HarmfulContentMatch
from src.config import get_settings
from src.monitoring import get_logger
from src.services.openai_moderation import OpenAIModerationService
from src.utterances.chunking_service import Chunk, get_chunking_service
from src.utterances.schema import Utterance

logger = get_logger(__name__)


class OpenAIModerationTransientError(Exception):
    """Raised when the OpenAI moderation API call fails.

    The slot-level orchestrator (`moderation_slot.run_safety_moderation`) treats
    this as a provider failure and combines it with the parallel GCP NL result
    — matching the .08 GCP transient-error pattern (codex P1.5).
    """


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
) -> list[HarmfulContentMatch]:
    """Run OpenAI content moderation on utterance chunks in one request.

    OpenAI's moderation API accepts an array input and returns one result per
    input in order. The returned list contains only flagged chunk matches plus
    an aggregate whole-utterance match for any multi-chunk utterance with at
    least one flagged chunk.

    Raises `OpenAIModerationTransientError` when the moderation API call fails
    so the slot orchestrator can decide how to combine with the parallel GCP
    result (previously this swallowed and returned all-Nones, which made
    "both providers failed" undetectable).
    """
    if not utterances:
        return []
    if moderation_service is None:
        logger.warning("Moderation service not configured")
        return []

    settings = get_settings()
    chunking_service = get_chunking_service(settings)
    scanable: list[tuple[int, Utterance, Chunk]] = []
    chunk_count_by_utterance: dict[int, int] = {}
    for utterance_index, utterance in enumerate(utterances):
        chunks = (
            [
                Chunk(
                    text=utterance.text or "",
                    start_offset=0,
                    end_offset=len(utterance.text or ""),
                    chunk_idx=0,
                    chunk_count=1,
                )
            ]
            if not settings.VIBECHECK_MODERATION_CHUNK_ENABLED
            else chunking_service.chunk_text(utterance.text or "")
        )
        chunk_count_by_utterance[utterance_index] = len(chunks)
        for chunk in chunks:
            scanable.append((utterance_index, utterance, chunk))

    if not scanable:
        return []

    texts = [chunk.text for _, _, chunk in scanable]
    try:
        results = await moderation_service.moderate_texts(texts)
    except Exception as e:
        logger.warning(
            "Error in bulk content moderation",
            extra={"error": str(e), "batch_size": len(texts)},
        )
        raise OpenAIModerationTransientError(str(e)) from e

    matches: list[HarmfulContentMatch] = []
    flagged_by_utterance: dict[int, list[HarmfulContentMatch]] = defaultdict(list)
    for (orig_idx, utterance, chunk), result in zip(scanable, results, strict=False):
        if result.flagged:
            match = HarmfulContentMatch(
                source="openai",
                utterance_id=utterance.utterance_id or "",
                utterance_text=chunk.text if chunk.chunk_count > 1 else utterance.text or "",
                max_score=result.max_score,
                categories=result.categories,
                scores=result.scores,
                flagged_categories=result.flagged_categories,
                chunk_idx=chunk.chunk_idx if chunk.chunk_count > 1 else None,
                chunk_count=chunk.chunk_count,
            )
            matches.append(match)
            if chunk.chunk_count > 1:
                flagged_by_utterance[orig_idx].append(match)

    for orig_idx, chunk_matches in flagged_by_utterance.items():
        if not chunk_matches:
            continue
        utterance = utterances[orig_idx]
        matches.append(
            _aggregate_matches(
                utterance,
                chunk_matches,
                chunk_count=chunk_count_by_utterance[orig_idx],
            )
        )

    return matches


def _aggregate_matches(
    utterance: Utterance,
    chunk_matches: list[HarmfulContentMatch],
    *,
    chunk_count: int,
) -> HarmfulContentMatch:
    scores: dict[str, float] = {}
    categories: dict[str, bool] = {}
    flagged: list[str] = []
    for match in chunk_matches:
        for name, score in match.scores.items():
            scores[name] = max(scores.get(name, 0.0), score)
        for name, hit in match.categories.items():
            categories[name] = categories.get(name, False) or hit
        for name in match.flagged_categories:
            if name not in flagged:
                flagged.append(name)

    return HarmfulContentMatch(
        source="openai",
        utterance_id=utterance.utterance_id or "",
        utterance_text=utterance.text or "",
        max_score=max((match.max_score for match in chunk_matches), default=0.0),
        categories=categories,
        scores=scores,
        flagged_categories=flagged,
        chunk_idx=None,
        chunk_count=chunk_count,
    )


__all__ = [
    "OpenAIModerationTransientError",
    "check_content_moderation",
    "check_content_moderation_bulk",
]
