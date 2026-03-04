from __future__ import annotations

import asyncio
import contextlib
import logging
from enum import IntEnum

from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)

DEFAULT_POOL_NAME = "default"
DEFAULT_POOL_CAPACITY = 12
DEFAULT_WORKER_CAPACITY = 12
WORKER_HEARTBEAT_INTERVAL = 30
WORKER_HEARTBEAT_TTL = 90


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


async def register_worker_async(
    pool_name: str = DEFAULT_POOL_NAME,
    worker_id: str | None = None,
    capacity: int = DEFAULT_WORKER_CAPACITY,
) -> None:
    """Register this worker in the pool, contributing capacity. Idempotent via upsert."""
    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from src.config import settings
    from src.database import get_session_maker
    from src.dbos_workflows.token_bucket.models import TokenPoolWorker

    effective_worker_id = worker_id or settings.INSTANCE_ID

    async with get_session_maker()() as session:
        stmt = (
            pg_insert(TokenPoolWorker)
            .values(
                pool_name=pool_name,
                worker_id=effective_worker_id,
                capacity_contribution=capacity,
            )
            .on_conflict_do_update(
                constraint="uq_token_pool_worker",
                set_={
                    "capacity_contribution": capacity,
                    "last_heartbeat": func.now(),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(
            "Worker registered",
            extra={
                "pool_name": pool_name,
                "worker_id": effective_worker_id,
                "capacity": capacity,
            },
        )


async def deregister_worker_async(
    pool_name: str = DEFAULT_POOL_NAME,
    worker_id: str | None = None,
) -> None:
    """Remove this worker's capacity contribution on graceful shutdown."""
    from sqlalchemy import delete

    from src.config import settings
    from src.database import get_session_maker
    from src.dbos_workflows.token_bucket.models import TokenPoolWorker

    effective_worker_id = worker_id or settings.INSTANCE_ID

    async with get_session_maker()() as session:
        await session.execute(
            delete(TokenPoolWorker).where(
                TokenPoolWorker.pool_name == pool_name,
                TokenPoolWorker.worker_id == effective_worker_id,
            )
        )
        await session.commit()
        logger.info(
            "Worker deregistered",
            extra={
                "pool_name": pool_name,
                "worker_id": effective_worker_id,
            },
        )


async def update_worker_heartbeat_async(
    pool_name: str = DEFAULT_POOL_NAME,
    worker_id: str | None = None,
) -> None:
    """Update last_heartbeat for this worker."""
    from sqlalchemy import func, update

    from src.config import settings
    from src.database import get_session_maker
    from src.dbos_workflows.token_bucket.models import TokenPoolWorker

    effective_worker_id = worker_id or settings.INSTANCE_ID

    async with get_session_maker()() as session:
        await session.execute(
            update(TokenPoolWorker)
            .where(
                TokenPoolWorker.pool_name == pool_name,
                TokenPoolWorker.worker_id == effective_worker_id,
            )
            .values(last_heartbeat=func.now())
        )
        await session.commit()


_heartbeat_task: asyncio.Task[None] | None = None


async def start_worker_heartbeat(
    pool_name: str = DEFAULT_POOL_NAME,
    worker_id: str | None = None,
) -> None:
    global _heartbeat_task

    from src.config import settings

    effective_worker_id = worker_id or settings.INSTANCE_ID

    async def _loop() -> None:
        while True:
            try:
                await asyncio.sleep(WORKER_HEARTBEAT_INTERVAL)
                await update_worker_heartbeat_async(pool_name, effective_worker_id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker heartbeat failed")

    _heartbeat_task = asyncio.create_task(_loop())


async def stop_worker_heartbeat() -> None:
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _heartbeat_task
        _heartbeat_task = None
