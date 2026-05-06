"""Pydantic models for extracted opinion trends and opposition pairs."""
from __future__ import annotations

from pydantic import BaseModel


class ClaimTrend(BaseModel):
    label: str
    cluster_ids: list[str]
    summary: str


class ClaimOpposition(BaseModel):
    topic: str
    supporting_cluster_ids: list[str]
    opposing_cluster_ids: list[str]
    note: str | None = None


class TrendsOppositionsReport(BaseModel):
    trends: list[ClaimTrend]
    oppositions: list[ClaimOpposition]
    input_cluster_count: int
    skipped_for_cap: int


__all__ = [
    "ClaimOpposition",
    "ClaimTrend",
    "TrendsOppositionsReport",
]
