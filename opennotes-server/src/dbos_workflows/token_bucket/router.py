from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dbos_workflows.token_bucket.config import WORKER_HEARTBEAT_TTL
from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool, TokenPoolWorker
from src.dbos_workflows.token_bucket.schemas import TokenHoldDetail, TokenPoolStatus

router = APIRouter(prefix="/admin/token-pools", tags=["admin"])


async def _compute_effective_capacity(
    session: AsyncSession, pool_name: str, static_capacity: int
) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=WORKER_HEARTBEAT_TTL)
    result = await session.execute(
        select(func.coalesce(func.sum(TokenPoolWorker.capacity_contribution), 0)).where(
            TokenPoolWorker.pool_name == pool_name,
            TokenPoolWorker.last_heartbeat >= cutoff,
        )
    )
    worker_capacity = result.scalar() or 0
    if worker_capacity > 0:
        return int(worker_capacity)
    return static_capacity


@router.get("/", response_model=list[TokenPoolStatus])
async def list_token_pools(
    session: AsyncSession = Depends(get_db),
) -> list[TokenPoolStatus]:
    pools_result = await session.execute(select(TokenPool))
    pools = pools_result.scalars().all()

    statuses = []
    for pool in pools:
        effective_capacity = await _compute_effective_capacity(
            session, pool.pool_name, pool.capacity
        )

        held_result = await session.execute(
            select(
                func.coalesce(func.sum(TokenHold.weight), 0),
                func.count(TokenHold.id),
            ).where(
                TokenHold.pool_name == pool.pool_name,
                TokenHold.released_at.is_(None),
            )
        )
        row = held_result.one()
        total_held = row[0]
        hold_count = row[1]
        available = effective_capacity - total_held
        utilization = (total_held / effective_capacity * 100) if effective_capacity > 0 else 0.0

        statuses.append(
            TokenPoolStatus(
                pool_name=pool.pool_name,
                capacity=effective_capacity,
                available=available,
                active_hold_count=hold_count,
                utilization_pct=round(utilization, 1),
            )
        )
    return statuses


@router.get("/{pool_name}/holds", response_model=list[TokenHoldDetail])
async def get_pool_holds(
    pool_name: str,
    session: AsyncSession = Depends(get_db),
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
