"""
Unit tests for TaskIQ metrics middleware.

Tests verify that the middleware correctly records task execution
duration and completion metrics without requiring actual NATS/Redis.
"""

from unittest.mock import MagicMock, patch

import pytest
from taskiq import TaskiqResult
from taskiq.message import TaskiqMessage


class TestTaskIQMetricsMiddleware:
    """Test TaskIQMetricsMiddleware functionality."""

    @pytest.fixture
    def mock_metrics(self):
        """Patch the OTEL metrics to verify they are called correctly."""
        with (
            patch("src.tasks.metrics_middleware.taskiq_task_duration_seconds") as mock_duration,
            patch("src.tasks.metrics_middleware.taskiq_tasks_total") as mock_total,
        ):
            mock_duration.record = MagicMock()
            mock_total.add = MagicMock()
            yield {"duration": mock_duration, "total": mock_total}

    def test_pre_execute_stores_start_time(self, mock_metrics) -> None:
        """pre_execute should store the start time for the task."""
        from src.tasks.metrics_middleware import TaskIQMetricsMiddleware

        middleware = TaskIQMetricsMiddleware()

        message = TaskiqMessage(
            task_id="test-task-123",
            task_name="test:my_task",
            labels={},
            args=[],
            kwargs={},
        )

        result = middleware.pre_execute(message)

        assert result is message
        assert "test-task-123" in middleware._start_times
        assert isinstance(middleware._start_times["test-task-123"], float)

    def test_post_execute_records_duration_for_success(self, mock_metrics) -> None:
        """post_execute should record duration and success status."""
        from src.tasks.metrics_middleware import TaskIQMetricsMiddleware

        middleware = TaskIQMetricsMiddleware()

        message = TaskiqMessage(
            task_id="test-task-456",
            task_name="content:batch_scan",
            labels={},
            args=[],
            kwargs={},
        )

        middleware.pre_execute(message)

        result = TaskiqResult(
            is_err=False,
            log=None,
            return_value={"status": "completed"},
            execution_time=1.5,
        )

        middleware.post_execute(message, result)

        mock_metrics["duration"].record.assert_called_once()
        call_args = mock_metrics["duration"].record.call_args
        assert call_args[0][1] == {"task_name": "content:batch_scan"}

        mock_metrics["total"].add.assert_called_once_with(
            1, {"task_name": "content:batch_scan", "status": "success"}
        )

        assert "test-task-456" not in middleware._start_times

    def test_post_execute_records_error_status(self, mock_metrics) -> None:
        """post_execute should record error status when task fails."""
        from src.tasks.metrics_middleware import TaskIQMetricsMiddleware

        middleware = TaskIQMetricsMiddleware()

        message = TaskiqMessage(
            task_id="test-task-789",
            task_name="content:ai_note",
            labels={},
            args=[],
            kwargs={},
        )

        middleware.pre_execute(message)

        result = TaskiqResult(
            is_err=True,
            log=None,
            return_value=None,
            execution_time=0.5,
        )

        middleware.post_execute(message, result)

        mock_metrics["total"].add.assert_called_once_with(
            1, {"task_name": "content:ai_note", "status": "error"}
        )

    def test_post_execute_handles_missing_start_time(self, mock_metrics) -> None:
        """post_execute should handle case where pre_execute wasn't called."""
        from src.tasks.metrics_middleware import TaskIQMetricsMiddleware

        middleware = TaskIQMetricsMiddleware()

        message = TaskiqMessage(
            task_id="orphan-task",
            task_name="unknown:task",
            labels={},
            args=[],
            kwargs={},
        )

        result = TaskiqResult(
            is_err=False,
            log=None,
            return_value=None,
            execution_time=1.0,
        )

        middleware.post_execute(message, result)

        mock_metrics["duration"].record.assert_not_called()
        mock_metrics["total"].add.assert_not_called()

    def test_middleware_cleans_up_start_time(self, mock_metrics) -> None:
        """post_execute should remove the start time after recording."""
        from src.tasks.metrics_middleware import TaskIQMetricsMiddleware

        middleware = TaskIQMetricsMiddleware()

        message = TaskiqMessage(
            task_id="cleanup-test",
            task_name="test:cleanup",
            labels={},
            args=[],
            kwargs={},
        )

        middleware.pre_execute(message)
        assert "cleanup-test" in middleware._start_times

        result = TaskiqResult(
            is_err=False,
            log=None,
            return_value=None,
            execution_time=0.1,
        )

        middleware.post_execute(message, result)
        assert "cleanup-test" not in middleware._start_times
