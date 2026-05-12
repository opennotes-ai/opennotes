from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
    chunk_idx: int | None = None
    chunk_count: int | None = None


class OpinionsReport(BaseModel):
    sentiment_stats: SentimentStatsReport
    subjective_claims: list[SubjectiveClaim]


class _SentimentScoreLLM(BaseModel):
    utterance_id: str
    label: SentimentLabel
    valence: float = Field(ge=-1.0, le=1.0)


class _SentimentBatchLLM(BaseModel):
    scores: list[_SentimentScoreLLM]


class _SubjectiveClaimLLM(BaseModel):
    claim_text: str
    stance: SubjectiveStance


class _SubjectiveClaimsLLM(BaseModel):
    claims: list[_SubjectiveClaimLLM]


class _PerUtteranceSubjectiveClaims(BaseModel):
    utterance_index: int = Field(ge=0)
    claims: list[_SubjectiveClaimLLM] = Field(default_factory=list)


class _BulkSubjectiveClaimsLLM(BaseModel):
    results: list[_PerUtteranceSubjectiveClaims] = Field(default_factory=list)
