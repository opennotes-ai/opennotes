"""DBOS scheduled workflows for periodic maintenance operations.

Replaces TaskIQ scheduler tasks (src/tasks/scheduler_tasks.py) with
durable DBOS scheduled workflows. These workflows run automatically
when the DBOS worker is launched via DBOS.launch().

Schedules:
    cleanup_stale_batch_jobs_workflow: Weekly, Sunday midnight UTC (0 0 * * 0)
    monitor_stuck_batch_jobs_workflow: Every 6 hours (0 */6 * * *)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dbos import DBOS

from src.batch_jobs.rechunk_service import (
    DEFAULT_STALE_JOB_THRESHOLD_HOURS,
    DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
    RechunkBatchJobService,
    get_stuck_jobs_info,
)
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

logger = get_logger(__name__)


def _cleanup_stale_jobs_sync(
    stale_threshold_hours: float = DEFAULT_STALE_JOB_THRESHOLD_HOURS,
) -> dict[str, Any]:
    """Synchronous wrapper for stale job cleanup logic."""
    from src.database import get_session_maker

    async def _async_impl() -> dict[str, Any]:
        async with get_session_maker()() as session:
            service = RechunkBatchJobService(session)
            failed_jobs = await service.cleanup_stale_jobs(
                stale_threshold_hours=stale_threshold_hours
            )

            result: dict[str, Any] = {
                "status": "completed",
                "cleaned_count": len(failed_jobs),
                "job_ids": [str(job.id) for job in failed_jobs],
                "threshold_hours": stale_threshold_hours,
                "executed_at": datetime.now(UTC).isoformat(),
            }

            if failed_jobs:
                logger.info(
                    "Scheduled cleanup marked stale jobs as failed",
                    extra={
                        "cleaned_count": len(failed_jobs),
                        "job_ids": result["job_ids"],
                        "threshold_hours": stale_threshold_hours,
                    },
                )
            else:
                logger.info(
                    "Scheduled cleanup found no stale jobs",
                    extra={"threshold_hours": stale_threshold_hours},
                )

            return result

    return run_sync(_async_impl())


def _monitor_stuck_jobs_sync(
    threshold_minutes: int = DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    """Synchronous wrapper for stuck job monitoring logic."""
    from src.database import get_session_maker

    async def _async_impl() -> dict[str, Any]:
        async with get_session_maker()() as session:
            stuck_jobs = await get_stuck_jobs_info(session, threshold_minutes=threshold_minutes)

            result: dict[str, Any] = {
                "status": "completed",
                "stuck_count": len(stuck_jobs),
                "threshold_minutes": threshold_minutes,
                "executed_at": datetime.now(UTC).isoformat(),
                "stuck_jobs": [
                    {
                        "job_id": str(job.job_id),
                        "job_type": job.job_type,
                        "status": job.status,
                        "stuck_duration_seconds": round(job.stuck_duration_seconds),
                    }
                    for job in stuck_jobs
                ],
            }

            if stuck_jobs:
                logger.warning(
                    "Scheduled monitor found stuck batch jobs",
                    extra={
                        "stuck_count": len(stuck_jobs),
                        "job_ids": [str(job.job_id) for job in stuck_jobs],
                        "threshold_minutes": threshold_minutes,
                    },
                )
            else:
                logger.debug(
                    "Scheduled monitor found no stuck jobs",
                    extra={"threshold_minutes": threshold_minutes},
                )

            return result

    return run_sync(_async_impl())


@DBOS.scheduled("0 0 * * 0")
@DBOS.workflow()
def cleanup_stale_batch_jobs_workflow(
    scheduled_time: datetime,
    actual_time: datetime,
) -> dict[str, Any]:
    """Scheduled workflow to clean up stale batch jobs.

    Runs weekly (Sunday midnight UTC) to mark jobs stuck in PENDING or
    IN_PROGRESS status as FAILED. Recovers from worker crashes or
    network failures that left jobs in a non-terminal state.

    Args:
        scheduled_time: When the workflow was scheduled to run
        actual_time: When the workflow actually started running
    """
    logger.info(
        "Starting scheduled stale job cleanup",
        extra={
            "scheduled_time": scheduled_time.isoformat(),
            "actual_time": actual_time.isoformat(),
        },
    )

    try:
        result = _cleanup_stale_jobs_sync()
        logger.info(
            "Scheduled stale job cleanup completed",
            extra={
                "cleaned_count": result["cleaned_count"],
                "scheduled_time": scheduled_time.isoformat(),
            },
        )
        return result
    except Exception as e:
        logger.error(
            "Scheduled stale job cleanup failed",
            extra={
                "error": str(e),
                "scheduled_time": scheduled_time.isoformat(),
            },
        )
        raise


@DBOS.scheduled("0 */6 * * *")
@DBOS.workflow()
def monitor_stuck_batch_jobs_workflow(
    scheduled_time: datetime,
    actual_time: datetime,
) -> dict[str, Any]:
    """Scheduled workflow to monitor for stuck batch jobs.

    Runs every 6 hours to check for jobs that appear stuck (in non-terminal
    status without recent updates). Logs warnings for any stuck jobs found.
    This is an informational check for alerting - it does NOT modify jobs.

    Args:
        scheduled_time: When the workflow was scheduled to run
        actual_time: When the workflow actually started running
    """
    logger.info(
        "Starting scheduled stuck jobs monitor",
        extra={
            "scheduled_time": scheduled_time.isoformat(),
            "actual_time": actual_time.isoformat(),
        },
    )

    try:
        result = _monitor_stuck_jobs_sync()
        logger.info(
            "Scheduled stuck jobs monitor completed",
            extra={
                "stuck_count": result["stuck_count"],
                "scheduled_time": scheduled_time.isoformat(),
            },
        )
        return result
    except Exception as e:
        logger.error(
            "Scheduled stuck jobs monitor failed",
            extra={
                "error": str(e),
                "scheduled_time": scheduled_time.isoformat(),
            },
        )
        raise


CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME: str = cleanup_stale_batch_jobs_workflow.__qualname__
MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME: str = monitor_stuck_batch_jobs_workflow.__qualname__
