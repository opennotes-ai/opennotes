from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class ClaimCategory(StrEnum):
    """5-way taxonomy for claim classification.

    Mirrors vibecheck-server's `ClaimCategory` so downstream premises/evidence
    tooling can use a shared vocabulary (TASK-1657.04 depends on these keys).
    """

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


class DedupedClaim(BaseModel):
    canonical_text: str
    category: ClaimCategory = ClaimCategory.POTENTIALLY_FACTUAL
    occurrence_count: int = Field(ge=1)
    author_count: int = Field(ge=0)
    utterance_ids: list[str]
    representative_authors: list[str]


class ClaimsReport(BaseModel):
    deduped_claims: list[DedupedClaim]
    total_claims: int
    total_unique: int


class FactCheckMatch(BaseModel):
    claim_text: str
    publisher: str
    review_title: str
    review_url: str
    textual_rating: str
    review_date: date | None = None
