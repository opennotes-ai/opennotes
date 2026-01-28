"""Unit tests for BatchJobDBOSAdapter.

Tests the adapter layer that synchronizes DBOS workflow state to BatchJob records.
All adapter methods use fire-and-forget semantics - errors are logged but not raised.

Work Package: WP03 - BatchJob Adapter Layer
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobStatus
from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter


@pytest.fixture
def mock_batch_job():
    """Create a mock BatchJob instance."""
    job = MagicMock(spec=BatchJob)
    job.id = uuid4()
    job.workflow_id = "test-workflow-123"
    job.job_type = "rechunk:fact_check"
    job.status = BatchJobStatus.PENDING.value
    job.total_tasks = 100
    job.completed_tasks = 0
    job.failed_tasks = 0
    job.metadata_ = {}
    job.error_summary = None
    return job


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a session factory that returns a mock session as context manager."""

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory


@pytest.fixture
def mock_service(mock_batch_job):
    """Create a mock BatchJobService."""
    service = MagicMock()
    service.create_job = AsyncMock(return_value=mock_batch_job)
    service.get_job = AsyncMock(return_value=mock_batch_job)
    service.start_job = AsyncMock(return_value=mock_batch_job)
    service.complete_job = AsyncMock(return_value=mock_batch_job)
    service.fail_job = AsyncMock(return_value=mock_batch_job)
    service.cancel_job = AsyncMock(return_value=mock_batch_job)
    service.update_progress = AsyncMock(return_value=mock_batch_job)
    return service


@pytest.fixture
def adapter(mock_session_factory):
    """Create an adapter with mocked session factory."""
    return BatchJobDBOSAdapter(mock_session_factory)


@pytest.mark.unit
class TestBatchJobDBOSAdapterInit:
    """Tests for BatchJobDBOSAdapter initialization."""

    def test_accepts_session_factory(self):
        """Adapter accepts a session factory callable."""

        def session_factory():
            return MagicMock()

        adapter = BatchJobDBOSAdapter(session_factory)
        assert adapter._db_session_factory == session_factory

    def test_accepts_context_manager_factory(self, mock_session_factory):
        """Adapter accepts a context manager factory."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        assert adapter._db_session_factory == mock_session_factory


@pytest.mark.unit
class TestCreateForWorkflow:
    """Tests for create_for_workflow method."""

    @pytest.mark.asyncio
    async def test_creates_batch_job_with_workflow_id(
        self, adapter, mock_service, mock_batch_job
    ):
        """create_for_workflow creates a BatchJob with the workflow_id."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.create_for_workflow(
                workflow_id="test-workflow-123",
                job_type="rechunk:fact_check",
                total_tasks=100,
                metadata={"community_server_id": "server-456"},
            )

            assert result == mock_batch_job.id
            mock_service.create_job.assert_called_once()
            call_args = mock_service.create_job.call_args
            job_create = call_args[0][0]
            assert job_create.workflow_id == "test-workflow-123"
            assert job_create.job_type == "rechunk:fact_check"
            assert job_create.total_tasks == 100
            assert job_create.metadata_ == {"community_server_id": "server-456"}

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, adapter):
        """create_for_workflow returns None when an error occurs."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.return_value.create_job = AsyncMock(
                side_effect=Exception("Database error")
            )

            result = await adapter.create_for_workflow(
                workflow_id="test-workflow-123",
                job_type="rechunk:fact_check",
                total_tasks=100,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_logs_success(self, adapter, mock_service, mock_batch_job):
        """create_for_workflow logs success with all relevant fields."""
        with (
            patch(
                "src.dbos_workflows.batch_job_adapter.BatchJobService",
                return_value=mock_service,
            ),
            patch("src.dbos_workflows.batch_job_adapter.logger") as mock_logger,
        ):
            await adapter.create_for_workflow(
                workflow_id="test-workflow-123",
                job_type="rechunk:fact_check",
                total_tasks=100,
            )

            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            extra = call_kwargs["extra"]
            assert extra["workflow_id"] == "test-workflow-123"
            assert extra["job_type"] == "rechunk:fact_check"
            assert extra["total_tasks"] == 100


@pytest.mark.unit
class TestUpdateStatus:
    """Tests for update_status method."""

    @pytest.mark.asyncio
    async def test_updates_to_in_progress(self, adapter, mock_service, mock_batch_job):
        """update_status transitions to IN_PROGRESS via start_job."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_status(
                mock_batch_job.id, BatchJobStatus.IN_PROGRESS
            )

            assert result is True
            mock_service.start_job.assert_called_once_with(mock_batch_job.id)

    @pytest.mark.asyncio
    async def test_updates_to_completed(self, adapter, mock_service, mock_batch_job):
        """update_status transitions to COMPLETED via complete_job."""
        mock_batch_job.completed_tasks = 95
        mock_batch_job.failed_tasks = 5
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_status(
                mock_batch_job.id, BatchJobStatus.COMPLETED
            )

            assert result is True
            mock_service.complete_job.assert_called_once_with(
                mock_batch_job.id,
                completed_tasks=95,
                failed_tasks=5,
            )

    @pytest.mark.asyncio
    async def test_updates_to_failed_with_error_summary(
        self, adapter, mock_service, mock_batch_job
    ):
        """update_status transitions to FAILED with error_summary via fail_job."""
        error_summary = {"error": "Test failure", "count": 5}
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_status(
                mock_batch_job.id, BatchJobStatus.FAILED, error_summary=error_summary
            )

            assert result is True
            mock_service.fail_job.assert_called_once_with(
                mock_batch_job.id, error_summary
            )

    @pytest.mark.asyncio
    async def test_updates_to_cancelled(self, adapter, mock_service, mock_batch_job):
        """update_status transitions to CANCELLED via cancel_job."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_status(
                mock_batch_job.id, BatchJobStatus.CANCELLED
            )

            assert result is True
            mock_service.cancel_job.assert_called_once_with(mock_batch_job.id)

    @pytest.mark.asyncio
    async def test_returns_false_when_job_not_found(self, adapter, mock_service):
        """update_status returns False when BatchJob is not found."""
        mock_service.get_job = AsyncMock(return_value=None)
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_status(uuid4(), BatchJobStatus.IN_PROGRESS)

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, adapter):
        """update_status returns False when an error occurs."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.return_value.get_job = AsyncMock(
                side_effect=Exception("Database error")
            )

            result = await adapter.update_status(uuid4(), BatchJobStatus.IN_PROGRESS)

            assert result is False


@pytest.mark.unit
class TestUpdateProgress:
    """Tests for update_progress method."""

    @pytest.mark.asyncio
    async def test_sets_absolute_progress(self, adapter, mock_service, mock_batch_job):
        """update_progress sets absolute completed and failed counts."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_progress(
                mock_batch_job.id, completed_tasks=50, failed_tasks=5
            )

            assert result is True
            mock_service.update_progress.assert_called_once_with(
                mock_batch_job.id, completed_tasks=50, failed_tasks=5
            )

    @pytest.mark.asyncio
    async def test_increments_completed(self, adapter, mock_service, mock_batch_job):
        """update_progress increments completed_tasks by 1."""
        mock_batch_job.completed_tasks = 10
        mock_batch_job.failed_tasks = 2
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_progress(
                mock_batch_job.id, increment_completed=True
            )

            assert result is True
            mock_service.update_progress.assert_called_once_with(
                mock_batch_job.id, completed_tasks=11, failed_tasks=2
            )

    @pytest.mark.asyncio
    async def test_increments_failed(self, adapter, mock_service, mock_batch_job):
        """update_progress increments failed_tasks by 1."""
        mock_batch_job.completed_tasks = 10
        mock_batch_job.failed_tasks = 2
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_progress(
                mock_batch_job.id, increment_failed=True
            )

            assert result is True
            mock_service.update_progress.assert_called_once_with(
                mock_batch_job.id, completed_tasks=10, failed_tasks=3
            )

    @pytest.mark.asyncio
    async def test_increments_both(self, adapter, mock_service, mock_batch_job):
        """update_progress can increment both completed and failed."""
        mock_batch_job.completed_tasks = 10
        mock_batch_job.failed_tasks = 2
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_progress(
                mock_batch_job.id, increment_completed=True, increment_failed=True
            )

            assert result is True
            mock_service.update_progress.assert_called_once_with(
                mock_batch_job.id, completed_tasks=11, failed_tasks=3
            )

    @pytest.mark.asyncio
    async def test_returns_false_when_job_not_found(self, adapter, mock_service):
        """update_progress returns False when BatchJob is not found."""
        mock_service.get_job = AsyncMock(return_value=None)
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.update_progress(uuid4(), completed_tasks=50)

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, adapter):
        """update_progress returns False when an error occurs."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.return_value.get_job = AsyncMock(
                side_effect=Exception("Database error")
            )

            result = await adapter.update_progress(uuid4(), completed_tasks=50)

            assert result is False


@pytest.mark.unit
class TestFinalizeJob:
    """Tests for finalize_job method."""

    @pytest.mark.asyncio
    async def test_finalizes_successful_job(self, adapter, mock_service, mock_batch_job):
        """finalize_job marks job as completed when success=True."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.finalize_job(
                mock_batch_job.id,
                success=True,
                completed_tasks=95,
                failed_tasks=5,
            )

            assert result is True
            mock_service.complete_job.assert_called_once_with(
                mock_batch_job.id, 95, 5
            )

    @pytest.mark.asyncio
    async def test_finalizes_failed_job(self, adapter, mock_service, mock_batch_job):
        """finalize_job marks job as failed with error_summary when success=False."""
        error_summary = {"error": "Processing failed", "details": "timeout"}
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.finalize_job(
                mock_batch_job.id,
                success=False,
                completed_tasks=50,
                failed_tasks=50,
                error_summary=error_summary,
            )

            assert result is True
            mock_service.update_progress.assert_called_once_with(
                mock_batch_job.id, completed_tasks=50, failed_tasks=50
            )
            mock_service.fail_job.assert_called_once_with(
                mock_batch_job.id, error_summary
            )

    @pytest.mark.asyncio
    async def test_returns_false_when_job_not_found(self, adapter, mock_service):
        """finalize_job returns False when BatchJob is not found."""
        mock_service.get_job = AsyncMock(return_value=None)
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
            return_value=mock_service,
        ):
            result = await adapter.finalize_job(
                uuid4(), success=True, completed_tasks=100, failed_tasks=0
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, adapter):
        """finalize_job returns False when an error occurs."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.return_value.get_job = AsyncMock(
                side_effect=Exception("Database error")
            )

            result = await adapter.finalize_job(
                uuid4(), success=True, completed_tasks=100, failed_tasks=0
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_logs_finalization(self, adapter, mock_service, mock_batch_job):
        """finalize_job logs the finalization with all relevant fields."""
        with (
            patch(
                "src.dbos_workflows.batch_job_adapter.BatchJobService",
                return_value=mock_service,
            ),
            patch("src.dbos_workflows.batch_job_adapter.logger") as mock_logger,
        ):
            await adapter.finalize_job(
                mock_batch_job.id,
                success=True,
                completed_tasks=95,
                failed_tasks=5,
            )

            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            extra = call_kwargs["extra"]
            assert extra["success"] is True
            assert extra["completed"] == 95
            assert extra["failed"] == 5


@pytest.mark.unit
class TestGetJobByWorkflowId:
    """Tests for get_job_by_workflow_id method."""

    @pytest.mark.asyncio
    async def test_returns_job_when_found(
        self, adapter, mock_session, mock_session_factory, mock_batch_job
    ):
        """get_job_by_workflow_id returns BatchJob when found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_batch_job)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await adapter.get_job_by_workflow_id("test-workflow-123")

        assert result == mock_batch_job
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, adapter, mock_session, mock_session_factory
    ):
        """get_job_by_workflow_id returns None when job not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await adapter.get_job_by_workflow_id("nonexistent-workflow")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, adapter, mock_session, mock_session_factory):
        """get_job_by_workflow_id returns None when an error occurs."""
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))

        result = await adapter.get_job_by_workflow_id("test-workflow-123")

        assert result is None


@pytest.mark.unit
class TestSyncWrappers:
    """Tests for synchronous wrapper methods."""

    @pytest.mark.asyncio
    async def test_create_for_workflow_sync_calls_async(
        self, adapter, mock_service, mock_batch_job
    ):
        """create_for_workflow_sync wraps the async method."""
        with (
            patch(
                "src.dbos_workflows.batch_job_adapter.BatchJobService",
                return_value=mock_service,
            ),
            patch("asyncio.run") as mock_run,
        ):
            mock_run.return_value = mock_batch_job.id

            result = adapter.create_for_workflow_sync(
                workflow_id="test-workflow-123",
                job_type="rechunk:fact_check",
                total_tasks=100,
            )

            assert result == mock_batch_job.id
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_sync_calls_async(self, adapter, mock_batch_job):
        """update_status_sync wraps the async method."""
        with patch("asyncio.run") as mock_run:
            mock_run.return_value = True

            result = adapter.update_status_sync(
                mock_batch_job.id, BatchJobStatus.IN_PROGRESS
            )

            assert result is True
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_sync_calls_async(self, adapter, mock_batch_job):
        """update_progress_sync wraps the async method."""
        with patch("asyncio.run") as mock_run:
            mock_run.return_value = True

            result = adapter.update_progress_sync(
                mock_batch_job.id, completed_tasks=50
            )

            assert result is True
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_job_sync_calls_async(self, adapter, mock_batch_job):
        """finalize_job_sync wraps the async method."""
        with patch("asyncio.run") as mock_run:
            mock_run.return_value = True

            result = adapter.finalize_job_sync(
                mock_batch_job.id,
                success=True,
                completed_tasks=100,
                failed_tasks=0,
            )

            assert result is True
            mock_run.assert_called_once()


@pytest.mark.unit
class TestAdapterNeverRaises:
    """Tests verifying adapter methods never raise exceptions."""

    @pytest.mark.asyncio
    async def test_create_never_raises(self, adapter):
        """create_for_workflow never raises exceptions."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.side_effect = RuntimeError("Catastrophic failure")

            result = await adapter.create_for_workflow(
                workflow_id="test", job_type="test", total_tasks=1
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_update_status_never_raises(self, adapter):
        """update_status never raises exceptions."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.side_effect = RuntimeError("Catastrophic failure")

            result = await adapter.update_status(uuid4(), BatchJobStatus.IN_PROGRESS)

            assert result is False

    @pytest.mark.asyncio
    async def test_update_progress_never_raises(self, adapter):
        """update_progress never raises exceptions."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.side_effect = RuntimeError("Catastrophic failure")

            result = await adapter.update_progress(uuid4(), completed_tasks=50)

            assert result is False

    @pytest.mark.asyncio
    async def test_finalize_never_raises(self, adapter):
        """finalize_job never raises exceptions."""
        with patch(
            "src.dbos_workflows.batch_job_adapter.BatchJobService",
        ) as mock_service_class:
            mock_service_class.side_effect = RuntimeError("Catastrophic failure")

            result = await adapter.finalize_job(
                uuid4(), success=True, completed_tasks=100, failed_tasks=0
            )

            assert result is False
