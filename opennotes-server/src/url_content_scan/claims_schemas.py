from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class DedupedClaim(BaseModel):
    canonical_text: str
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
