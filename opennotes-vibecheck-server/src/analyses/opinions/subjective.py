"""Subjective-claim extraction.

A subjective claim expresses an opinion, preference, evaluation, or stance
(e.g. "The UI is ugly", "I like the new layout"). Factual, verifiable claims
(e.g. "The UI has 3 buttons") are excluded here; those are handled by the
claims extractor in ``src/analyses/claims/``.
"""
from __future__ import annotations

from src.analyses.opinions._schemas import (
    SubjectiveClaim,
    _BulkSubjectiveClaimsLLM,
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


_BULK_SYSTEM_PROMPT = (
    _SYSTEM_PROMPT
    + " You will receive a numbered list of utterances. Return one "
    "`_PerUtteranceSubjectiveClaims` per input utterance, matching the "
    "input index. Preserve order. Emit an empty `claims` list for "
    "utterances without subjective content."
)


async def extract_subjective_claims(
    utterance: Utterance,
    *,
    settings: Settings | None = None,
    index: int = 0,
) -> list[SubjectiveClaim]:
    """Thin wrapper over ``extract_subjective_claims_bulk`` for single-utterance callers."""
    results = await extract_subjective_claims_bulk(
        [utterance], settings=settings, start_index=index
    )
    return results[0] if results else []


async def extract_subjective_claims_bulk(
    utterances: list[Utterance],
    *,
    settings: Settings | None = None,
    start_index: int = 0,
) -> list[list[SubjectiveClaim]]:
    """Extract subjective claims for every utterance in ONE LLM call.

    Returns a list of claim-lists index-aligned with ``utterances``. Empty
    or id-less utterances get an empty list without costing a model call.
    ``start_index`` is a fallback prefix for synthetic utterance_ids when
    utterances don't have their own.
    """
    if not utterances:
        return []

    out: list[list[SubjectiveClaim]] = [[] for _ in utterances]
    prompt_lines: list[str] = []
    for i, u in enumerate(utterances):
        text = (u.text or "").strip()
        if not text:
            continue
        prompt_lines.append(f"[{i}] {text}")

    if not prompt_lines:
        return out

    settings = settings or get_settings()
    agent = build_agent(
        settings,
        output_type=_BulkSubjectiveClaimsLLM,
        system_prompt=_BULK_SYSTEM_PROMPT,
    )
    result = await agent.run("Utterances:\n" + "\n".join(prompt_lines))
    parsed: _BulkSubjectiveClaimsLLM = result.output

    for entry in parsed.results:
        idx = entry.utterance_index
        if 0 <= idx < len(utterances):
            uid = _utterance_id(utterances[idx], start_index + idx)
            out[idx] = [
                SubjectiveClaim(claim_text=c.claim_text, utterance_id=uid, stance=c.stance)
                for c in entry.claims
            ]
    return out


__all__ = [
    "extract_subjective_claims",
    "extract_subjective_claims_bulk",
]
