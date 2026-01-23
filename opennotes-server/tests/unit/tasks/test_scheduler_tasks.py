"""
Unit tests for scheduler tasks.

Tests scheduled task registration and execution.
Task: task-1043 - Add monitoring/alerting and cleanup scheduler
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.broker import get_registered_tasks


@pytest.mark.unit
class TestSchedulerTaskRegistration:
    """Tests for scheduler task registration."""

    def test_cleanup_stale_batch_jobs_task_is_registered(self):
        """Verify cleanup_stale_batch_jobs_task is registered with broker."""
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


@pytest.mark.unit
class TestCleanupStaleBatchJobsTaskExecution:
    """Tests for cleanup_stale_batch_jobs_task execution."""

    @pytest.mark.asyncio
    @patch("src.tasks.scheduler_tasks.create_async_engine")
    @patch("src.tasks.scheduler_tasks.async_sessionmaker")
    @patch("src.tasks.scheduler_tasks.RechunkBatchJobService")
    async def test_cleanup_stale_batch_jobs_task_calls_cleanup(
        self,
        mock_service_class,
        mock_sessionmaker,
        mock_create_engine,
    ):
        """cleanup_stale_batch_jobs_task calls cleanup_stale_jobs method."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        mock_job = MagicMock()
        mock_job.id = "test-job-id"

        mock_service = MagicMock()
        mock_service.cleanup_stale_jobs = AsyncMock(return_value=[mock_job])
        mock_service_class.return_value = mock_service

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_sessionmaker.return_value.return_value = mock_session

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine

        result = await cleanup_stale_batch_jobs_task()

        mock_service.cleanup_stale_jobs.assert_called_once()
        assert result["status"] == "completed"
        assert result["cleaned_count"] == 1
        assert "test-job-id" in result["job_ids"]

    @pytest.mark.asyncio
    @patch("src.tasks.scheduler_tasks.create_async_engine")
    @patch("src.tasks.scheduler_tasks.async_sessionmaker")
    @patch("src.tasks.scheduler_tasks.RechunkBatchJobService")
    async def test_cleanup_stale_batch_jobs_task_with_custom_threshold(
        self,
        mock_service_class,
        mock_sessionmaker,
        mock_create_engine,
    ):
        """cleanup_stale_batch_jobs_task respects custom threshold parameter."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        mock_service = MagicMock()
        mock_service.cleanup_stale_jobs = AsyncMock(return_value=[])
        mock_service_class.return_value = mock_service

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_sessionmaker.return_value.return_value = mock_session

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine

        result = await cleanup_stale_batch_jobs_task(stale_threshold_hours=4.0)

        mock_service.cleanup_stale_jobs.assert_called_once_with(stale_threshold_hours=4.0)
        assert result["threshold_hours"] == 4.0

    @pytest.mark.asyncio
    @patch("src.tasks.scheduler_tasks.create_async_engine")
    @patch("src.tasks.scheduler_tasks.async_sessionmaker")
    @patch("src.tasks.scheduler_tasks.RechunkBatchJobService")
    async def test_cleanup_stale_batch_jobs_task_disposes_engine(
        self,
        mock_service_class,
        mock_sessionmaker,
        mock_create_engine,
    ):
        """cleanup_stale_batch_jobs_task properly disposes database engine."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        mock_service = MagicMock()
        mock_service.cleanup_stale_jobs = AsyncMock(return_value=[])
        mock_service_class.return_value = mock_service

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_sessionmaker.return_value.return_value = mock_session

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine

        await cleanup_stale_batch_jobs_task()

        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.tasks.scheduler_tasks.create_async_engine")
    @patch("src.tasks.scheduler_tasks.async_sessionmaker")
    @patch("src.tasks.scheduler_tasks.RechunkBatchJobService")
    async def test_cleanup_stale_batch_jobs_task_disposes_engine_on_error(
        self,
        mock_service_class,
        mock_sessionmaker,
        mock_create_engine,
    ):
        """cleanup_stale_batch_jobs_task disposes engine even on error."""
        from src.tasks.scheduler_tasks import cleanup_stale_batch_jobs_task

        mock_service = MagicMock()
        mock_service.cleanup_stale_jobs = AsyncMock(side_effect=Exception("Test error"))
        mock_service_class.return_value = mock_service

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_sessionmaker.return_value.return_value = mock_session

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine

        with pytest.raises(Exception, match="Test error"):
            await cleanup_stale_batch_jobs_task()

        mock_engine.dispose.assert_called_once()
