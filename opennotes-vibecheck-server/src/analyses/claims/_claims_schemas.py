"""Pydantic schemas for claim extraction and semantic dedup.

Kept in a per-package `_claims_schemas.py` so the `src/analyses/claims/` namespace
stays self-contained and parallel agents can land sibling modules
(`known_misinfo.py`, etc.) without touching a shared schemas file.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SourceKind(StrEnum):
    """Origin of a supporting fact used by the evidence slot."""

    UTTERANCE = "utterance"
    EXTERNAL = "external"


class SupportingFact(BaseModel):
    """A single supporting statement for a deduped claim."""

    statement: str
    source_kind: SourceKind
    source_ref: str


class Premise(BaseModel):
    """A premise statement attached to one or more claims."""

    premise_id: str
    statement: str


class PremisesRegistry(BaseModel):
    """Global registry of unique premises discovered across all claims."""

    premises: dict[str, Premise] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_registry(cls, value: Any) -> Any:
        if isinstance(value, dict) and "premises" not in value:
            return {"premises": value}
        return value


class ClaimCategory(StrEnum):
    POTENTIALLY_FACTUAL = "potentially_factual"
    SELF_CLAIMS = "self_claims"
    PREDICTIONS = "predictions"
    SUBJECTIVE = "subjective"
    OTHER = "other"


class Claim(BaseModel):
    """A single verifiable factual claim extracted from an utterance."""

    claim_text: str
    utterance_id: str
    category: ClaimCategory = ClaimCategory.POTENTIALLY_FACTUAL
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedClaim(BaseModel):
    """LLM-facing claim representation (no utterance_id — caller attaches it)."""

    claim_text: str
    category: ClaimCategory = ClaimCategory.POTENTIALLY_FACTUAL
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
    category: ClaimCategory = ClaimCategory.POTENTIALLY_FACTUAL
    occurrence_count: int = Field(ge=1)
    author_count: int = Field(ge=0)
    utterance_ids: list[str]
    representative_authors: list[str]
    supporting_facts: list[SupportingFact] = Field(default_factory=list)
    premise_ids: list[str] = Field(default_factory=list)
    facts_to_verify: int = Field(default=0, ge=0)


class ClaimsReport(BaseModel):
    """Output of `dedupe_claims` — prevalence stats for the Facts sidebar."""

    deduped_claims: list[DedupedClaim]
    total_claims: int
    total_unique: int
    premises: PremisesRegistry | None = None
