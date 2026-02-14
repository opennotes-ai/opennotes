"""Unit tests for deprecated scheduler tasks (no-op stubs).

Tests that the TaskIQ scheduler task registrations exist as no-op stubs
for backward compatibility, and that they do NOT delegate to DBOS helpers.
The real logic lives in src/dbos_workflows/scheduler_workflows.py.

Task: TASK-1097.01 - Address review findings in scheduler DBOS workflows
"""

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

    def test_cleanup_stale_batch_jobs_task_has_deprecated_type(self):
        """Verify cleanup_stale_batch_jobs_task is marked as deprecated."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()
        _func, labels = registered_tasks["scheduler:cleanup_stale_batch_jobs"]

        assert labels.get("component") == "scheduler"
        assert labels.get("task_type") == "deprecated"

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
        assert schedule[0]["cron"] == "*/15 * * * *"
        assert schedule[0]["schedule_id"] == "stuck_jobs_monitor"

    def test_monitor_stuck_batch_jobs_task_has_deprecated_type(self):
        """Verify monitor_stuck_batch_jobs_task is marked as deprecated."""
        import src.tasks.scheduler_tasks  # noqa: F401

        registered_tasks = get_registered_tasks()
        _func, labels = registered_tasks["scheduler:monitor_stuck_batch_jobs"]

        assert labels.get("component") == "scheduler"
        assert labels.get("task_type") == "deprecated"


@pytest.mark.unit
class TestDeprecatedStubsAreNoOps:
    """Tests that deprecated stubs are no-ops and do NOT delegate to DBOS helpers."""

    @pytest.mark.asyncio
    async def test_cleanup_stub_returns_deprecated_status(self):
        """cleanup_stale_batch_jobs_task returns deprecated status without doing work."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        result = await cleanup_stale_batch_jobs_task()

        assert result == {"status": "deprecated", "migrated_to": "dbos"}

    @pytest.mark.asyncio
    async def test_monitor_stub_returns_deprecated_status(self):
        """monitor_stuck_batch_jobs_task returns deprecated status without doing work."""
        from src.tasks.scheduler_tasks import monitor_stuck_batch_jobs_task

        result = await monitor_stuck_batch_jobs_task()

        assert result == {"status": "deprecated", "migrated_to": "dbos"}

    @pytest.mark.asyncio
    async def test_cleanup_stub_accepts_arbitrary_args(self):
        """cleanup_stale_batch_jobs_task accepts any args for legacy compatibility."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        result = await cleanup_stale_batch_jobs_task("arg1", key="value")

        assert result["status"] == "deprecated"

    @pytest.mark.asyncio
    async def test_monitor_stub_accepts_arbitrary_args(self):
        """monitor_stuck_batch_jobs_task accepts any args for legacy compatibility."""
        from src.tasks.scheduler_tasks import monitor_stuck_batch_jobs_task

        result = await monitor_stuck_batch_jobs_task("arg1", key="value")

        assert result["status"] == "deprecated"
