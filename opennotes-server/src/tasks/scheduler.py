"""
TaskIQ scheduler configuration.

This module configures the TaskIQ scheduler for running scheduled tasks.
The scheduler uses LabelScheduleSource to discover tasks with `schedule`
labels and dispatch them according to their cron/interval configuration.

Usage:
    # Run the scheduler as a separate process:
    taskiq scheduler src.tasks.scheduler:scheduler --skip-first-run

    # Or with specific modules:
    taskiq scheduler src.tasks.scheduler:scheduler src.tasks.scheduler_tasks

The scheduler queries registered tasks for schedule labels and dispatches
them to the broker at the configured times. Workers then execute the tasks
as normal background jobs.

Note: The scheduler process must be running for scheduled tasks to execute.
It's separate from the worker process and should be deployed as its own service.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

import src.tasks.scheduler_tasks  # noqa: F401  # pyright: ignore[reportUnusedImport]
from src.tasks.broker import get_broker

scheduler = TaskiqScheduler(
    broker=get_broker(),
    sources=[LabelScheduleSource(get_broker())],
)
