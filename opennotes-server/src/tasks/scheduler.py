"""Deprecated TaskIQ scheduler configuration.

Scheduled tasks have been migrated to DBOS scheduled workflows in
src/dbos_workflows/scheduler_workflows.py. The DBOS worker handles
scheduling automatically via @DBOS.scheduled() decorators.

This module is retained only for backwards compatibility. The TaskIQ
scheduler process (taskiq scheduler src.tasks.scheduler:scheduler) is
no longer needed and should not be deployed.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

import src.tasks.scheduler_tasks  # noqa: F401  # pyright: ignore[reportUnusedImport]
from src.tasks.broker import get_broker

scheduler = TaskiqScheduler(
    broker=get_broker(),
    sources=[LabelScheduleSource(get_broker())],
)
