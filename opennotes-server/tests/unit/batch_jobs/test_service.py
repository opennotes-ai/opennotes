from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobStatus
from src.batch_jobs.service import BatchJobService


def _make_job(status: BatchJobStatus) -> BatchJob:
    return BatchJob(
        id=uuid4(),
        job_type="url_scan",
        status=status.value,
        total_tasks=10,
        completed_tasks=0,
        failed_tasks=0,
        metadata_={"source": "url_scan"},
    )


def _locked_result(job: BatchJob) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    return result


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def progress_tracker() -> AsyncMock:
    tracker = AsyncMock()
    tracker.start_tracking = AsyncMock()
    tracker.stop_tracking = AsyncMock()
    tracker.update_progress = AsyncMock()
    return tracker


@pytest.fixture
def service(mock_session: AsyncMock, progress_tracker: AsyncMock) -> BatchJobService:
    return BatchJobService(session=mock_session, progress_tracker=progress_tracker)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transition_job_status_starts_tracking_for_extracting(
    service: BatchJobService,
    mock_session: AsyncMock,
    progress_tracker: AsyncMock,
) -> None:
    job = _make_job(BatchJobStatus.PENDING)
    mock_session.execute.return_value = _locked_result(job)

    updated_job = await service.transition_job_status(job.id, BatchJobStatus.EXTRACTING)

    assert updated_job is job
    assert job.status == BatchJobStatus.EXTRACTING.value
    assert job.started_at is not None
    progress_tracker.start_tracking.assert_awaited_once_with(job.id)
    progress_tracker.stop_tracking.assert_not_awaited()
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transition_job_status_advances_extracting_to_analyzing_without_restarting_tracking(
    service: BatchJobService,
    mock_session: AsyncMock,
    progress_tracker: AsyncMock,
) -> None:
    job = _make_job(BatchJobStatus.EXTRACTING)
    job.started_at = datetime(2026, 5, 4, tzinfo=UTC)
    mock_session.execute.return_value = _locked_result(job)

    await service.transition_job_status(job.id, BatchJobStatus.ANALYZING)

    assert job.status == BatchJobStatus.ANALYZING.value
    assert job.started_at == datetime(2026, 5, 4, tzinfo=UTC)
    progress_tracker.start_tracking.assert_not_awaited()
    progress_tracker.stop_tracking.assert_not_awaited()
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_job_preserves_legacy_in_progress_entrypoint(
    service: BatchJobService,
    mock_session: AsyncMock,
    progress_tracker: AsyncMock,
) -> None:
    job = _make_job(BatchJobStatus.PENDING)
    mock_session.execute.return_value = _locked_result(job)

    updated_job = await service.start_job(job.id)

    assert updated_job is job
    assert job.status == BatchJobStatus.IN_PROGRESS.value
    assert job.started_at is not None
    progress_tracker.start_tracking.assert_awaited_once_with(job.id)
    progress_tracker.stop_tracking.assert_not_awaited()
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starting_status", "terminal_method", "expected_status"),
    [
        (BatchJobStatus.EXTRACTING, "complete_job", BatchJobStatus.COMPLETED),
        (BatchJobStatus.ANALYZING, "fail_job", BatchJobStatus.FAILED),
        (BatchJobStatus.EXTRACTING, "cancel_job", BatchJobStatus.CANCELLED),
    ],
)
async def test_terminal_methods_accept_url_scan_active_statuses(
    service: BatchJobService,
    mock_session: AsyncMock,
    progress_tracker: AsyncMock,
    starting_status: BatchJobStatus,
    terminal_method: str,
    expected_status: BatchJobStatus,
) -> None:
    job = _make_job(starting_status)
    mock_session.execute.return_value = _locked_result(job)

    method = getattr(service, terminal_method)
    if terminal_method == "complete_job":
        updated_job = await method(job.id, completed_tasks=7, failed_tasks=1)
    elif terminal_method == "fail_job":
        updated_job = await method(
            job.id,
            error_summary={"reason": "analysis_failed"},
            completed_tasks=4,
            failed_tasks=2,
        )
    else:
        updated_job = await method(job.id)

    assert updated_job is job
    assert job.status == expected_status.value
    assert job.completed_at is not None
    progress_tracker.stop_tracking.assert_awaited_once_with(job.id)
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_partial_job_is_terminal_and_cleans_up_tracking(
    service: BatchJobService,
    mock_session: AsyncMock,
    progress_tracker: AsyncMock,
) -> None:
    job = _make_job(BatchJobStatus.ANALYZING)
    mock_session.execute.return_value = _locked_result(job)

    updated_job = await service.partial_job(
        job.id,
        completed_tasks=6,
        failed_tasks=2,
        error_summary={"reason": "some_items_failed"},
    )

    assert updated_job is job
    assert job.status == BatchJobStatus.PARTIAL.value
    assert job.completed_at is not None
    assert job.completed_tasks == 6
    assert job.failed_tasks == 2
    assert job.error_summary == {"reason": "some_items_failed"}
    progress_tracker.stop_tracking.assert_awaited_once_with(job.id)
    mock_session.commit.assert_awaited_once()
