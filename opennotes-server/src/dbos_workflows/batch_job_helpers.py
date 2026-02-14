"""Shared synchronous helpers for BatchJob lifecycle management in DBOS workflows.

DBOS workflow steps are synchronous, so these helpers wrap async BatchJobService
operations via run_sync(). All helpers are fire-and-forget: errors are logged
but return False rather than propagating, to avoid blocking workflow execution
on transient DB errors.

Used by: import_workflow.py, approval_workflow.py, rechunk_workflow.py
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.monitoring import get_logger
from src.utils.async_compat import run_sync

logger = get_logger(__name__)


def start_batch_job_sync(
    batch_job_id: UUID,
    total_tasks: int | None = None,
) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job is None:
                raise ValueError(f"Batch job not found: {batch_job_id}")
            if total_tasks is not None:
                job.total_tasks = total_tasks
            await service.start_job(batch_job_id)
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to start batch job",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


def update_batch_job_progress_sync(
    batch_job_id: UUID,
    completed_tasks: int,
    failed_tasks: int,
    current_item: str | None = None,
) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            await service.update_progress(
                batch_job_id,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                current_item=current_item,
            )
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to update batch job progress",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


def finalize_batch_job_sync(
    batch_job_id: UUID,
    success: bool,
    completed_tasks: int,
    failed_tasks: int,
    error_summary: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
) -> bool:
    from src.batch_jobs.service import BatchJobService
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job and stats:
                job.metadata_ = {**(job.metadata_ or {}), "stats": stats}  # pyright: ignore[reportAttributeAccessIssue]
            if success:
                await service.complete_job(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
            else:
                await service.update_progress(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
                await service.fail_job(batch_job_id, error_summary)
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to finalize batch job",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        logger.warning(
            "finalize_batch_job_sync returning False — job may remain IN_PROGRESS",
            extra={
                "batch_job_id": str(batch_job_id),
                "intended_success": success,
            },
        )
        return False
