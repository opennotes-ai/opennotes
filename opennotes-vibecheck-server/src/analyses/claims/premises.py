"""Premise extraction for deduped claims.

The implementation here is intentionally pure and deterministic; production
integration is provided through a batch seam that can be swapped to an LLM-based
extractor without changing the callers or tests.

This module exposes a single function used by the async slot:
`build_premises_by_claim`, which attaches premise IDs to eligible claims and
returns a global premises registry.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from src.analyses.claims._claims_schemas import (
    ClaimCategory,
    DedupedClaim,
    Premise,
    PremisesRegistry,
)
from src.config import Settings
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot

logger = logging.getLogger(__name__)

PremiseSeam = Callable[[list[str], Settings], Awaitable[dict[str, list[Any]]]]

_ELIGIBLE_PREMISE_CATEGORIES = {
    ClaimCategory.PREDICTIONS,
    ClaimCategory.SUBJECTIVE,
    ClaimCategory.SELF_CLAIMS,
}


class _PremiseExtractionItem(BaseModel):
    canonical_text: str
    premises: list[str] = Field(default_factory=list, max_length=4)


class _PremiseExtractionResponse(BaseModel):
    results: list[_PremiseExtractionItem] = Field(default_factory=list)


_PREMISE_SYSTEM_PROMPT = (
    "Extract implicit premises for non-factual claims.\n"
    "\n"
    "A premise is a load-bearing assumption a reader could agree or disagree with.\n"
    "Rules:\n"
    "- Return 0-4 high-quality premises per claim.\n"
    "- Keep each premise concise, standalone, and debatable.\n"
    "- Do not produce recursive sub-premises or evidence citations.\n"
    "- Avoid fluffy restatements of the claim.\n"
    "- canonical_text must exactly match one claim from the input."
)


async def infer_premises_batch(
    claim_texts: list[str],
    settings: Settings,
) -> dict[str, list[str]]:
    """Extract 0-4 implicit premises for each claim in one model call."""
    if not claim_texts:
        return {}
    agent = build_agent(
        settings,
        output_type=_PremiseExtractionResponse,
        system_prompt=_PREMISE_SYSTEM_PROMPT,
        name="vibecheck.claims_premises",
        tier="synthesis",
    )
    prompt = "Claims:\n" + "\n".join(f"- {claim_text}" for claim_text in claim_texts)
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, prompt)
    response = result.output
    out: dict[str, list[str]] = {claim_text: [] for claim_text in claim_texts}
    if not isinstance(response, _PremiseExtractionResponse):
        return out
    allowed = set(claim_texts)
    for item in response.results:
        canonical_text = item.canonical_text.strip()
        if canonical_text not in allowed:
            continue
        out[canonical_text] = [
            statement.strip()
            for statement in item.premises[:4]
            if isinstance(statement, str) and statement.strip()
        ]
    return out


def _premise_id(statement: str) -> str:
    """Derive a stable, deterministic premise ID from its text."""
    digest = hashlib.sha1(_premise_key(statement).encode("utf-8")).hexdigest()[:12]
    return f"premise_{digest}"


def _premise_key(statement: str) -> str:
    """Normalize minor wording differences before registry-level dedupe."""
    normalized = re.sub(r"[^a-z0-9]+", " ", statement.casefold()).strip()
    normalized = re.sub(r"\b(a|an|the)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or statement.strip()


def _coerce_statement(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    statement = raw.strip()
    return statement or None


def _unique_items_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


async def build_premises_by_claim(
    claims: list[DedupedClaim],
    settings: Settings,
    *,
    premise_extractor: PremiseSeam | None = None,
) -> tuple[PremisesRegistry, dict[str, list[str]]]:
    """Attach premise IDs to eligible deduped claims and build a shared registry.

    Args:
        claims: deduplicated claims to enrich.
        settings: service settings passed through to the batch seam.
        premise_extractor: seam for one batch call spanning all eligible claims.
    """
    eligible_claims = [claim for claim in claims if claim.category in _ELIGIBLE_PREMISE_CATEGORIES]
    if not eligible_claims:
        return PremisesRegistry(), {}

    eligible_texts = _unique_items_in_order([c.canonical_text for c in eligible_claims])
    if not eligible_texts:
        return PremisesRegistry(), {}

    premise_texts_by_claim: dict[str, list[str]] = {}
    extractor = premise_extractor or infer_premises_batch
    raw_output = await extractor(eligible_texts, settings)

    if not isinstance(raw_output, dict):
        logger.warning("premise seam returned non-dict payload: %r", raw_output)
        raw_output = {}

    for canonical in eligible_texts:
        raw_values = raw_output.get(canonical, [])
        if not isinstance(raw_values, list):
            continue
        premises_for_claim: list[str] = []
        premise_texts_by_claim[canonical] = premises_for_claim
        for raw in raw_values:
            statement = _coerce_statement(raw)
            if statement is None:
                continue
            premises_for_claim.append(statement)

    registry = PremisesRegistry()
    premise_id_by_key: dict[str, str] = {}

    output: dict[str, list[str]] = {}
    for claim in eligible_claims:
        premises = premise_texts_by_claim.get(claim.canonical_text, [])
        claim_premise_ids: list[str] = []
        seen_for_claim: set[str] = set()
        for statement in premises:
            premise_key = _premise_key(statement)
            premise_id = premise_id_by_key.get(premise_key)
            if premise_id is None:
                premise_id = _premise_id(statement)
                premise_id_by_key[premise_key] = premise_id
                registry.premises[premise_id] = Premise(
                    premise_id=premise_id,
                    statement=statement,
                )
            if premise_id in seen_for_claim:
                continue
            seen_for_claim.add(premise_id)
            claim_premise_ids.append(premise_id)
        if claim_premise_ids:
            output[claim.canonical_text] = claim_premise_ids

    return registry, output


__all__ = ["build_premises_by_claim", "infer_premises_batch"]
