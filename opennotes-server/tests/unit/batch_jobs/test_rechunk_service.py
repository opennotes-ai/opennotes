"""
Unit tests for RechunkBatchJobService.

Tests rechunk job creation and cancellation, with focus on null community_server_id
handling to ensure task-896 and task-898 regressions are prevented.

Task: task-986.10 - Restore deleted test coverage
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJob
from src.batch_jobs.rechunk_service import (
    JOB_TYPE_FACT_CHECK,
    JOB_TYPE_PREVIOUSLY_SEEN,
    RechunkBatchJobService,
    RechunkType,
)


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
def mock_lock_manager():
    """Create a mock RechunkLockManager."""
    lock_manager = MagicMock()
    lock_manager.acquire_lock = AsyncMock(return_value=True)
    lock_manager.release_lock = AsyncMock(return_value=True)
    return lock_manager


@pytest.fixture
def mock_batch_job_service():
    """Create a mock BatchJobService."""
    service = MagicMock()
    service.create_job = AsyncMock()
    service.start_job = AsyncMock()
    service.cancel_job = AsyncMock()
    service.get_job = AsyncMock()
    service.fail_job = AsyncMock()
    return service


@pytest.fixture
def rechunk_service(mock_session, mock_lock_manager, mock_batch_job_service):
    """Create a RechunkBatchJobService with mocked dependencies."""
    return RechunkBatchJobService(
        session=mock_session,
        lock_manager=mock_lock_manager,
        batch_job_service=mock_batch_job_service,
    )


@pytest.mark.unit
class TestRechunkServiceNullCommunityServerId:
    """Tests for null community_server_id handling (task-896 regression)."""

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_start_fact_check_rechunk_job_with_null_community_server_id(
        self,
        mock_task,
        rechunk_service,
        mock_batch_job_service,
        mock_session,
    ):
        """Start fact check rechunk with null community_server_id stores None, not 'None' string."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_batch_job_service.start_job.return_value = mock_job
        mock_task.kiq = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 100
        mock_session.execute.return_value = mock_result

        result = await rechunk_service.start_fact_check_rechunk_job(
            community_server_id=None,
            batch_size=50,
        )

        assert result == mock_job
        mock_batch_job_service.create_job.assert_called_once()
        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]

        assert job_create.job_type == JOB_TYPE_FACT_CHECK
        assert job_create.metadata_["community_server_id"] is None
        assert job_create.metadata_["community_server_id"] != "None"
        assert job_create.metadata_["batch_size"] == 50
        assert job_create.metadata_["chunk_type"] == RechunkType.FACT_CHECK.value

    @pytest.mark.asyncio
    async def test_cancel_rechunk_job_with_null_community_server_id(
        self,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
    ):
        """Cancel rechunk job with null community_server_id releases fact_check lock correctly."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.metadata_ = {
            "community_server_id": None,
            "chunk_type": RechunkType.FACT_CHECK.value,
        }
        mock_batch_job_service.get_job.return_value = mock_job
        mock_batch_job_service.cancel_job.return_value = mock_job

        result = await rechunk_service.cancel_rechunk_job(job_id)

        assert result == mock_job
        mock_lock_manager.release_lock.assert_called_once_with("fact_check")


@pytest.mark.unit
class TestRechunkServiceMetadataSerialization:
    """Tests for metadata serialization (task-898 regression)."""

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_metadata_stores_null_not_string_none(
        self,
        mock_task,
        rechunk_service,
        mock_batch_job_service,
        mock_session,
    ):
        """Metadata community_server_id stores JSON null, not string 'None'."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_batch_job_service.start_job.return_value = mock_job
        mock_task.kiq = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 50
        mock_session.execute.return_value = mock_result

        await rechunk_service.start_fact_check_rechunk_job(
            community_server_id=None,
            batch_size=100,
        )

        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]
        metadata = job_create.metadata_

        assert "community_server_id" in metadata
        assert metadata["community_server_id"] is None
        assert not isinstance(metadata["community_server_id"], str)

    @pytest.mark.asyncio
    async def test_get_job_with_null_community_server_id_in_metadata(
        self,
        rechunk_service,
        mock_batch_job_service,
    ):
        """Get job correctly reads null community_server_id from metadata."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.metadata_ = {
            "community_server_id": None,
            "batch_size": 100,
            "chunk_type": RechunkType.FACT_CHECK.value,
        }
        mock_batch_job_service.get_job.return_value = mock_job
        mock_batch_job_service.cancel_job.return_value = mock_job

        result = await rechunk_service.cancel_rechunk_job(job_id)

        assert result.metadata_["community_server_id"] is None


@pytest.mark.unit
class TestRechunkServiceWithCommunityServerId:
    """Tests for previously_seen rechunk with community_server_id."""

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_previously_seen_rechunk_task")
    async def test_start_previously_seen_rechunk_job_stores_community_server_id_as_string(
        self,
        mock_task,
        rechunk_service,
        mock_batch_job_service,
        mock_session,
    ):
        """Previously seen rechunk stores community_server_id as string UUID."""
        job_id = uuid4()
        community_server_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_batch_job_service.start_job.return_value = mock_job
        mock_task.kiq = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 200
        mock_session.execute.return_value = mock_result

        result = await rechunk_service.start_previously_seen_rechunk_job(
            community_server_id=community_server_id,
            batch_size=100,
        )

        assert result == mock_job
        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]

        assert job_create.job_type == JOB_TYPE_PREVIOUSLY_SEEN
        assert job_create.metadata_["community_server_id"] == str(community_server_id)
        assert job_create.metadata_["chunk_type"] == RechunkType.PREVIOUSLY_SEEN.value

    @pytest.mark.asyncio
    async def test_cancel_previously_seen_job_releases_lock_with_community_id(
        self,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
    ):
        """Cancel previously_seen job releases lock with community_server_id."""
        job_id = uuid4()
        community_server_id = str(uuid4())
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.metadata_ = {
            "community_server_id": community_server_id,
            "chunk_type": RechunkType.PREVIOUSLY_SEEN.value,
        }
        mock_batch_job_service.get_job.return_value = mock_job
        mock_batch_job_service.cancel_job.return_value = mock_job

        result = await rechunk_service.cancel_rechunk_job(job_id)

        assert result == mock_job
        mock_lock_manager.release_lock.assert_called_once_with(
            "previously_seen", community_server_id
        )


@pytest.mark.unit
class TestRechunkServiceLockHandling:
    """Tests for lock acquisition and release."""

    @pytest.mark.asyncio
    async def test_lock_acquisition_failure_raises_runtime_error(
        self,
        rechunk_service,
        mock_lock_manager,
    ):
        """Lock acquisition failure raises RuntimeError."""
        mock_lock_manager.acquire_lock.return_value = False

        with pytest.raises(RuntimeError) as exc_info:
            await rechunk_service.start_fact_check_rechunk_job(
                community_server_id=None,
            )

        assert "already in progress" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_lock_released_on_job_creation_failure(
        self,
        mock_task,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
        mock_session,
    ):
        """Lock is released when job creation fails."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 100
        mock_session.execute.return_value = mock_result
        mock_batch_job_service.create_job.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await rechunk_service.start_fact_check_rechunk_job(
                community_server_id=None,
            )

        mock_lock_manager.release_lock.assert_called_once_with("fact_check")

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_lock_released_on_task_dispatch_failure(
        self,
        mock_task,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
        mock_session,
    ):
        """Lock is released when task dispatch fails."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_batch_job_service.create_job.return_value = mock_job
        mock_batch_job_service.start_job.return_value = mock_job
        mock_task.kiq = AsyncMock(side_effect=Exception("Task dispatch error"))

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 100
        mock_session.execute.return_value = mock_result

        with pytest.raises(Exception, match="Task dispatch error"):
            await rechunk_service.start_fact_check_rechunk_job(
                community_server_id=None,
            )

        mock_lock_manager.release_lock.assert_called_once_with("fact_check")
        mock_batch_job_service.fail_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_job_not_found_returns_none(
        self,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
    ):
        """Cancel returns None when job not found."""
        mock_batch_job_service.get_job.return_value = None

        result = await rechunk_service.cancel_rechunk_job(uuid4())

        assert result is None
        mock_lock_manager.release_lock.assert_not_called()


@pytest.mark.unit
class TestRechunkServiceEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_cancel_job_with_empty_metadata(
        self,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
    ):
        """Cancel job with empty metadata handles gracefully."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job.return_value = mock_job
        mock_batch_job_service.cancel_job.return_value = mock_job

        result = await rechunk_service.cancel_rechunk_job(job_id)

        assert result == mock_job
        mock_lock_manager.release_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_job_with_none_metadata(
        self,
        rechunk_service,
        mock_batch_job_service,
        mock_lock_manager,
    ):
        """Cancel job with None metadata handles gracefully."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.metadata_ = None
        mock_batch_job_service.get_job.return_value = mock_job
        mock_batch_job_service.cancel_job.return_value = mock_job

        result = await rechunk_service.cancel_rechunk_job(job_id)

        assert result == mock_job
        mock_lock_manager.release_lock.assert_not_called()
