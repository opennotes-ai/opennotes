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

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.batch_jobs.rechunk_service import (
    DEFAULT_STALE_JOB_THRESHOLD_HOURS,
    RechunkBatchJobService,
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
) -> dict:
    """
    Scheduled task to clean up stale batch jobs.

    Runs weekly (Sunday midnight UTC) to mark jobs stuck in PENDING or
    IN_PROGRESS status as FAILED. This recovers from scenarios like
    worker crashes or network failures.

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
