"""GCP Natural Language moderateText client.

Calls `POST https://language.googleapis.com/v2/documents:moderateText` for
each utterance, bounded by a concurrency semaphore of 8, and emits
`HarmfulContentMatch` with `source="gcp"` for utterances above the threshold.

Transient errors (429, 5xx, network, missing ADC) raise
`GcpModerationTransientError` so the slot worker at .12 can catch and retry.
"""
from __future__ import annotations

import asyncio

import httpx

from src.analyses.safety._schemas import HarmfulContentMatch
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token
from src.utterances.schema import Utterance

MODERATE_TEXT_URL = "https://language.googleapis.com/v2/documents:moderateText"


class GcpModerationTransientError(Exception):
    """Auth/5xx/429/network — slot worker catches and fails retryable."""


async def moderate_texts_gcp(
    utterances: list[Utterance],
    *,
    httpx_client: httpx.AsyncClient,
    threshold: float = 0.5,
) -> list[HarmfulContentMatch | None]:
    if not utterances:
        return []
    token = get_access_token(CLOUD_PLATFORM_SCOPE)
    if not token:
        raise GcpModerationTransientError("ADC token unavailable")
    sem = asyncio.Semaphore(8)

    async def one(utt: Utterance) -> HarmfulContentMatch | None:
        if not (utt.text or "").strip():
            return None
        async with sem:
            r = await httpx_client.post(
                MODERATE_TEXT_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"document": {"type": "PLAIN_TEXT", "content": utt.text}},
                timeout=10.0,
            )
            if r.status_code == 429 or r.status_code >= 500:
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
            return HarmfulContentMatch(
                source="gcp",
                utterance_id=utt.utterance_id or "",
                max_score=max_score,
                categories=categories,
                scores=scores,
                flagged_categories=flagged,
            )

    return list(await asyncio.gather(*(one(u) for u in utterances)))
