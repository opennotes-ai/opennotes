from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from dbos import DBOS
from sqlalchemy import delete, func, select, update

from src.dbos_workflows.token_bucket.config import WORKER_HEARTBEAT_TTL
from src.dbos_workflows.token_bucket.models import TokenHold, TokenPoolWorker
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

MAX_HOLD_DURATION_SECONDS = 3600


@DBOS.step()
def find_stale_holds(max_age_seconds: int = MAX_HOLD_DURATION_SECONDS) -> list[dict[str, Any]]:
    from src.database import get_session_maker

    async def _find() -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
        async with get_session_maker()() as session:
            result = await session.execute(
                select(TokenHold)
                .where(
                    TokenHold.released_at.is_(None),
                    TokenHold.acquired_at < cutoff,
                )
                .limit(100)
            )
            holds = result.scalars().all()
            return [
                {
                    "id": str(h.id),
                    "pool_name": h.pool_name,
                    "workflow_id": h.workflow_id,
                    "weight": h.weight,
                    "acquired_at": h.acquired_at.isoformat() if h.acquired_at else None,
                }
                for h in holds
            ]

    return run_sync(_find())


@DBOS.step()
def release_stale_hold(hold: dict[str, Any]) -> bool:
    from src.database import get_session_maker

    async def _release() -> bool:
        async with get_session_maker()() as session:
            result = await session.execute(
                update(TokenHold)
                .where(
                    TokenHold.pool_name == hold["pool_name"],
                    TokenHold.workflow_id == hold["workflow_id"],
                    TokenHold.released_at.is_(None),
                )
                .values(released_at=func.now())
                .returning(TokenHold.id)
            )
            released = result.scalar_one_or_none()
            await session.commit()
            return released is not None

    released = run_sync(_release())
    if released:
        logger.info(
            "Released stale token hold",
            extra={
                "pool_name": hold["pool_name"],
                "workflow_id": hold["workflow_id"],
                "weight": hold["weight"],
                "acquired_at": hold["acquired_at"],
            },
        )
    return released


@DBOS.step()
def cleanup_stale_workers(heartbeat_ttl_seconds: int = WORKER_HEARTBEAT_TTL) -> int:
    """Remove workers whose heartbeat has expired."""
    from src.database import get_session_maker

    async def _cleanup() -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_ttl_seconds)
        async with get_session_maker()() as session:
            result = await session.execute(
                delete(TokenPoolWorker).where(
                    TokenPoolWorker.last_heartbeat < cutoff,
                )
            )
            count: int = result.rowcount or 0  # pyright: ignore[reportAttributeAccessIssue]
            if count > 0:
                await session.commit()
                logger.info(
                    "Removed stale workers",
                    extra={"count": count},
                )
            return count

    return run_sync(_cleanup())


@DBOS.scheduled("*/5 * * * *")  # pyright: ignore[reportArgumentType]
@DBOS.workflow()
def cleanup_stale_token_holds(
    scheduled_time: datetime,
    actual_time: datetime,
) -> dict[str, Any]:
    logger.info(
        "Starting stale token hold cleanup",
        extra={
            "scheduled_time": scheduled_time.isoformat(),
            "actual_time": actual_time.isoformat(),
        },
    )

    stale_holds = find_stale_holds()
    released_count = 0

    for hold in stale_holds:
        if release_stale_hold(hold):
            released_count += 1

    stale_workers_removed = cleanup_stale_workers()

    logger.info(
        "Stale token hold cleanup completed",
        extra={
            "found": len(stale_holds),
            "released": released_count,
            "stale_workers_removed": stale_workers_removed,
        },
    )

    return {
        "found": len(stale_holds),
        "released": released_count,
        "stale_workers_removed": stale_workers_removed,
    }


CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME: str = cleanup_stale_token_holds.__qualname__
