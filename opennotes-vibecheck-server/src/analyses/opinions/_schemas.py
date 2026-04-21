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
