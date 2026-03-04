from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from dbos import DBOS
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from src.dbos_workflows.token_bucket.config import WORKER_HEARTBEAT_TTL
from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool, TokenPoolWorker
from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)

MAX_SCAVENGE_BATCH = 10

_TERMINAL_STATUSES = frozenset(
    {
        "ERROR",
        "SUCCESS",
        "CANCELLED",
        "MAX_RECOVERY_ATTEMPTS_EXCEEDED",
        "RETRIES_EXCEEDED",
    }
)


async def _get_effective_capacity(session: Any, pool_name: str, static_capacity: int) -> int:
    """Compute effective pool capacity from active workers, falling back to static capacity."""
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


async def _scavenge_zombie_holds(session: Any, pool_name: str) -> int:
    """Release holds whose DBOS workflows have reached a terminal state.

    Must be called while holding the SELECT FOR UPDATE lock on the pool row.
    Returns the number of holds released.
    """
    holds_result = await session.execute(
        select(TokenHold).where(
            TokenHold.pool_name == pool_name,
            TokenHold.released_at.is_(None),
        )
    )
    active_holds = holds_result.scalars().all()

    released_count = 0
    for hold in active_holds[:MAX_SCAVENGE_BATCH]:
        try:
            wf_status = await asyncio.to_thread(DBOS.get_workflow_status, hold.workflow_id)
        except Exception:
            logger.warning(
                "Failed to check workflow status",
                extra={"pool_name": pool_name, "workflow_id": hold.workflow_id},
                exc_info=True,
            )
            continue
        if wf_status is None:
            continue
        if wf_status.status in _TERMINAL_STATUSES:
            await session.execute(
                update(TokenHold).where(TokenHold.id == hold.id).values(released_at=func.now())
            )
            logger.info(
                "Scavenged zombie hold",
                extra={
                    "pool_name": pool_name,
                    "workflow_id": hold.workflow_id,
                    "workflow_status": wf_status.status,
                    "weight": hold.weight,
                },
            )
            released_count += 1

    return released_count


async def try_acquire_tokens_async(pool_name: str, weight: int, workflow_id: str) -> bool:
    """Atomically acquire tokens. Idempotent via workflow_id.

    Uses SELECT FOR UPDATE on the pool row to serialize concurrent acquisitions.
    When the pool is full, actively scavenges holds from terminated workflows
    before giving up.
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

        effective_capacity = await _get_effective_capacity(session, pool_name, pool_row.capacity)

        held_result = await session.execute(
            select(func.coalesce(func.sum(TokenHold.weight), 0)).where(
                TokenHold.pool_name == pool_name,
                TokenHold.released_at.is_(None),
            )
        )
        total_held: int = held_result.scalar() or 0

        if effective_capacity - total_held < weight:
            scavenged = await _scavenge_zombie_holds(session, pool_name)
            if scavenged > 0:
                held_result = await session.execute(
                    select(func.coalesce(func.sum(TokenHold.weight), 0)).where(
                        TokenHold.pool_name == pool_name,
                        TokenHold.released_at.is_(None),
                    )
                )
                total_held = held_result.scalar() or 0

            if effective_capacity - total_held < weight:
                return False

        session.add(
            TokenHold(
                pool_name=pool_name,
                workflow_id=workflow_id,
                weight=weight,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            return True
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

        effective_capacity = await _get_effective_capacity(session, pool_name, pool.capacity)

        held_result = await session.execute(
            select(func.coalesce(func.sum(TokenHold.weight), 0)).where(
                TokenHold.pool_name == pool_name,
                TokenHold.released_at.is_(None),
            )
        )
        total_held: int = held_result.scalar() or 0

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
            "capacity": effective_capacity,
            "available": effective_capacity - total_held,
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
