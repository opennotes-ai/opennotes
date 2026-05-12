"""Schema contracts for the overall recommendation synthesis output."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class OverallVerdict(StrEnum):
    PASS = "pass"
    FLAG = "flag"


class OverallDecision(BaseModel):
    verdict: OverallVerdict
    reason: str
