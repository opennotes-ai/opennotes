from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from dbos import DBOS, Queue
from sqlalchemy import func, select

from src.batch_jobs.constants import COPY_REQUESTS_JOB_TYPE
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.dbos_workflows.batch_job_helpers import (
    finalize_batch_job_sync,
    update_batch_job_progress_sync,
)
from src.dbos_workflows.enqueue_utils import safe_enqueue
from src.monitoring import get_logger
from src.notes.models import Request
from src.utils.async_compat import run_sync

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

FAILURE_THRESHOLD = 0.5
COPY_BATCH_SIZE = 50

copy_requests_queue = Queue(
    name="copy_requests",
    worker_concurrency=2,
    concurrency=5,
)


def _finalize_job(
    batch_job_id: UUID,
    success: bool,
    completed_tasks: int,
    failed_tasks: int,
    error_summary: dict[str, Any] | None = None,
) -> None:
    ok = finalize_batch_job_sync(
        batch_job_id,
        success=success,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        error_summary=error_summary,
    )
    if not ok:
        logger.warning(
            "finalize_batch_job_sync returned False; job may remain IN_PROGRESS",
            extra={"batch_job_id": str(batch_job_id), "intended_success": success},
        )


def _compute_batch_success(completed_count: int, failed_count: int) -> bool:
    total = completed_count + failed_count
    if total == 0:
        return False
    return (failed_count / total) < FAILURE_THRESHOLD


async def dispatch_copy_requests(
    db: AsyncSession,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> UUID:
    count_stmt = (
        select(func.count())
        .select_from(Request)
        .where(
            Request.community_server_id == source_community_server_id,
            Request.deleted_at.is_(None),
        )
    )
    result = await db.execute(count_stmt)
    total_requests = result.scalar() or 0

    batch_job_service = BatchJobService(db)
    job_metadata: dict[str, str | int | bool | float | list[str] | None] = {
        "source_community_server_id": str(source_community_server_id),
        "target_community_server_id": str(target_community_server_id),
        "execution_backend": "dbos",
    }

    job = await batch_job_service.create_job(
        BatchJobCreate(
            job_type=COPY_REQUESTS_JOB_TYPE,
            total_tasks=total_requests,
            metadata=job_metadata,
        )
    )

    if total_requests == 0:
        await batch_job_service.start_job(job.id)
        await batch_job_service.complete_job(job.id, completed_tasks=0, failed_tasks=0)
        await db.commit()
        await db.refresh(job)
        return job.id

    await batch_job_service.start_job(job.id)
    await db.commit()
    await db.refresh(job)

    try:
        handle = await safe_enqueue(
            lambda: copy_requests_queue.enqueue(
                copy_requests_workflow,
                str(job.id),
                str(source_community_server_id),
                str(target_community_server_id),
            )
        )
        workflow_id = handle.workflow_id
    except Exception as e:
        await batch_job_service.fail_job(
            job.id,
            error_summary={"stage": "dispatch", "error": str(e)},
        )
        await db.commit()
        logger.error(
            "Failed to dispatch copy-requests workflow",
            extra={"batch_job_id": str(job.id), "error": str(e)},
            exc_info=True,
        )
        raise

    await batch_job_service.set_workflow_id(job.id, workflow_id)
    await db.commit()

    logger.info(
        "Copy-requests workflow dispatched",
        extra={
            "batch_job_id": str(job.id),
            "workflow_id": workflow_id,
            "total_requests": total_requests,
        },
    )

    return job.id


@DBOS.workflow()
def copy_requests_workflow(
    batch_job_id: str,
    source_community_server_id: str,
    target_community_server_id: str,
) -> dict[str, Any]:
    workflow_id = DBOS.workflow_id

    logger.info(
        "Starting copy-requests workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
        },
    )

    try:
        result = copy_requests_step(
            batch_job_id,
            source_community_server_id,
            target_community_server_id,
        )
    except Exception:
        logger.exception(
            "Copy-requests step failed",
            extra={"batch_job_id": batch_job_id, "workflow_id": workflow_id},
        )
        _finalize_job(
            UUID(batch_job_id),
            success=False,
            completed_tasks=0,
            failed_tasks=0,
        )
        return {"total_copied": 0, "total_failed": 0, "total_skipped": 0}

    completed_count = result["total_copied"]
    failed_count = result["total_failed"]
    success = _compute_batch_success(completed_count, failed_count)

    _finalize_job(
        UUID(batch_job_id),
        success=success,
        completed_tasks=completed_count,
        failed_tasks=failed_count,
    )

    logger.info(
        "Copy-requests workflow completed",
        extra={
            "workflow_id": workflow_id,
            "completed": completed_count,
            "failed": failed_count,
        },
    )

    return result


@DBOS.step(retries_allowed=True, max_attempts=3)
def copy_requests_step(
    batch_job_id: str,
    source_community_server_id: str,
    target_community_server_id: str,
) -> dict[str, Any]:
    from src.database import get_session_maker
    from src.notes.copy_request_service import CopyRequestService

    progress_counter = {"count": 0}

    def on_progress(current: int, total: int) -> None:
        progress_counter["count"] = current
        if current % COPY_BATCH_SIZE == 0 or current == total:
            update_batch_job_progress_sync(
                UUID(batch_job_id),
                completed_tasks=current,
                failed_tasks=0,
            )

    async def _run() -> dict[str, Any]:
        async with get_session_maker()() as db:
            result = await CopyRequestService.copy_requests(
                db=db,
                source_community_server_id=UUID(source_community_server_id),
                target_community_server_id=UUID(target_community_server_id),
                on_progress=on_progress,
            )
            await db.commit()
            return {
                "total_copied": result.total_copied,
                "total_skipped": result.total_skipped,
                "total_failed": result.total_failed,
            }

    return run_sync(_run())


COPY_REQUESTS_WORKFLOW_NAME: str = copy_requests_workflow.__qualname__
