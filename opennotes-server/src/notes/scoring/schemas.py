from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field

from src.common.base_schemas import SQLAlchemySchema


def _none_to_zero(v: Any) -> float:
    return 0.0 if v is None else v


SafeFloat = Annotated[float, BeforeValidator(_none_to_zero)]


class RaterFactorData(SQLAlchemySchema):
    rater_id: str
    agent_name: str | None
    personality: str | None
    intercept: SafeFloat = 0.0
    factor1: SafeFloat = 0.0


class NoteFactorData(SQLAlchemySchema):
    note_id: str
    intercept: SafeFloat = 0.0
    factor1: SafeFloat = 0.0
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


class ScoringHistoryEntryAttributes(SQLAlchemySchema):
    timestamp: str = Field(..., description="ISO 8601 timestamp of the snapshot")
    path: str = Field(..., description="GCS blob path")
    size: int = Field(..., description="Blob size in bytes")


class ScoringHistoryEntryResource(BaseModel):
    type: Literal["scoring-history-entries"] = "scoring-history-entries"
    id: str
    attributes: ScoringHistoryEntryAttributes


class ScoringHistoryListResponse(SQLAlchemySchema):
    data: list[ScoringHistoryEntryResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    meta: dict[str, Any] | None = None


class ScoringHistorySnapshotAttributes(SQLAlchemySchema):
    timestamp: str = Field(..., description="ISO 8601 timestamp of the snapshot")
    snapshot: dict[str, Any] = Field(..., description="Full scoring snapshot data")


class ScoringHistorySnapshotResource(BaseModel):
    type: Literal["scoring-history-snapshots"] = "scoring-history-snapshots"
    id: str
    attributes: ScoringHistorySnapshotAttributes


class ScoringHistorySnapshotResponse(SQLAlchemySchema):
    data: ScoringHistorySnapshotResource
    jsonapi: dict[str, str] = {"version": "1.1"}
