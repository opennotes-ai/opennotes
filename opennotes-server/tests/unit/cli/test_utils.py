"""Unit tests for CLI utilities."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.batch_jobs.models import BatchJob
from src.cli.utils import (
    format_job_output,
    run_async,
)


class TestRunAsync:
    """Tests for run_async helper."""

    def test_run_async_executes_coroutine(self) -> None:
        """Test that run_async executes a coroutine and returns result."""

        async def sample_coro() -> str:
            return "result"

        result = run_async(sample_coro())
        assert result == "result"

    def test_run_async_handles_exception(self) -> None:
        """Test that run_async propagates exceptions."""

        async def failing_coro() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing_coro())


class TestFormatJobOutput:
    """Tests for format_job_output."""

    def test_format_basic_output(self) -> None:
        """Test basic job output formatting."""
        job = MagicMock(spec=BatchJob)
        job.id = "test-job-123"
        job.status = "pending"
        job.total_tasks = 100
        job.completed_tasks = 0
        job.failed_tasks = 0
        job.job_type = "import:fact_check_bureau"
        job.started_at = None
        job.completed_at = None
        job.metadata_ = {}
        job.error_summary = None

        output = format_job_output(job)

        assert "Job ID: test-job-123" in output
        assert "Status: pending" in output
        assert "Progress: 0/100" in output

    def test_format_with_failed_tasks(self) -> None:
        """Test output includes failed task count."""
        job = MagicMock(spec=BatchJob)
        job.id = "test-job-123"
        job.status = "in_progress"
        job.total_tasks = 100
        job.completed_tasks = 50
        job.failed_tasks = 5
        job.job_type = "import:fact_check_bureau"
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.metadata_ = {}
        job.error_summary = None

        output = format_job_output(job)

        assert "Progress: 50/100" in output
        assert "Failed: 5" in output

    def test_format_verbose_includes_details(self) -> None:
        """Test verbose output includes additional details."""
        job = MagicMock(spec=BatchJob)
        job.id = "test-job-123"
        job.status = "completed"
        job.total_tasks = 100
        job.completed_tasks = 100
        job.failed_tasks = 0
        job.job_type = "import:fact_check_bureau"
        job.started_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        job.completed_at = datetime(2024, 1, 1, 12, 5, 0, tzinfo=UTC)
        job.metadata_ = {"batch_size": 1000}
        job.error_summary = None

        output = format_job_output(job, verbose=True)

        assert "Type: import:fact_check_bureau" in output
        assert "Started:" in output
        assert "Completed:" in output
        assert "Metadata:" in output
        assert "batch_size" in output

    def test_format_with_zero_total_tasks(self) -> None:
        """Test output when total_tasks is 0."""
        job = MagicMock(spec=BatchJob)
        job.id = "test-job-123"
        job.status = "completed"
        job.total_tasks = 0
        job.completed_tasks = 50
        job.failed_tasks = 0
        job.job_type = "import:fact_check_bureau"
        job.started_at = None
        job.completed_at = None
        job.metadata_ = {}
        job.error_summary = None

        output = format_job_output(job)

        assert "Completed: 50" in output
        assert "Progress:" not in output

    def test_format_with_error_summary(self) -> None:
        """Test verbose output includes error summary."""
        job = MagicMock(spec=BatchJob)
        job.id = "test-job-123"
        job.status = "failed"
        job.total_tasks = 100
        job.completed_tasks = 50
        job.failed_tasks = 10
        job.job_type = "import:fact_check_bureau"
        job.started_at = datetime.now(UTC)
        job.completed_at = datetime.now(UTC)
        job.metadata_ = {}
        job.error_summary = {"error": "Connection timeout", "count": 10}

        output = format_job_output(job, verbose=True)

        assert "Errors:" in output
        assert "Connection timeout" in output
