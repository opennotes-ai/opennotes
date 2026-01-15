"""
Unit tests for ImportBatchJobService.

Tests for start_scrape_job and start_promotion_job methods to verify
correct BatchJob creation and TaskIQ task dispatch.

Task: task-1006.03 - Add start_scrape_job and start_promotion_job
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

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

        assert job_create.job_type == "scrape:candidates"
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
        """start_scrape_job commits session before dispatching task."""
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

        mock_session.commit.assert_called_once()

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

        assert job_create.job_type == "promote:candidates"
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
        """start_promotion_job commits session before dispatching task."""
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

        mock_session.commit.assert_called_once()

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
