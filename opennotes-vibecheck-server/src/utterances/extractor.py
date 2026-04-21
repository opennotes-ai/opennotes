from __future__ import annotations

from src.firecrawl_client import FirecrawlClient

from .schema import UtterancesPayload


class UtteranceExtractionError(Exception):
    """Raised when Firecrawl-based utterance extraction fails."""


async def extract_utterances(url: str, client: FirecrawlClient) -> UtterancesPayload:
    """Extract a UtterancesPayload for `url` via Firecrawl /v2/extract.

    Firecrawl validates the response against UtterancesPayload's schema, so we
    trust the structure but defensively deduplicate and regenerate missing or
    duplicate utterance_ids using a stable, deterministic rule.
    """
    try:
        payload = await client.extract(url, UtterancesPayload)
    except Exception as exc:
        raise UtteranceExtractionError(str(exc)) from exc

    if not isinstance(payload, UtterancesPayload):
        raise UtteranceExtractionError(
            f"firecrawl returned unexpected payload type: {type(payload).__name__}"
        )

    seen: set[str] = set()
    for i, utterance in enumerate(payload.utterances):
        uid = utterance.utterance_id
        if not uid or uid in seen:
            utterance.utterance_id = (
                f"{utterance.kind}-{i}-{hash(utterance.text) & 0xFFFFFFFF:08x}"
            )
        seen.add(utterance.utterance_id or "")

    return payload
