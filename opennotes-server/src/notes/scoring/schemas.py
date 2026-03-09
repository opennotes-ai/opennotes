from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.common.base_schemas import SQLAlchemySchema


class RaterFactorData(SQLAlchemySchema):
    rater_id: str
    agent_name: str | None
    personality: str | None
    intercept: float
    factor1: float


class NoteFactorData(SQLAlchemySchema):
    note_id: str
    intercept: float
    factor1: float
    status: str | None
    classification: str | None
    author_agent_name: str | None


class ScoringAnalysisAttributes(SQLAlchemySchema):
    scored_at: datetime
    tier: str | None
    global_intercept: float
    rater_count: int
    note_count: int
    rater_factors: list[RaterFactorData]
    note_factors: list[NoteFactorData]


class ScoringAnalysisResource(BaseModel):
    type: Literal["scoring-analyses"] = "scoring-analyses"
    id: str
    attributes: ScoringAnalysisAttributes


class ScoringAnalysisResponse(SQLAlchemySchema):
    data: ScoringAnalysisResource
    jsonapi: dict[str, str] = {"version": "1.1"}
