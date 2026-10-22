from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.url_content_scan.claims_schemas import DedupedClaim

SentimentLabel = Literal["positive", "negative", "neutral"]
SubjectiveStance = Literal["supports", "opposes", "evaluates"]


class SentimentScore(BaseModel):
    utterance_id: str
    label: SentimentLabel
    valence: float = Field(ge=-1.0, le=1.0)


class SentimentStatsReport(BaseModel):
    per_utterance: list[SentimentScore]
    positive_pct: float = Field(ge=0.0, le=100.0)
    negative_pct: float = Field(ge=0.0, le=100.0)
    neutral_pct: float = Field(ge=0.0, le=100.0)
    mean_valence: float = Field(ge=-1.0, le=1.0)


class SubjectiveClaim(BaseModel):
    claim_text: str
    utterance_id: str
    stance: SubjectiveStance


class OpinionsReport(BaseModel):
    sentiment_stats: SentimentStatsReport
    subjective_claims: list[SubjectiveClaim]


class ClaimTrend(BaseModel):
    label: str
    cluster_texts: list[str]
    summary: str


class ClaimOpposition(BaseModel):
    topic: str
    supporting_cluster_texts: list[str]
    opposing_cluster_texts: list[str]
    note: str | None = None


class TrendsOppositionsReport(BaseModel):
    trends: list[ClaimTrend]
    oppositions: list[ClaimOpposition]
    input_cluster_count: int
    skipped_for_cap: int


def empty_trends_oppositions_report() -> TrendsOppositionsReport:
    return TrendsOppositionsReport(
        trends=[],
        oppositions=[],
        input_cluster_count=0,
        skipped_for_cap=0,
    )


class HighlightsThresholdInfo(BaseModel):
    total_authors: int
    total_utterances: int
    min_authors_required: int
    min_occurrences_required: int


class OpinionsHighlight(BaseModel):
    cluster: DedupedClaim
    crossed_scaled_threshold: bool


class OpinionsHighlightsReport(BaseModel):
    highlights: list[OpinionsHighlight]
    threshold: HighlightsThresholdInfo
    fallback_engaged: bool
    floor_eligible_count: int
    total_input_count: int
