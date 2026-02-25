from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from dbos import DBOS
from sqlalchemy import func, select, update

from src.dbos_workflows.token_bucket.models import TokenHold
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
                select(TokenHold).where(
                    TokenHold.released_at.is_(None),
                    TokenHold.acquired_at < cutoff,
                )
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

    logger.info(
        "Stale token hold cleanup completed",
        extra={
            "found": len(stale_holds),
            "released": released_count,
        },
    )

    return {"found": len(stale_holds), "released": released_count}


CLEANUP_STALE_TOKEN_HOLDS_WORKFLOW_NAME: str = cleanup_stale_token_holds.__qualname__
