"""Pydantic models for extracted opinion trends and opposition pairs."""
from __future__ import annotations

from pydantic import BaseModel


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


__all__ = [
    "ClaimOpposition",
    "ClaimTrend",
    "TrendsOppositionsReport",
    "empty_trends_oppositions_report",
]
