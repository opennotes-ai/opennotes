"""Per-utterance claim extraction via pydantic-ai + Vertex Gemini.

`extract_claims(utterance, settings)` returns `list[Claim]` by asking the shared
Gemini agent to emit a structured `ClaimExtractionResponse`. The utterance_id is
attached to each claim after the LLM call, so the model never has to echo it back.
"""
from __future__ import annotations

from src.analyses.claims._claims_schemas import Claim, ClaimExtractionResponse
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


async def extract_claims(utterance: Utterance, settings: Settings) -> list[Claim]:
    """Extract verifiable claims from a single utterance.

    Returns an empty list when the utterance has no text or the LLM finds no
    verifiable claims. Callers are expected to tolerate an empty result.
    """
    text = (utterance.text or "").strip()
    if not text:
        return []

    uid = utterance.utterance_id or ""
    if not uid:
        return []

    agent = build_agent(
        settings,
        output_type=ClaimExtractionResponse,
        system_prompt=_SYSTEM_PROMPT,
    )
    result = await agent.run(text)
    response = result.output
    if not isinstance(response, ClaimExtractionResponse):
        raise TypeError(
            f"expected ClaimExtractionResponse from Gemini, got {type(response).__name__}"
        )

    return [
        Claim(
            claim_text=item.claim_text,
            utterance_id=uid,
            confidence=item.confidence,
        )
        for item in response.claims
    ]
