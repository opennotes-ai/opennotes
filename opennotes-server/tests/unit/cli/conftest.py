"""Fixtures for CLI unit tests."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJob


@pytest.fixture
def mock_batch_job() -> BatchJob:
    """Create a mock batch job for testing."""
    job = MagicMock(spec=BatchJob)
    job.id = uuid4()
    job.job_type = "import:fact_check_bureau"
    job.status = "pending"
    job.total_tasks = 100
    job.completed_tasks = 0
    job.failed_tasks = 0
    job.metadata_ = {"batch_size": 1000}
    job.error_summary = None
    job.started_at = None
    job.completed_at = None
    job.created_at = datetime.now(UTC)
    job.is_terminal = False
    job.progress_percentage = 0.0
    return job


@pytest.fixture
def mock_completed_job(mock_batch_job: BatchJob) -> BatchJob:
    """Create a mock completed batch job."""
    mock_batch_job.status = "completed"
    mock_batch_job.completed_tasks = 100
    mock_batch_job.is_terminal = True
    mock_batch_job.completed_at = datetime.now(UTC)
    mock_batch_job.progress_percentage = 100.0
    return mock_batch_job


@pytest.fixture
def mock_failed_job(mock_batch_job: BatchJob) -> BatchJob:
    """Create a mock failed batch job."""
    mock_batch_job.status = "failed"
    mock_batch_job.completed_tasks = 50
    mock_batch_job.failed_tasks = 10
    mock_batch_job.is_terminal = True
    mock_batch_job.error_summary = {"error": "Test error"}
    return mock_batch_job


@pytest.fixture
def mock_import_service(mock_batch_job: BatchJob) -> AsyncMock:
    """Create a mock ImportBatchJobService."""
    service = AsyncMock()
    service.start_import_job = AsyncMock(return_value=mock_batch_job)
    service.start_scrape_job = AsyncMock(return_value=mock_batch_job)
    service.start_promotion_job = AsyncMock(return_value=mock_batch_job)
    return service


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_session_maker(mock_session: AsyncMock) -> MagicMock:
    """Create a mock session maker that returns the mock session."""

    class MockContextManager:
        async def __aenter__(self) -> AsyncMock:
            return mock_session

        async def __aexit__(self, *args: Any) -> None:
            pass

    maker = MagicMock()
    maker.return_value = MockContextManager()
    return maker
