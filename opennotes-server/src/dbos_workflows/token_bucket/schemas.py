from __future__ import annotations

from datetime import datetime

from src.common.base_schemas import SQLAlchemySchema


class TokenPoolStatus(SQLAlchemySchema):
    pool_name: str
    capacity: int
    available: int
    active_hold_count: int
    utilization_pct: float


class TokenHoldDetail(SQLAlchemySchema):
    workflow_id: str
    weight: int
    acquired_at: datetime
