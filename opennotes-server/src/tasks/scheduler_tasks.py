"""
Scheduled tasks for periodic maintenance operations.

This module defines tasks that run on a schedule via TaskIQ's scheduler.
The scheduler must be run as a separate process:

    taskiq scheduler src.tasks.scheduler:scheduler

Tasks use the `schedule` label with cron expressions for timing.

Schedule expressions use standard cron format:
    minute hour day-of-month month day-of-week

Examples:
    "0 0 * * 0"   - Sunday at midnight UTC
    "0 */6 * * *" - Every 6 hours
    "30 2 * * *"  - Daily at 2:30 AM UTC
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.batch_jobs.rechunk_service import (
    DEFAULT_STALE_JOB_THRESHOLD_HOURS,
    DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
    RechunkBatchJobService,
    get_stuck_jobs_info,
)
from src.config import get_settings
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)


@register_task(
    task_name="scheduler:cleanup_stale_batch_jobs",
    component="scheduler",
    task_type="maintenance",
    schedule=[
        {
            "cron": "0 0 * * 0",
            "schedule_id": "weekly_stale_job_cleanup",
        }
    ],
)
async def cleanup_stale_batch_jobs_task(
    stale_threshold_hours: float = DEFAULT_STALE_JOB_THRESHOLD_HOURS,
) -> dict[str, Any]:
    """
    Scheduled task to clean up stale batch jobs.

    Runs weekly (Sunday midnight UTC) to mark jobs stuck in PENDING or
    IN_PROGRESS status as FAILED. This recovers from scenarios like
    worker crashes or network failures.

    Note:
        Creates its own database engine per execution. This is intentional for
        TaskIQ scheduled tasks: workers run as separate processes that may be
        restarted or scaled independently. Per-task engine creation ensures
        clean connection state with no shared resources between executions.
        For weekly execution frequency, this overhead is negligible.

    Args:
        stale_threshold_hours: Hours after which a job is considered stale.
            Defaults to 2 hours.

    Returns:
        dict with cleanup results including count and job IDs
    """
    settings = get_settings()

    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            service = RechunkBatchJobService(session)
            failed_jobs = await service.cleanup_stale_jobs(
                stale_threshold_hours=stale_threshold_hours
            )

            result = {
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

    except Exception as e:
        logger.error(
            "Scheduled cleanup failed",
            extra={"error": str(e), "threshold_hours": stale_threshold_hours},
        )
        raise
    finally:
        await engine.dispose()


@register_task(
    task_name="scheduler:monitor_stuck_batch_jobs",
    component="scheduler",
    task_type="monitoring",
    schedule=[
        {
            "cron": "*/15 * * * *",
            "schedule_id": "stuck_jobs_monitor",
        }
    ],
)
async def monitor_stuck_batch_jobs_task(
    threshold_minutes: int = DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    """
    Scheduled task to monitor for stuck batch jobs.

    Runs every 15 minutes to check for jobs that appear stuck (in non-terminal
    status without recent updates). Logs warnings for any stuck jobs found.
    This is an informational check for alerting - it does NOT modify jobs.

    Note:
        Creates its own database engine per execution. This is intentional for
        TaskIQ scheduled tasks: workers run as separate processes that may be
        restarted or scaled independently. Per-task engine creation ensures
        clean connection state with no shared resources between executions.

    Args:
        threshold_minutes: Minutes after which a job is considered stuck.
            Defaults to 30 minutes.

    Returns:
        dict with monitoring results including stuck job count and details
    """
    settings = get_settings()

    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            stuck_jobs = await get_stuck_jobs_info(session, threshold_minutes=threshold_minutes)

            result = {
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

    except Exception as e:
        logger.error(
            "Scheduled stuck jobs monitor failed",
            extra={"error": str(e), "threshold_minutes": threshold_minutes},
        )
        raise
    finally:
        await engine.dispose()
