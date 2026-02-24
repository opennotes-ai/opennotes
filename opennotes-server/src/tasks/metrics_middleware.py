"""
TaskIQ metrics middleware for recording task execution duration.

This middleware integrates with the existing OTEL metrics
to record execution time for all TaskIQ tasks, providing visibility into
task performance in monitoring dashboards.

Metrics recorded:
- taskiq_task_duration_seconds: Histogram of task execution duration by task name
- taskiq_tasks_total: Counter of tasks by name and status (success/error)
"""

import logging
import time
from typing import Any

from taskiq import TaskiqMiddleware, TaskiqResult
from taskiq.message import TaskiqMessage

from src.monitoring.metrics import taskiq_task_duration_seconds, taskiq_tasks_total

logger = logging.getLogger(__name__)


class TaskIQMetricsMiddleware(TaskiqMiddleware):
    """
    Middleware that records execution time metrics for TaskIQ tasks.

    Records:
    - Task execution duration (histogram)
    - Task completion count by status (counter)

    Uses the existing OTEL metrics for consistency with
    other application metrics.
    """

    def __init__(self) -> None:
        super().__init__()
        self._start_times: dict[str, float] = {}

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Record task start time before execution."""
        self._start_times[message.task_id] = time.perf_counter()
        return message

    def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
    ) -> None:
        """Record task duration and status after execution."""
        start_time = self._start_times.pop(message.task_id, None)
        if start_time is None:
            logger.warning(f"No start time found for task {message.task_id}, skipping metrics")
            return

        duration = time.perf_counter() - start_time
        task_name = message.task_name

        taskiq_task_duration_seconds.record(duration, {"task_name": task_name})

        status = "error" if result.is_err else "success"
        taskiq_tasks_total.add(1, {"task_name": task_name, "status": status})

        logger.debug(f"Task {task_name} completed in {duration:.3f}s with status {status}")
