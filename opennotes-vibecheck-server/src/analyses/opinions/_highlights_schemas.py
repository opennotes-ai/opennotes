from __future__ import annotations

from pydantic import BaseModel

from src.analyses.claims._claims_schemas import DedupedClaim


class OpinionsHighlight(BaseModel):
    cluster: DedupedClaim
    crossed_scaled_threshold: bool


class HighlightsThresholdInfo(BaseModel):
    total_authors: int
    total_utterances: int
    min_authors_required: int
    min_occurrences_required: int


class OpinionsHighlightsReport(BaseModel):
    highlights: list[OpinionsHighlight]
    threshold: HighlightsThresholdInfo
    fallback_engaged: bool
    floor_eligible_count: int
    total_input_count: int
