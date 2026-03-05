from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.database import get_db
from src.dbos_workflows.token_bucket.config import WORKER_HEARTBEAT_TTL
from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool, TokenPoolWorker
from src.dbos_workflows.token_bucket.schemas import TokenHoldDetail, TokenPoolStatus
from src.users.models import User

router = APIRouter(prefix="/admin/token-pools", tags=["admin"])


async def verify_service_account(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    if not is_service_account(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can perform this action",
        )
    return current_user


@router.get("/", response_model=list[TokenPoolStatus])
async def list_token_pools(
    _service_account: Annotated[User, Depends(verify_service_account)],
    session: AsyncSession = Depends(get_db),
) -> list[TokenPoolStatus]:
    cutoff = datetime.now(UTC) - timedelta(seconds=WORKER_HEARTBEAT_TTL)

    worker_cap_sq = (
        select(
            TokenPoolWorker.pool_name,
            func.coalesce(func.sum(TokenPoolWorker.capacity_contribution), 0).label(
                "worker_capacity"
            ),
        )
        .where(TokenPoolWorker.last_heartbeat >= cutoff)
        .group_by(TokenPoolWorker.pool_name)
        .subquery()
    )

    holds_sq = (
        select(
            TokenHold.pool_name,
            func.coalesce(func.sum(TokenHold.weight), 0).label("total_held"),
            func.count(TokenHold.id).label("hold_count"),
        )
        .where(TokenHold.released_at.is_(None))
        .group_by(TokenHold.pool_name)
        .subquery()
    )

    query = (
        select(
            TokenPool.pool_name,
            TokenPool.capacity,
            func.coalesce(worker_cap_sq.c.worker_capacity, 0).label("worker_capacity"),
            func.coalesce(holds_sq.c.total_held, 0).label("total_held"),
            func.coalesce(holds_sq.c.hold_count, 0).label("hold_count"),
        )
        .outerjoin(worker_cap_sq, TokenPool.pool_name == worker_cap_sq.c.pool_name)
        .outerjoin(holds_sq, TokenPool.pool_name == holds_sq.c.pool_name)
    )

    result = await session.execute(query)
    rows = result.all()

    statuses = []
    for row in rows:
        worker_cap = int(row.worker_capacity)
        effective_capacity = worker_cap if worker_cap > 0 else row.capacity
        total_held = int(row.total_held)
        available = max(0, effective_capacity - total_held)
        utilization = (total_held / effective_capacity * 100) if effective_capacity > 0 else 0.0
        statuses.append(
            TokenPoolStatus(
                pool_name=row.pool_name,
                capacity=effective_capacity,
                available=available,
                active_hold_count=int(row.hold_count),
                utilization_pct=round(utilization, 1),
            )
        )
    return statuses


@router.get("/{pool_name}/holds", response_model=list[TokenHoldDetail])
async def get_pool_holds(
    pool_name: str,
    _service_account: Annotated[User, Depends(verify_service_account)],
    session: AsyncSession = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[TokenHoldDetail]:
    pool_result = await session.execute(select(TokenPool).where(TokenPool.pool_name == pool_name))
    if pool_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Pool '{pool_name}' not found")

    holds_result = await session.execute(
        select(TokenHold)
        .where(
            TokenHold.pool_name == pool_name,
            TokenHold.released_at.is_(None),
        )
        .order_by(TokenHold.acquired_at)
        .limit(limit)
    )
    holds = holds_result.scalars().all()

    return [
        TokenHoldDetail(
            workflow_id=h.workflow_id,
            weight=h.weight,
            acquired_at=h.acquired_at,
        )
        for h in holds
    ]
