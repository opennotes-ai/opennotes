"""GCP Natural Language moderateText client.

Calls `POST https://language.googleapis.com/v2/documents:moderateText` for
each utterance, bounded by a concurrency semaphore of 8, and emits
`HarmfulContentMatch` with `source="gcp"` for utterances above the threshold.

Transient errors (429, 5xx, network, missing ADC) raise
`GcpModerationTransientError` so the slot worker at .12 can catch and retry.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

import httpx

from src.analyses.safety._schemas import HarmfulContentMatch
from src.config import Settings
from src.monitoring import external_api_span
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token
from src.utterances.chunking_service import Chunk, get_chunking_service
from src.utterances.schema import Utterance

MODERATE_TEXT_URL = "https://language.googleapis.com/v2/documents:moderateText"


class GcpModerationTransientError(Exception):
    """Auth/5xx/429/network — slot worker catches and fails retryable."""


async def moderate_texts_gcp(
    utterances: list[Utterance],
    *,
    httpx_client: httpx.AsyncClient,
    settings: Settings | None = None,
    threshold: float = 0.5,
) -> list[HarmfulContentMatch]:
    if not utterances:
        return []
    token = get_access_token(CLOUD_PLATFORM_SCOPE)
    if not token:
        raise GcpModerationTransientError("ADC token unavailable")
    sem = asyncio.Semaphore(8)

    chunking_service = await get_chunking_service(settings)
    scanable: list[tuple[int, Utterance, Chunk]] = []
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
            if settings is not None and not settings.VIBECHECK_GCP_MODERATION_CHUNK_ENABLED
            else chunking_service.chunk_text(utterance.text or "")
        )
        for chunk in chunks:
            if chunk.text.strip():
                scanable.append((utterance_index, utterance, chunk))

    if not scanable:
        return []

    async def one(utt: Utterance, chunk: Chunk) -> HarmfulContentMatch | None:
        if not chunk.text.strip():
            return None
        async with sem:
            with external_api_span("gcp_nl", "documents.moderate_text") as obs:
                try:
                    r = await httpx_client.post(
                        MODERATE_TEXT_URL,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={"document": {"type": "PLAIN_TEXT", "content": chunk.text}},
                        timeout=20.0,
                    )
                except httpx.HTTPError as exc:
                    obs.set_error_category("network")
                    raise GcpModerationTransientError("gcp-moderation network") from exc
                obs.set_response_status(r.status_code)
                if r.status_code == 429:
                    obs.set_error_category("rate_limited")
                    raise GcpModerationTransientError(f"gcp-moderation {r.status_code}")
                if r.status_code >= 500:
                    obs.set_error_category("upstream")
                    raise GcpModerationTransientError(f"gcp-moderation {r.status_code}")
                r.raise_for_status()
                payload = r.json()
                cats = payload.get("moderationCategories") or []
                if not cats:
                    return None
                scores: dict[str, float] = {
                    str(c.get("name", "")): float(c.get("confidence", 0.0))
                    for c in cats
                    if isinstance(c, dict)
                }
                if not scores:
                    return None
                max_score = max(scores.values())
                if max_score <= threshold:
                    return None
                categories = {name: score > threshold for name, score in scores.items()}
                flagged = [name for name, hit in categories.items() if hit]
                obs.add_flagged(1)
                return HarmfulContentMatch(
                    source="gcp",
                    utterance_id=utt.utterance_id or "",
                    utterance_text=chunk.text if chunk.chunk_count > 1 else utt.text or "",
                    max_score=max_score,
                    categories=categories,
                    scores=scores,
                    flagged_categories=flagged,
                    chunk_idx=chunk.chunk_idx if chunk.chunk_count > 1 else None,
                    chunk_count=chunk.chunk_count,
                )

    chunk_results = list(await asyncio.gather(*(one(u, c) for _, u, c in scanable)))
    matches: list[HarmfulContentMatch] = []
    flagged_by_utterance: dict[int, list[HarmfulContentMatch]] = defaultdict(list)
    for (utterance_index, _utterance, chunk), result in zip(scanable, chunk_results, strict=True):
        if result is None:
            continue
        matches.append(result)
        if chunk.chunk_count > 1:
            flagged_by_utterance[utterance_index].append(result)

    for utterance_index, chunk_matches in flagged_by_utterance.items():
        matches.append(_aggregate_matches(utterances[utterance_index], chunk_matches))

    return matches


def _aggregate_matches(
    utterance: Utterance, chunk_matches: list[HarmfulContentMatch]
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
        source="gcp",
        utterance_id=utterance.utterance_id or "",
        utterance_text=utterance.text or "",
        max_score=max((match.max_score for match in chunk_matches), default=0.0),
        categories=categories,
        scores=scores,
        flagged_categories=flagged,
        chunk_idx=None,
        chunk_count=chunk_matches[0].chunk_count,
    )
