from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentedModel
from pydantic_ai.settings import ModelSettings

from src.config import Settings, get_settings
from src.url_content_scan.analyses.claims.dedup import ExtractedClaim
from src.url_content_scan.observability import (
    url_scan_extractor_instrumentation,
    url_scan_instrumentation,
)
from src.url_content_scan.utterances.schema import Utterance

_SYSTEM_PROMPT = """\
You extract atomic verifiable factual claims from short user-generated text.

Rules:
- Extract only factual claims that could be checked against external evidence.
- Omit opinions, preferences, questions, jokes, commands, and emotional reactions.
- Rewrite each claim as a concise standalone assertion.
- Split compound assertions into separate atomic claims when needed.
- Return an empty list when the utterance contains no verifiable claim.
"""


class _ClaimExtractionResponse(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


_CLAIM_EXTRACTION_AGENT: Agent[None, _ClaimExtractionResponse] = Agent(
    name="url-content-scan-claims-extract",
    output_type=_ClaimExtractionResponse,
    capabilities=[url_scan_instrumentation()],
)


async def extract_claims(
    utterance: Utterance,
    *,
    settings: Settings | None = None,
) -> list[ExtractedClaim]:
    text = utterance.text.strip()
    if not text:
        return []

    cfg = settings or get_settings()
    base_model = cfg.DEFAULT_MINI_MODEL.to_pydantic_ai_model()
    instrumented_model = InstrumentedModel(base_model, url_scan_extractor_instrumentation(cfg))
    result = await _CLAIM_EXTRACTION_AGENT.run(
        text,
        model=instrumented_model,
        instructions=_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )
    return result.output.claims


__all__ = [
    "ExtractedClaim",
    "extract_claims",
]
