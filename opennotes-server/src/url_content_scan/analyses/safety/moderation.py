from __future__ import annotations

import asyncio

from src.bulk_content_scan.openai_moderation_service import (
    ModerationResult,
    OpenAIModerationService,
)
from src.url_content_scan.safety_schemas import HarmfulContentMatch
from src.url_content_scan.schemas import SafetySection
from src.url_content_scan.utterances.schema import Utterance

_MAX_MODERATION_CONCURRENCY = 8


async def run_safety_moderation(
    utterances: list[Utterance],
    *,
    moderation_service: OpenAIModerationService | object | None,
    max_concurrency: int = _MAX_MODERATION_CONCURRENCY,
) -> SafetySection:
    if not utterances:
        return SafetySection()
    if moderation_service is None:
        return SafetySection()

    scannable = [utterance for utterance in utterances if utterance.text.strip()]
    if not scannable:
        return SafetySection()

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _moderate_one(utterance: Utterance) -> ModerationResult:
        async with semaphore:
            return await moderation_service.moderate_text(utterance.text)

    results = await asyncio.gather(*(_moderate_one(utterance) for utterance in scannable))
    matches: list[HarmfulContentMatch] = []
    for utterance, result in zip(scannable, results, strict=False):
        if not result.flagged:
            continue
        matches.append(
            HarmfulContentMatch(
                utterance_id=utterance.utterance_id or "",
                utterance_text=utterance.text,
                max_score=result.max_score,
                categories=result.categories,
                scores=result.scores,
                flagged_categories=result.flagged_categories,
                source="openai",
            )
        )

    return SafetySection(harmful_content_matches=matches)
