"""
TaskIQ metrics middleware for recording task execution duration.

This middleware integrates with the existing Prometheus metrics registry
to record execution time for all TaskIQ tasks, providing visibility into
task performance in monitoring dashboards.

Metrics recorded:
- taskiq_task_duration_seconds: Histogram of task execution duration by task name
- taskiq_tasks_total: Counter of tasks by name and status (success/error)
"""

import logging
import time
from typing import Any

from prometheus_client import Counter, Histogram
from taskiq import TaskiqMiddleware, TaskiqResult
from taskiq.message import TaskiqMessage

from src.monitoring.metrics import registry

logger = logging.getLogger(__name__)

taskiq_task_duration_seconds = Histogram(
    "taskiq_task_duration_seconds",
    "Duration of TaskIQ task execution in seconds",
    ["task_name", "instance_id"],
    registry=registry,
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

taskiq_tasks_total = Counter(
    "taskiq_tasks_total",
    "Total TaskIQ tasks executed",
    ["task_name", "status", "instance_id"],
    registry=registry,
)


class TaskIQMetricsMiddleware(TaskiqMiddleware):
    """
    Middleware that records execution time metrics for TaskIQ tasks.

    Records:
    - Task execution duration (histogram)
    - Task completion count by status (counter)

    Uses the existing Prometheus registry for consistency with
    other application metrics.
    """

    def __init__(self, instance_id: str = "default") -> None:
        super().__init__()
        self.instance_id = instance_id
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

        taskiq_task_duration_seconds.labels(
            task_name=task_name,
            instance_id=self.instance_id,
        ).observe(duration)

        status = "error" if result.is_err else "success"
        taskiq_tasks_total.labels(
            task_name=task_name,
            status=status,
            instance_id=self.instance_id,
        ).inc()

        logger.debug(f"Task {task_name} completed in {duration:.3f}s with status {status}")
