"""
Unit tests for ImportBatchJobService.

Tests for start_scrape_job and start_promotion_job methods to verify
correct BatchJob creation and TaskIQ task dispatch.

Note: Rate limiting for concurrent jobs is now handled by DistributedRateLimitMiddleware,
not by the service layer. Lock management tests have been moved to middleware tests.

Task: task-1006.03 - Add start_scrape_job and start_promotion_job
Task: task-1006.08 - Add negative tests and improve ordering verification
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs import PROMOTION_JOB_TYPE, SCRAPE_JOB_TYPE
from src.batch_jobs.import_service import ImportBatchJobService
from src.batch_jobs.models import BatchJob


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy async session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_batch_job_service():
    """Create a mock BatchJobService."""
    service = MagicMock()
    service.create_job = AsyncMock()
    service.start_job = AsyncMock()
    service.get_job = AsyncMock()
    service.fail_job = AsyncMock()
    return service


@pytest.fixture
def import_service(mock_session, mock_batch_job_service):
    """Create an ImportBatchJobService with mocked dependencies."""
    service = ImportBatchJobService(session=mock_session)
    service._batch_job_service = mock_batch_job_service
    return service


@pytest.mark.unit
class TestStartScrapeJob:
    """Tests for start_scrape_job method."""

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_scrape_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_scrape_job_creates_job_with_correct_type(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_scrape_job creates BatchJob with job_type='scrape:candidates'."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_task.kiq = AsyncMock()
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        result = await import_service.start_scrape_job(
            batch_size=500,
            dry_run=False,
        )

        assert result == mock_job
        mock_batch_job_service.create_job.assert_called_once()
        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]

        assert job_create.job_type == SCRAPE_JOB_TYPE
        assert job_create.total_tasks == 0
        assert job_create.metadata_["batch_size"] == 500
        assert job_create.metadata_["dry_run"] is False

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_scrape_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_scrape_job_dispatches_taskiq_task(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_scrape_job dispatches process_scrape_batch TaskIQ task."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_task.kiq = AsyncMock()
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        await import_service.start_scrape_job(
            batch_size=500,
            dry_run=True,
        )

        mock_task.kiq.assert_called_once_with(
            job_id=str(job_id),
            batch_size=500,
            dry_run=True,
            db_url="postgresql://test",
            redis_url="redis://test",
            concurrency=10,
        )

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_scrape_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_scrape_job_commits_session_before_dispatch(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_scrape_job commits session before dispatching task.

        Verifies ordering via call sequence tracking: commit must happen
        before kiq() to ensure the job row exists for the worker.
        """
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        call_order = []

        async def track_commit():
            call_order.append("commit")

        async def track_kiq(**kwargs):
            call_order.append("kiq")

        mock_session.commit = AsyncMock(side_effect=track_commit)
        mock_task.kiq = AsyncMock(side_effect=track_kiq)

        await import_service.start_scrape_job()

        assert call_order == ["commit", "kiq"], f"Expected commit before kiq, got: {call_order}"

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_scrape_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_scrape_job_uses_default_batch_size(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_scrape_job uses default batch_size=1000."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_task.kiq = AsyncMock()
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        await import_service.start_scrape_job()

        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]
        assert job_create.metadata_["batch_size"] == 1000


@pytest.mark.unit
class TestStartPromotionJob:
    """Tests for start_promotion_job method."""

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_promotion_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_promotion_job_creates_job_with_correct_type(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_promotion_job creates BatchJob with job_type='promote:candidates'."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_task.kiq = AsyncMock()
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        result = await import_service.start_promotion_job(
            batch_size=500,
            dry_run=False,
        )

        assert result == mock_job
        mock_batch_job_service.create_job.assert_called_once()
        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]

        assert job_create.job_type == PROMOTION_JOB_TYPE
        assert job_create.total_tasks == 0
        assert job_create.metadata_["batch_size"] == 500
        assert job_create.metadata_["dry_run"] is False

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_promotion_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_promotion_job_dispatches_taskiq_task(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_promotion_job dispatches process_promotion_batch TaskIQ task."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_task.kiq = AsyncMock()
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        await import_service.start_promotion_job(
            batch_size=500,
            dry_run=True,
        )

        mock_task.kiq.assert_called_once_with(
            job_id=str(job_id),
            batch_size=500,
            dry_run=True,
            db_url="postgresql://test",
            redis_url="redis://test",
        )

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_promotion_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_promotion_job_commits_session_before_dispatch(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_promotion_job commits session before dispatching task.

        Verifies ordering via call sequence tracking: commit must happen
        before kiq() to ensure the job row exists for the worker.
        """
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        call_order = []

        async def track_commit():
            call_order.append("commit")

        async def track_kiq(**kwargs):
            call_order.append("kiq")

        mock_session.commit = AsyncMock(side_effect=track_commit)
        mock_task.kiq = AsyncMock(side_effect=track_kiq)

        await import_service.start_promotion_job()

        assert call_order == ["commit", "kiq"], f"Expected commit before kiq, got: {call_order}"

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_promotion_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_promotion_job_uses_default_batch_size(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_promotion_job uses default batch_size=1000."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_task.kiq = AsyncMock()
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        await import_service.start_promotion_job()

        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]
        assert job_create.metadata_["batch_size"] == 1000


@pytest.mark.unit
class TestKiqDispatchFailure:
    """Tests for kiq() dispatch failure scenarios.

    These tests verify that when TaskIQ dispatch fails, the job is marked
    as failed and the exception is re-raised.
    """

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_scrape_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_scrape_job_fails_job_on_kiq_exception(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_scrape_job marks job as failed when kiq() fails."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        mock_task.kiq = AsyncMock(side_effect=RuntimeError("NATS connection failed"))

        with pytest.raises(RuntimeError, match="NATS connection failed"):
            await import_service.start_scrape_job()

        mock_batch_job_service.fail_job.assert_called_once()
        fail_call = mock_batch_job_service.fail_job.call_args
        assert fail_call[0][0] == job_id
        assert "NATS connection failed" in fail_call[1]["error_summary"]["error"]
        assert fail_call[1]["error_summary"]["stage"] == "task_dispatch"

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_promotion_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_promotion_job_fails_job_on_kiq_exception(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_promotion_job marks job as failed when kiq() fails."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        mock_task.kiq = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        with pytest.raises(ConnectionError, match="Redis unavailable"):
            await import_service.start_promotion_job()

        mock_batch_job_service.fail_job.assert_called_once()
        fail_call = mock_batch_job_service.fail_job.call_args
        assert fail_call[0][0] == job_id
        assert "Redis unavailable" in fail_call[1]["error_summary"]["error"]
        assert fail_call[1]["error_summary"]["stage"] == "task_dispatch"

    @pytest.mark.asyncio
    @patch("src.tasks.import_tasks.process_scrape_batch")
    @patch("src.batch_jobs.import_service.get_settings")
    async def test_start_scrape_job_commits_after_fail_job(
        self,
        mock_get_settings,
        mock_task,
        import_service,
        mock_batch_job_service,
        mock_session,
    ):
        """start_scrape_job commits session after marking job as failed."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_get_settings.return_value = MagicMock(
            DATABASE_URL="postgresql://test",
            REDIS_URL="redis://test",
        )

        mock_task.kiq = AsyncMock(side_effect=RuntimeError("NATS connection failed"))

        with pytest.raises(RuntimeError):
            await import_service.start_scrape_job()

        assert mock_session.commit.call_count == 2  # Once for create, once for fail
        mock_session.refresh.assert_called_once_with(mock_job)
