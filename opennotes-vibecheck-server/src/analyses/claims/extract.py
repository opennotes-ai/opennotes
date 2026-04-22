"""Claim extraction via pydantic-ai + Vertex Gemini.

Two entry points:
- `extract_claims_bulk(utterances, settings)` — ONE Gemini call for all
  utterances, returns `list[list[Claim]]` index-aligned to `utterances`.
  This is what the orchestrator uses; avoids per-utterance API bursts that
  blow through Vertex quotas.
- `extract_claims(utterance, settings)` — thin wrapper around the bulk path
  for backwards compatibility (one-element batch).
"""
from __future__ import annotations

from src.analyses.claims._claims_schemas import (
    BulkClaimExtractionResponse,
    Claim,
    ClaimExtractionResponse,
)
from src.config import Settings
from src.services.gemini_agent import build_agent
from src.utterances.schema import Utterance

_SYSTEM_PROMPT = (
    "You extract verifiable factual claims from short user-generated text "
    "(posts, comments, replies).\n"
    "\n"
    "Rules:\n"
    "- A claim is a statement that can, in principle, be checked against "
    "external evidence.\n"
    "- Opinions, questions, jokes, and purely emotional statements are NOT claims.\n"
    "- Rewrite each claim as a concise, standalone assertion (no pronouns that "
    "depend on surrounding context).\n"
    "- confidence is your estimate (0.0-1.0) that the text is actually making "
    "this claim, not whether the claim is true.\n"
    "- If the text contains no verifiable claims, return an empty list."
)


_BULK_SYSTEM_PROMPT = (
    _SYSTEM_PROMPT
    + "\n\n"
    + "You will receive a NUMBERED list of utterances. For each utterance, "
    "return a `_PerUtteranceClaims` object whose `utterance_index` matches "
    "the index in the input and whose `claims` list contains the extracted "
    "claims from that utterance (empty list if none). Always emit one entry "
    "per input utterance, even if empty, preserving input order by index."
)


async def extract_claims(utterance: Utterance, settings: Settings) -> list[Claim]:
    """Thin wrapper over `extract_claims_bulk` for single-utterance callers."""
    results = await extract_claims_bulk([utterance], settings)
    return results[0] if results else []


async def extract_claims_bulk(
    utterances: list[Utterance], settings: Settings
) -> list[list[Claim]]:
    """Extract verifiable claims for every utterance in ONE LLM call.

    Returns a list of claim-lists index-aligned with `utterances`. Utterances
    with no text or no utterance_id get an empty list in their slot without
    costing a model call.
    """
    if not utterances:
        return []

    usable_indices: list[int] = []
    prompt_lines: list[str] = []
    for i, u in enumerate(utterances):
        text = (u.text or "").strip()
        uid = u.utterance_id or ""
        if not text or not uid:
            continue
        usable_indices.append(i)
        prompt_lines.append(f"[{i}] {text}")

    out: list[list[Claim]] = [[] for _ in utterances]
    if not prompt_lines:
        return out

    agent = build_agent(
        settings,
        output_type=BulkClaimExtractionResponse,
        system_prompt=_BULK_SYSTEM_PROMPT,
    )
    prompt = "Utterances:\n" + "\n".join(prompt_lines)
    result = await agent.run(prompt)
    response = result.output
    if not isinstance(response, BulkClaimExtractionResponse):
        raise TypeError(
            f"expected BulkClaimExtractionResponse from Gemini, got {type(response).__name__}"
        )

    for entry in response.results:
        idx = entry.utterance_index
        if 0 <= idx < len(utterances):
            uid = utterances[idx].utterance_id or ""
            if not uid:
                continue
            out[idx] = [
                Claim(claim_text=c.claim_text, utterance_id=uid, confidence=c.confidence)
                for c in entry.claims
            ]
    return out


__all__ = [
    "ClaimExtractionResponse",
    "extract_claims",
    "extract_claims_bulk",
]
