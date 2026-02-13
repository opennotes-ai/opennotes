"""Deprecated TaskIQ scheduled tasks -- replaced by DBOS scheduled workflows.

These tasks have been migrated to src/dbos_workflows/scheduler_workflows.py:
    - cleanup_stale_batch_jobs_task -> cleanup_stale_batch_jobs_workflow
    - monitor_stuck_batch_jobs_task -> monitor_stuck_batch_jobs_workflow

The DBOS scheduled workflows run automatically when the DBOS worker is
launched. They use @DBOS.scheduled() with cron expressions and do not
require a separate TaskIQ scheduler process.

These stubs remain for backwards compatibility with any existing scheduled
invocations that may be in-flight. They delegate to the DBOS workflow
sync helpers.
"""

from typing import Any

from src.batch_jobs.rechunk_service import (
    DEFAULT_STALE_JOB_THRESHOLD_HOURS,
    DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
)
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
    """Deprecated: Use cleanup_stale_batch_jobs_workflow in src/dbos_workflows/scheduler_workflows.py."""
    logger.warning(
        "Deprecated TaskIQ cleanup_stale_batch_jobs_task invoked; use DBOS scheduled workflow instead",
    )
    from src.dbos_workflows.scheduler_workflows import _cleanup_stale_jobs_sync

    return _cleanup_stale_jobs_sync(stale_threshold_hours=stale_threshold_hours)


@register_task(
    task_name="scheduler:monitor_stuck_batch_jobs",
    component="scheduler",
    task_type="monitoring",
    schedule=[
        {
            "cron": "0 */6 * * *",
            "schedule_id": "stuck_jobs_monitor",
        }
    ],
)
async def monitor_stuck_batch_jobs_task(
    threshold_minutes: int = DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    """Deprecated: Use monitor_stuck_batch_jobs_workflow in src/dbos_workflows/scheduler_workflows.py."""
    logger.warning(
        "Deprecated TaskIQ monitor_stuck_batch_jobs_task invoked; use DBOS scheduled workflow instead",
    )
    from src.dbos_workflows.scheduler_workflows import _monitor_stuck_jobs_sync

    return _monitor_stuck_jobs_sync(threshold_minutes=threshold_minutes)
