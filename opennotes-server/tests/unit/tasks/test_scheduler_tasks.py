"""Unit tests for deprecated scheduler tasks (stubs).

Tests that the TaskIQ scheduler task registrations still exist
for backward compatibility, even though the real logic has moved
to DBOS scheduled workflows (src/dbos_workflows/scheduler_workflows.py).

Task: task-1097 - Migrate scheduler tasks to DBOS scheduled workflows
"""

from unittest.mock import patch

import pytest

from src.tasks.broker import get_registered_tasks


@pytest.mark.unit
class TestSchedulerTaskRegistration:
    """Tests for scheduler task registration (backward compat)."""

    def test_cleanup_stale_batch_jobs_task_is_registered(self):
        """Verify cleanup_stale_batch_jobs_task is still registered with broker."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()

        assert "scheduler:cleanup_stale_batch_jobs" in registered_tasks

    def test_cleanup_stale_batch_jobs_task_has_schedule_label(self):
        """Verify cleanup_stale_batch_jobs_task has schedule label for cron."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()
        _func, labels = registered_tasks["scheduler:cleanup_stale_batch_jobs"]

        assert "schedule" in labels
        schedule = labels["schedule"]
        assert isinstance(schedule, list)
        assert len(schedule) == 1
        assert schedule[0]["cron"] == "0 0 * * 0"
        assert schedule[0]["schedule_id"] == "weekly_stale_job_cleanup"

    def test_cleanup_stale_batch_jobs_task_has_correct_labels(self):
        """Verify cleanup_stale_batch_jobs_task has correct component and task_type labels."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()
        _func, labels = registered_tasks["scheduler:cleanup_stale_batch_jobs"]

        assert labels.get("component") == "scheduler"
        assert labels.get("task_type") == "maintenance"

    def test_monitor_stuck_batch_jobs_task_is_registered(self):
        """Verify monitor_stuck_batch_jobs_task is still registered with broker."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()

        assert "scheduler:monitor_stuck_batch_jobs" in registered_tasks

    def test_monitor_stuck_batch_jobs_task_has_schedule_label(self):
        """Verify monitor_stuck_batch_jobs_task has schedule label for cron."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()
        _func, labels = registered_tasks["scheduler:monitor_stuck_batch_jobs"]

        assert "schedule" in labels
        schedule = labels["schedule"]
        assert isinstance(schedule, list)
        assert len(schedule) == 1
        assert schedule[0]["cron"] == "0 */6 * * *"
        assert schedule[0]["schedule_id"] == "stuck_jobs_monitor"


@pytest.mark.unit
class TestDeprecatedStubDelegation:
    """Tests that deprecated stubs delegate to DBOS sync helpers."""

    @pytest.mark.asyncio
    async def test_cleanup_stub_delegates_to_dbos_helper(self):
        """cleanup_stale_batch_jobs_task delegates to _cleanup_stale_jobs_sync."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        expected = {
            "status": "completed",
            "cleaned_count": 0,
            "job_ids": [],
            "threshold_hours": 2,
            "executed_at": "2026-01-01T00:00:00+00:00",
        }

        with patch(
            "src.dbos_workflows.scheduler_workflows._cleanup_stale_jobs_sync",
            return_value=expected,
        ) as mock_cleanup:
            result = await cleanup_stale_batch_jobs_task()

        assert result == expected
        mock_cleanup.assert_called_once_with(stale_threshold_hours=2)

    @pytest.mark.asyncio
    async def test_monitor_stub_delegates_to_dbos_helper(self):
        """monitor_stuck_batch_jobs_task delegates to _monitor_stuck_jobs_sync."""
        from src.tasks.scheduler_tasks import monitor_stuck_batch_jobs_task

        expected = {
            "status": "completed",
            "stuck_count": 0,
            "threshold_minutes": 30,
            "executed_at": "2026-01-01T00:00:00+00:00",
            "stuck_jobs": [],
        }

        with patch(
            "src.dbos_workflows.scheduler_workflows._monitor_stuck_jobs_sync",
            return_value=expected,
        ) as mock_monitor:
            result = await monitor_stuck_batch_jobs_task()

        assert result == expected
        mock_monitor.assert_called_once_with(threshold_minutes=30)
