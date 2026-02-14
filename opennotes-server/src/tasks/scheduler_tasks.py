"""
TaskIQ scheduled tasks -- deprecated, replaced by DBOS scheduled workflows.

DEPRECATED: Task bodies have been migrated to DBOS durable workflows
in src/dbos_workflows/scheduler_workflows.py (TASK-1097).

The @register_task decorated functions remain as no-op stubs to drain
legacy JetStream messages. They do NOT delegate to DBOS helpers to
avoid double-execution if both schedulers run during migration.

Remove deprecated stubs after 2026-04-01 when all legacy messages
have been drained.
"""

from typing import Any

from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)


@register_task(
    task_name="scheduler:cleanup_stale_batch_jobs",
    component="scheduler",
    task_type="deprecated",
    schedule=[
        {
            "cron": "0 0 * * 0",
            "schedule_id": "weekly_stale_job_cleanup",
        }
    ],
)
async def cleanup_stale_batch_jobs_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1097. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated scheduler:cleanup_stale_batch_jobs message - discarding",
        extra={
            "task_name": "scheduler:cleanup_stale_batch_jobs",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1097",
        },
    )
    return {"status": "deprecated", "migrated_to": "dbos"}


@register_task(
    task_name="scheduler:monitor_stuck_batch_jobs",
    component="scheduler",
    task_type="deprecated",
    schedule=[
        {
            "cron": "*/15 * * * *",
            "schedule_id": "stuck_jobs_monitor",
        }
    ],
)
async def monitor_stuck_batch_jobs_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1097. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated scheduler:monitor_stuck_batch_jobs message - discarding",
        extra={
            "task_name": "scheduler:monitor_stuck_batch_jobs",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1097",
        },
    )
    return {"status": "deprecated", "migrated_to": "dbos"}
