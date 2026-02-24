from __future__ import annotations

import logging
from typing import Any

from dbos import DBOS
from sqlalchemy import func, select, update

from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool
from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)


async def try_acquire_tokens_async(pool_name: str, weight: int, workflow_id: str) -> bool:
    """Atomically acquire tokens. Idempotent via workflow_id.

    Uses SELECT FOR UPDATE on the pool row to serialize concurrent acquisitions.
    """
    from src.database import get_session_maker

    async with get_session_maker()() as session:
        existing = await session.execute(
            select(TokenHold).where(
                TokenHold.pool_name == pool_name,
                TokenHold.workflow_id == workflow_id,
                TokenHold.released_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            return True

        pool_result = await session.execute(
            select(TokenPool).where(TokenPool.pool_name == pool_name).with_for_update()
        )
        pool_row = pool_result.scalar_one_or_none()
        if pool_row is None:
            logger.error("Token pool not found: %s", pool_name)
            return False

        held_result = await session.execute(
            select(func.coalesce(func.sum(TokenHold.weight), 0)).where(
                TokenHold.pool_name == pool_name,
                TokenHold.released_at.is_(None),
            )
        )
        total_held = held_result.scalar()

        if pool_row.capacity - total_held < weight:
            return False

        session.add(
            TokenHold(
                pool_name=pool_name,
                workflow_id=workflow_id,
                weight=weight,
            )
        )
        await session.commit()
        return True


async def release_tokens_async(pool_name: str, workflow_id: str) -> bool:
    """Release tokens held by a workflow. Returns True if a hold was released."""
    from src.database import get_session_maker

    async with get_session_maker()() as session:
        result = await session.execute(
            update(TokenHold)
            .where(
                TokenHold.pool_name == pool_name,
                TokenHold.workflow_id == workflow_id,
                TokenHold.released_at.is_(None),
            )
            .values(released_at=func.now())
            .returning(TokenHold.id)
        )
        released = result.scalar_one_or_none()
        await session.commit()
        if released:
            logger.info(
                "Released tokens",
                extra={"pool_name": pool_name, "workflow_id": workflow_id},
            )
            return True
        return False


async def get_pool_status_async(pool_name: str) -> dict[str, Any] | None:
    """Get current pool status with capacity and active holds."""
    from src.database import get_session_maker

    async with get_session_maker()() as session:
        pool_result = await session.execute(
            select(TokenPool).where(TokenPool.pool_name == pool_name)
        )
        pool = pool_result.scalar_one_or_none()
        if pool is None:
            return None

        held_result = await session.execute(
            select(func.coalesce(func.sum(TokenHold.weight), 0)).where(
                TokenHold.pool_name == pool_name,
                TokenHold.released_at.is_(None),
            )
        )
        total_held = held_result.scalar()

        holds_result = await session.execute(
            select(TokenHold).where(
                TokenHold.pool_name == pool_name,
                TokenHold.released_at.is_(None),
            )
        )
        active_holds = [
            {
                "workflow_id": h.workflow_id,
                "weight": h.weight,
                "acquired_at": h.acquired_at.isoformat() if h.acquired_at else None,
            }
            for h in holds_result.scalars()
        ]

        return {
            "pool_name": pool.pool_name,
            "capacity": pool.capacity,
            "available": pool.capacity - total_held,
            "total_held": total_held,
            "active_holds": active_holds,
        }


@DBOS.step()
def try_acquire_tokens(pool_name: str, weight: int, workflow_id: str) -> bool:
    """DBOS step wrapper for token acquisition."""
    return run_sync(try_acquire_tokens_async(pool_name, weight, workflow_id))


@DBOS.step()
def release_tokens(pool_name: str, workflow_id: str) -> bool:
    """DBOS step wrapper for token release."""
    return run_sync(release_tokens_async(pool_name, workflow_id))


@DBOS.step()
def get_pool_status(pool_name: str) -> dict[str, Any] | None:
    """DBOS step wrapper for pool status query."""
    return run_sync(get_pool_status_async(pool_name))
