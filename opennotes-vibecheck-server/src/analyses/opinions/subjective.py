"""Subjective-claim extraction.

A subjective claim expresses an opinion, preference, evaluation, or stance
(e.g. "The UI is ugly", "I like the new layout"). Factual, verifiable claims
(e.g. "The UI has 3 buttons") are excluded here; those are handled by the
claims extractor in ``src/analyses/claims/``.
"""
from __future__ import annotations

from src.analyses.opinions._schemas import (
    SubjectiveClaim,
    _SubjectiveClaimsLLM,
)
from src.config import Settings, get_settings
from src.services.gemini_agent import build_agent
from src.utterances.schema import Utterance

_SYSTEM_PROMPT = (
    "You extract SUBJECTIVE claims from a single utterance. A subjective claim "
    "expresses an opinion, preference, evaluation, or stance that cannot be "
    "verified against an external source ('the UI is ugly', 'I like the new "
    "layout', 'this change is bad'). DO NOT extract factual, verifiable "
    "statements ('the UI has 3 buttons', 'the release shipped on Tuesday'). "
    "For each subjective claim, classify the stance as: "
    "'supports' (endorses or favors something), "
    "'opposes' (rejects or disfavors something), or "
    "'evaluates' (qualitative judgement without clear pro/con direction). "
    "Return an empty list if the utterance contains no subjective claims."
)


def _utterance_id(utterance: Utterance, index: int = 0) -> str:
    return utterance.utterance_id or f"utt-{index}"


async def extract_subjective_claims(
    utterance: Utterance,
    *,
    settings: Settings | None = None,
    index: int = 0,
) -> list[SubjectiveClaim]:
    """Return subjective claims contained in ``utterance``.

    Factual, verifiable statements are filtered out by the LLM prompt. The
    ``index`` argument is used only as a fallback when the utterance has no
    ``utterance_id`` assigned.
    """
    settings = settings or get_settings()
    uid = _utterance_id(utterance, index)

    agent = build_agent(
        settings,
        output_type=_SubjectiveClaimsLLM,
        system_prompt=_SYSTEM_PROMPT,
    )

    prompt = f"Utterance (utterance_id={uid}):\n{utterance.text}"
    result = await agent.run(prompt)
    parsed: _SubjectiveClaimsLLM = result.output

    return [
        SubjectiveClaim(
            claim_text=claim.claim_text,
            utterance_id=uid,
            stance=claim.stance,
        )
        for claim in parsed.claims
    ]
