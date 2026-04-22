"""Pydantic schemas for claim extraction and semantic dedup.

Kept in a per-package `_claims_schemas.py` so the `src/analyses/claims/` namespace
stays self-contained and parallel agents can land sibling modules
(`known_misinfo.py`, etc.) without touching a shared schemas file.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """A single verifiable factual claim extracted from an utterance."""

    claim_text: str
    utterance_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedClaim(BaseModel):
    """LLM-facing claim representation (no utterance_id — caller attaches it)."""

    claim_text: str
    confidence: float = Field(ge=0.0, le=1.0)


class ClaimExtractionResponse(BaseModel):
    """pydantic-ai Agent output_type wrapper.

    pydantic-ai structured output requires a `BaseModel`, so we wrap the
    list of claims. An empty list signals "no verifiable claims in this text".
    """

    claims: list[ExtractedClaim] = Field(default_factory=list)


class _PerUtteranceClaims(BaseModel):
    """Claims extracted from one utterance, keyed by its index in the batch."""

    utterance_index: int = Field(ge=0)
    claims: list[ExtractedClaim] = Field(default_factory=list)


class BulkClaimExtractionResponse(BaseModel):
    """Output wrapper for the bulk claim extractor.

    The model returns one `_PerUtteranceClaims` per input utterance (by index).
    Utterances with no verifiable claims should still get an entry with an
    empty `claims` list so the caller can index-align results.
    """

    results: list[_PerUtteranceClaims] = Field(default_factory=list)


class DedupedClaim(BaseModel):
    """A cluster of semantically-equivalent claims across utterances."""

    canonical_text: str
    occurrence_count: int = Field(ge=1)
    author_count: int = Field(ge=0)
    utterance_ids: list[str]
    representative_authors: list[str]


class ClaimsReport(BaseModel):
    """Output of `dedupe_claims` — prevalence stats for the Facts sidebar."""

    deduped_claims: list[DedupedClaim]
    total_claims: int
    total_unique: int
