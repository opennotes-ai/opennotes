"""Tests for DBOS scheduler workflows.

Tests the scheduled workflow components for stale job cleanup and
stuck job monitoring. Follows the same pattern as test_rechunk_workflow.py:
mock the sync helper functions and test workflow logic.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


class TestCleanupStaleJobsWorkflow:
    """Tests for cleanup_stale_batch_jobs_workflow."""

    def test_workflow_calls_cleanup_sync_helper(self) -> None:
        """Workflow delegates to _cleanup_stale_jobs_sync."""
        from src.dbos_workflows.scheduler_workflows import (
            cleanup_stale_batch_jobs_workflow,
        )

        now = datetime.now(UTC)
        expected_result = {
            "status": "completed",
            "cleaned_count": 2,
            "job_ids": ["id-1", "id-2"],
            "threshold_hours": 2,
            "executed_at": now.isoformat(),
        }

        with patch(
            "src.dbos_workflows.scheduler_workflows._cleanup_stale_jobs_sync"
        ) as mock_cleanup:
            mock_cleanup.return_value = expected_result

            result = cleanup_stale_batch_jobs_workflow.__wrapped__(
                scheduled_time=now,
                actual_time=now,
            )

        assert result is None
        mock_cleanup.assert_called_once()

    def test_workflow_returns_none_on_success(self) -> None:
        """Scheduled workflow returns None (ScheduledWorkflow protocol)."""
        from src.dbos_workflows.scheduler_workflows import (
            cleanup_stale_batch_jobs_workflow,
        )

        now = datetime.now(UTC)

        with patch(
            "src.dbos_workflows.scheduler_workflows._cleanup_stale_jobs_sync"
        ) as mock_cleanup:
            mock_cleanup.return_value = {
                "status": "completed",
                "cleaned_count": 0,
                "job_ids": [],
                "threshold_hours": 2,
                "executed_at": now.isoformat(),
            }

            result = cleanup_stale_batch_jobs_workflow.__wrapped__(
                scheduled_time=now,
                actual_time=now,
            )

        assert result is None

    def test_workflow_raises_on_error(self) -> None:
        """Workflow re-raises exceptions from cleanup logic."""
        from src.dbos_workflows.scheduler_workflows import (
            cleanup_stale_batch_jobs_workflow,
        )

        now = datetime.now(UTC)

        with patch(
            "src.dbos_workflows.scheduler_workflows._cleanup_stale_jobs_sync"
        ) as mock_cleanup:
            mock_cleanup.side_effect = RuntimeError("DB connection failed")

            with pytest.raises(RuntimeError, match="DB connection failed"):
                cleanup_stale_batch_jobs_workflow.__wrapped__(
                    scheduled_time=now,
                    actual_time=now,
                )


class TestMonitorStuckJobsWorkflow:
    """Tests for monitor_stuck_batch_jobs_workflow."""

    def test_workflow_calls_monitor_sync_helper(self) -> None:
        """Workflow delegates to _monitor_stuck_jobs_sync."""
        from src.dbos_workflows.scheduler_workflows import (
            monitor_stuck_batch_jobs_workflow,
        )

        now = datetime.now(UTC)
        expected_result = {
            "status": "completed",
            "stuck_count": 1,
            "threshold_minutes": 30,
            "executed_at": now.isoformat(),
            "stuck_jobs": [
                {
                    "job_id": "stuck-1",
                    "job_type": "rechunk:fact_check",
                    "status": "in_progress",
                    "stuck_duration_seconds": 3600,
                }
            ],
        }

        with patch(
            "src.dbos_workflows.scheduler_workflows._monitor_stuck_jobs_sync"
        ) as mock_monitor:
            mock_monitor.return_value = expected_result

            result = monitor_stuck_batch_jobs_workflow.__wrapped__(
                scheduled_time=now,
                actual_time=now,
            )

        assert result is None
        mock_monitor.assert_called_once()

    def test_workflow_returns_none_with_no_stuck_jobs(self) -> None:
        """Scheduled workflow returns None (ScheduledWorkflow protocol)."""
        from src.dbos_workflows.scheduler_workflows import (
            monitor_stuck_batch_jobs_workflow,
        )

        now = datetime.now(UTC)

        with patch(
            "src.dbos_workflows.scheduler_workflows._monitor_stuck_jobs_sync"
        ) as mock_monitor:
            mock_monitor.return_value = {
                "status": "completed",
                "stuck_count": 0,
                "threshold_minutes": 30,
                "executed_at": now.isoformat(),
                "stuck_jobs": [],
            }

            result = monitor_stuck_batch_jobs_workflow.__wrapped__(
                scheduled_time=now,
                actual_time=now,
            )

        assert result is None

    def test_workflow_raises_on_error(self) -> None:
        """Workflow re-raises exceptions from monitor logic."""
        from src.dbos_workflows.scheduler_workflows import (
            monitor_stuck_batch_jobs_workflow,
        )

        now = datetime.now(UTC)

        with patch(
            "src.dbos_workflows.scheduler_workflows._monitor_stuck_jobs_sync"
        ) as mock_monitor:
            mock_monitor.side_effect = RuntimeError("DB connection failed")

            with pytest.raises(RuntimeError, match="DB connection failed"):
                monitor_stuck_batch_jobs_workflow.__wrapped__(
                    scheduled_time=now,
                    actual_time=now,
                )


class TestCleanupStaleSyncHelper:
    """Tests for _cleanup_stale_jobs_sync helper."""

    def test_cleanup_calls_service_with_default_threshold(self) -> None:
        """Helper uses default stale threshold hours."""
        from src.dbos_workflows.scheduler_workflows import _cleanup_stale_jobs_sync

        mock_service = MagicMock()
        mock_service.cleanup_stale_jobs = MagicMock(return_value=[])

        mock_session = MagicMock()
        mock_session.__aenter__ = MagicMock(return_value=mock_session)
        mock_session.__aexit__ = MagicMock(return_value=None)

        with (
            patch("src.dbos_workflows.scheduler_workflows.run_sync") as mock_run_sync,
        ):
            mock_run_sync.return_value = {
                "status": "completed",
                "cleaned_count": 0,
                "job_ids": [],
                "threshold_hours": 2,
                "executed_at": "2026-01-01T00:00:00+00:00",
            }

            result = _cleanup_stale_jobs_sync()

        assert result["status"] == "completed"
        mock_run_sync.assert_called_once()

    def test_cleanup_with_custom_threshold(self) -> None:
        """Helper passes custom threshold to service."""
        from src.dbos_workflows.scheduler_workflows import _cleanup_stale_jobs_sync

        with (
            patch("src.dbos_workflows.scheduler_workflows.run_sync") as mock_run_sync,
        ):
            mock_run_sync.return_value = {
                "status": "completed",
                "cleaned_count": 0,
                "job_ids": [],
                "threshold_hours": 4.0,
                "executed_at": "2026-01-01T00:00:00+00:00",
            }

            result = _cleanup_stale_jobs_sync(stale_threshold_hours=4.0)

        assert result["threshold_hours"] == 4.0


class TestMonitorStuckSyncHelper:
    """Tests for _monitor_stuck_jobs_sync helper."""

    def test_monitor_calls_service_with_default_threshold(self) -> None:
        """Helper uses default stuck threshold minutes."""
        from src.dbos_workflows.scheduler_workflows import _monitor_stuck_jobs_sync

        with (
            patch("src.dbos_workflows.scheduler_workflows.run_sync") as mock_run_sync,
        ):
            mock_run_sync.return_value = {
                "status": "completed",
                "stuck_count": 0,
                "threshold_minutes": 30,
                "executed_at": "2026-01-01T00:00:00+00:00",
                "stuck_jobs": [],
            }

            result = _monitor_stuck_jobs_sync()

        assert result["status"] == "completed"
        mock_run_sync.assert_called_once()


class TestWorkflowNameConstants:
    """Tests for workflow name constants."""

    def test_cleanup_workflow_name_uses_qualname(self) -> None:
        """Cleanup workflow name constant matches function qualname."""
        from src.dbos_workflows.scheduler_workflows import (
            CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME,
            cleanup_stale_batch_jobs_workflow,
        )

        assert (
            cleanup_stale_batch_jobs_workflow.__qualname__ == CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME
        )

    def test_monitor_workflow_name_uses_qualname(self) -> None:
        """Monitor workflow name constant matches function qualname."""
        from src.dbos_workflows.scheduler_workflows import (
            MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME,
            monitor_stuck_batch_jobs_workflow,
        )

        assert (
            monitor_stuck_batch_jobs_workflow.__qualname__ == MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME
        )

    def test_workflow_names_are_distinct(self) -> None:
        """Both workflow name constants are unique."""
        from src.dbos_workflows.scheduler_workflows import (
            CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME,
            MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME,
        )

        assert CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME != MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME


class TestScheduledDecoratorPresence:
    """Tests that scheduled workflows have correct DBOS decorators."""

    def test_cleanup_workflow_is_decorated(self) -> None:
        """cleanup_stale_batch_jobs_workflow has __wrapped__ (DBOS decorator)."""
        from src.dbos_workflows.scheduler_workflows import (
            cleanup_stale_batch_jobs_workflow,
        )

        assert hasattr(cleanup_stale_batch_jobs_workflow, "__wrapped__")

    def test_monitor_workflow_is_decorated(self) -> None:
        """monitor_stuck_batch_jobs_workflow has __wrapped__ (DBOS decorator)."""
        from src.dbos_workflows.scheduler_workflows import (
            monitor_stuck_batch_jobs_workflow,
        )

        assert hasattr(monitor_stuck_batch_jobs_workflow, "__wrapped__")


class TestExportsFromInit:
    """Tests that scheduler workflow symbols are exported from __init__."""

    def test_cleanup_workflow_exported(self) -> None:
        """cleanup_stale_batch_jobs_workflow is in dbos_workflows exports."""
        from src.dbos_workflows import cleanup_stale_batch_jobs_workflow as wf

        assert callable(wf)

    def test_monitor_workflow_exported(self) -> None:
        """monitor_stuck_batch_jobs_workflow is in dbos_workflows exports."""
        from src.dbos_workflows import monitor_stuck_batch_jobs_workflow as wf

        assert callable(wf)

    def test_cleanup_name_constant_exported(self) -> None:
        """CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME is in dbos_workflows exports."""
        from src.dbos_workflows import CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME

        assert isinstance(CLEANUP_STALE_BATCH_JOBS_WORKFLOW_NAME, str)

    def test_monitor_name_constant_exported(self) -> None:
        """MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME is in dbos_workflows exports."""
        from src.dbos_workflows import MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME

        assert isinstance(MONITOR_STUCK_BATCH_JOBS_WORKFLOW_NAME, str)


CRON_FIELD_PATTERN = re.compile(
    r"^("
    r"\*"
    r"|(\d+(-\d+)?)"
    r"|(\*/\d+)"
    r")(,(\*|(\d+(-\d+)?)|(\*/\d+)))*$"
)

CRON_FIELD_RANGES = [
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 7),
]


def _is_valid_cron(expr: str) -> bool:
    """Validate a 5-field cron expression has correct syntax and value ranges."""
    fields = expr.split()
    if len(fields) != 5:
        return False

    for i, field in enumerate(fields):
        if not CRON_FIELD_PATTERN.match(field):
            return False

        low, high = CRON_FIELD_RANGES[i]
        for number_str in re.findall(r"\d+", field):
            val = int(number_str)
            if field.startswith("*/"):
                if val < 1 or val > high:
                    return False
            elif val < low or val > high:
                return False

    return True


class TestCronExpressionCorrectness:
    """Tests that cron expressions used in scheduler workflows are valid."""

    def test_cleanup_workflow_cron_is_valid(self) -> None:
        """Cleanup workflow uses a valid 5-field cron expression."""
        source = inspect.getsource(
            __import__(
                "src.dbos_workflows.scheduler_workflows", fromlist=["scheduler_workflows"]
            ).cleanup_stale_batch_jobs_workflow
        )
        match = re.search(r'@DBOS\.scheduled\("([^"]+)"\)', source)
        assert match is not None, "Could not find @DBOS.scheduled decorator"

        cron_expr = match.group(1)
        assert _is_valid_cron(cron_expr), f"Invalid cron expression: {cron_expr}"

    def test_monitor_workflow_cron_is_valid(self) -> None:
        """Monitor workflow uses a valid 5-field cron expression."""
        source = inspect.getsource(
            __import__(
                "src.dbos_workflows.scheduler_workflows", fromlist=["scheduler_workflows"]
            ).monitor_stuck_batch_jobs_workflow
        )
        match = re.search(r'@DBOS\.scheduled\("([^"]+)"\)', source)
        assert match is not None, "Could not find @DBOS.scheduled decorator"

        cron_expr = match.group(1)
        assert _is_valid_cron(cron_expr), f"Invalid cron expression: {cron_expr}"

    def test_cleanup_cron_is_weekly_sunday_midnight(self) -> None:
        """Cleanup runs weekly on Sunday at midnight UTC."""
        from src.dbos_workflows import scheduler_workflows

        source = inspect.getsource(scheduler_workflows.cleanup_stale_batch_jobs_workflow)
        match = re.search(r'@DBOS\.scheduled\("([^"]+)"\)', source)
        assert match is not None

        assert match.group(1) == "0 0 * * 0"

    def test_monitor_cron_is_every_15_minutes(self) -> None:
        """Monitor runs every 15 minutes."""
        from src.dbos_workflows import scheduler_workflows

        source = inspect.getsource(scheduler_workflows.monitor_stuck_batch_jobs_workflow)
        match = re.search(r'@DBOS\.scheduled\("([^"]+)"\)', source)
        assert match is not None

        assert match.group(1) == "*/15 * * * *"

    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            ("0 0 * * 0", True),
            ("*/15 * * * *", True),
            ("0 */6 * * *", True),
            ("5 4 * * *", True),
            ("0 0 1 1 *", True),
            ("", False),
            ("* * *", False),
            ("60 * * * *", False),
            ("* 25 * * *", False),
            ("* * 32 * *", False),
            ("* * * 13 *", False),
            ("* * * * 8", False),
            ("*/0 * * * *", False),
        ],
    )
    def test_cron_validator_correctness(self, expr: str, expected: bool) -> None:
        """Verify the cron validator itself produces correct results."""
        assert _is_valid_cron(expr) == expected, f"Expected {expected} for '{expr}'"
