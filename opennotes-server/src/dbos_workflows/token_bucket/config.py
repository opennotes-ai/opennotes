from __future__ import annotations

import logging
from enum import IntEnum

from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)

DEFAULT_POOL_NAME = "default"
DEFAULT_POOL_CAPACITY = 12


class WorkflowWeight(IntEnum):
    RECHUNK = 5
    CONTENT_SCAN = 3
    IMPORT_PIPELINE = 3
    SIMULATION_TURN = 2
    APPROVAL = 1
    CONTENT_MONITORING = 1
    SIMULATION_ORCHESTRATOR = 1


async def ensure_pool_exists_async(
    pool_name: str = DEFAULT_POOL_NAME,
    capacity: int | None = None,
) -> None:
    """Create pool if not exists, update capacity if changed. Idempotent."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from src.database import get_session_maker
    from src.dbos_workflows.token_bucket.models import TokenPool

    effective_capacity = capacity if capacity is not None else DEFAULT_POOL_CAPACITY

    async with get_session_maker()() as session:
        stmt = (
            pg_insert(TokenPool)
            .values(
                pool_name=pool_name,
                capacity=effective_capacity,
            )
            .on_conflict_do_update(
                index_elements=["pool_name"],
                set_={"capacity": effective_capacity},
            )
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(
            "Token pool ensured",
            extra={"pool_name": pool_name, "capacity": effective_capacity},
        )


def ensure_pool_exists(
    pool_name: str = DEFAULT_POOL_NAME,
    capacity: int | None = None,
) -> None:
    """Synchronous wrapper for pool initialization."""
    run_sync(ensure_pool_exists_async(pool_name, capacity))
