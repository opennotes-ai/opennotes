"""
Unit tests for BatchJobDBOSAdapter.

Tests the adapter's fire-and-forget behavior and DBOS-to-BatchJob synchronization.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobStatus
from src.dbos_workflows.batch_job_adapter import BatchJobDBOSAdapter, fire_and_forget


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy async session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a mock session factory that returns an async context manager."""

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory


@pytest.mark.unit
class TestFireAndForgetDecorator:
    """Tests for fire_and_forget decorator."""

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        """Decorated function returns result when successful."""

        @fire_and_forget(default_return="fallback")
        async def successful_func() -> str:
            return "success"

        result = await successful_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_returns_default_on_exception(self):
        """Decorated function returns default value on exception."""

        @fire_and_forget(default_return="default")
        async def failing_func() -> str:
            raise RuntimeError("Intentional failure")

        result = await failing_func()
        assert result == "default"

    @pytest.mark.asyncio
    async def test_logs_error_on_exception(self):
        """Decorated function logs error when exception occurs."""

        @fire_and_forget(default_return=None)
        async def failing_func() -> None:
            raise ValueError("Test error")

        with patch("src.dbos_workflows.batch_job_adapter.logger") as mock_logger:
            await failing_func()
            mock_logger.error.assert_called_once()


@pytest.mark.unit
class TestBatchJobDBOSAdapterCreateForWorkflow:
    """Tests for create_for_workflow method."""

    @pytest.mark.asyncio
    async def test_creates_batch_job_with_workflow_id(self, mock_session_factory):
        """create_for_workflow creates BatchJob with correct parameters."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)

        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(return_value=mock_job)
            mock_service_class.return_value = mock_service

            result = await adapter.create_for_workflow(
                workflow_id="wf-123",
                job_type="rechunk:fact_check",
                total_tasks=100,
                metadata={"key": "value"},
            )

            assert result == job_id
            mock_service.create_job.assert_called_once()
            create_call = mock_service.create_job.call_args
            job_create = create_call[0][0]
            assert job_create.workflow_id == "wf-123"
            assert job_create.job_type == "rechunk:fact_check"
            assert job_create.total_tasks == 100

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, mock_session_factory):
        """create_for_workflow returns None on database error (fire-and-forget)."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(side_effect=Exception("DB error"))
            mock_service_class.return_value = mock_service

            result = await adapter.create_for_workflow(
                workflow_id="wf-123",
                job_type="rechunk:fact_check",
                total_tasks=100,
            )

            assert result is None


@pytest.mark.unit
class TestBatchJobDBOSAdapterUpdateStatus:
    """Tests for update_status method."""

    @pytest.mark.asyncio
    async def test_updates_status_to_in_progress(self, mock_session_factory):
        """update_status calls start_job for IN_PROGRESS status."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.completed_tasks = 0
        mock_job.failed_tasks = 0

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.start_job = AsyncMock()
            mock_service_class.return_value = mock_service

            result = await adapter.update_status(job_id, BatchJobStatus.IN_PROGRESS)

            assert result is True
            mock_service.start_job.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_updates_status_to_completed(self, mock_session_factory):
        """update_status calls complete_job for COMPLETED status."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.completed_tasks = 50
        mock_job.failed_tasks = 5

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.complete_job = AsyncMock()
            mock_service_class.return_value = mock_service

            result = await adapter.update_status(job_id, BatchJobStatus.COMPLETED)

            assert result is True
            mock_service.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_job_not_found(self, mock_session_factory):
        """update_status returns False when BatchJob not found."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            result = await adapter.update_status(job_id, BatchJobStatus.IN_PROGRESS)

            assert result is False


@pytest.mark.unit
class TestBatchJobDBOSAdapterUpdateProgress:
    """Tests for update_progress method."""

    @pytest.mark.asyncio
    async def test_updates_absolute_progress_counts(self, mock_session_factory):
        """update_progress sets absolute completed and failed counts."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.completed_tasks = 10
        mock_job.failed_tasks = 2
        mock_job.total_tasks = 100

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.update_progress = AsyncMock()
            mock_service_class.return_value = mock_service

            result = await adapter.update_progress(
                job_id, completed_tasks=50, failed_tasks=10
            )

            assert result is True
            mock_service.update_progress.assert_called_once()
            call_kwargs = mock_service.update_progress.call_args[1]
            assert call_kwargs["completed_tasks"] == 50
            assert call_kwargs["failed_tasks"] == 10

    @pytest.mark.asyncio
    async def test_increments_completed_tasks(self, mock_session_factory):
        """update_progress increments completed_tasks when flag is True."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_job.completed_tasks = 10
        mock_job.failed_tasks = 2
        mock_job.total_tasks = 100

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.update_progress = AsyncMock()
            mock_service_class.return_value = mock_service

            result = await adapter.update_progress(job_id, increment_completed=True)

            assert result is True
            mock_service.update_progress.assert_called_once()
            call_kwargs = mock_service.update_progress.call_args[1]
            assert call_kwargs["completed_tasks"] == 11


@pytest.mark.unit
class TestBatchJobDBOSAdapterFinalizeJob:
    """Tests for finalize_job method."""

    @pytest.mark.asyncio
    async def test_finalizes_successful_job(self, mock_session_factory):
        """finalize_job completes job when success=True."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.complete_job = AsyncMock()
            mock_service_class.return_value = mock_service

            result = await adapter.finalize_job(
                job_id, success=True, completed_tasks=90, failed_tasks=10
            )

            assert result is True
            mock_service.complete_job.assert_called_once_with(job_id, 90, 10)

    @pytest.mark.asyncio
    async def test_finalizes_failed_job_with_error_summary(self, mock_session_factory):
        """finalize_job fails job when success=False."""
        adapter = BatchJobDBOSAdapter(mock_session_factory)
        job_id = uuid4()

        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id

        with patch("src.dbos_workflows.batch_job_adapter.BatchJobService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.update_progress = AsyncMock()
            mock_service.fail_job = AsyncMock()
            mock_service_class.return_value = mock_service

            error_summary = {"errors": ["Error 1"]}
            result = await adapter.finalize_job(
                job_id,
                success=False,
                completed_tasks=50,
                failed_tasks=50,
                error_summary=error_summary,
            )

            assert result is True
            mock_service.fail_job.assert_called_once_with(job_id, error_summary)
