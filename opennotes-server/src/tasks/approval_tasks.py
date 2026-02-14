"""
TaskIQ tasks for bulk candidate approval operations.

DEPRECATED: Bulk approval has been migrated to DBOS durable workflows.
See src/dbos_workflows/approval_workflow.py.

The @register_task stub below exists solely to drain legacy JetStream messages
that may still be in-flight. It returns {"status": "deprecated"} immediately.

Remove after 2026-04-01 when all legacy messages have been drained.
"""

from typing import Any

from src.batch_jobs.constants import BULK_APPROVAL_JOB_TYPE
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)


@register_task(
    task_name=BULK_APPROVAL_JOB_TYPE,
    component="fact_checking",
    task_type="deprecated",
)
async def process_bulk_approval(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Deprecated: TaskIQ stub to drain legacy JetStream messages.
    Bulk approval has been migrated to DBOS workflows.
    See src/dbos_workflows/approval_workflow.py
    """
    logger.info(
        "Deprecated TaskIQ stub: approve:candidates (draining legacy message)",
        extra={
            "task_name": BULK_APPROVAL_JOB_TYPE,
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "job_id": kwargs.get("job_id") if kwargs else None,
            "migration_note": "Task migrated to DBOS in TASK-1096",
        },
    )
    return {"status": "deprecated", "migrated_to": "dbos"}
