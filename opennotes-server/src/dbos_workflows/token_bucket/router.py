from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.database import get_db
from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool
from src.dbos_workflows.token_bucket.operations import _get_effective_capacity
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
    pools_result = await session.execute(select(TokenPool))
    pools = pools_result.scalars().all()

    statuses = []
    for pool in pools:
        effective_capacity = await _get_effective_capacity(session, pool.pool_name, pool.capacity)

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
        available = max(0, effective_capacity - total_held)
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
    _service_account: Annotated[User, Depends(verify_service_account)],
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
