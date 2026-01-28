"""
Integration tests for rechunk batch job workflows.

These tests verify:
- SC-001: Rechunk job completes successfully
- SC-002: Job resumes from checkpoint (via stale job cleanup/recovery)
- SC-003: BatchJob API returns valid responses
- SC-004: API response shape unchanged for consumers
- SC-008: Concurrent job handling

Note: The original WP06 spec referenced DBOS workflows, but the actual
implementation uses TaskIQ with PostgreSQL advisory locks for concurrency
control and Redis for progress tracking.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from src.batch_jobs.constants import (
    RECHUNK_FACT_CHECK_JOB_TYPE,
    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
)
from src.batch_jobs.models import BatchJob
from src.batch_jobs.rechunk_service import (
    ActiveJobExistsError,
    RechunkBatchJobService,
    get_stuck_jobs_info,
)
from src.batch_jobs.schemas import BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.database import get_session_maker


@pytest.mark.integration
class TestRechunkJobRecovery:
    """Tests for job recovery and stale job cleanup (SC-002)."""

    @pytest.mark.asyncio
    async def test_stale_job_cleanup_marks_jobs_failed(self) -> None:
        """
        Test that stale jobs are marked as failed during cleanup.

        SC-002: Given a job is stuck in IN_PROGRESS, when cleanup_stale_jobs
        is called, then the job is marked FAILED with appropriate error summary.
        """
        async with get_session_maker()() as session:
            stale_job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                completed_tasks=50,
                metadata_={
                    "community_server_id": None,
                    "batch_size": 100,
                    "chunk_type": "fact_check",
                },
                created_at=datetime.now(UTC) - timedelta(hours=3),
                started_at=datetime.now(UTC) - timedelta(hours=3),
                updated_at=datetime.now(UTC) - timedelta(hours=3),
            )
            session.add(stale_job)
            await session.commit()
            stale_job_id = stale_job.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            cleaned_jobs = await service.cleanup_stale_jobs(stale_threshold_hours=2)

            assert len(cleaned_jobs) == 1
            assert cleaned_jobs[0].id == stale_job_id
            assert cleaned_jobs[0].status == BatchJobStatus.FAILED.value
            assert cleaned_jobs[0].error_summary is not None
            assert "stale" in cleaned_jobs[0].error_summary.get("error", "").lower()

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == stale_job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    async def test_active_job_not_cleaned_up(self) -> None:
        """
        Test that recently updated jobs are not cleaned up.

        Jobs that have been updated within the threshold should not be marked as stale.
        """
        async with get_session_maker()() as session:
            active_job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                completed_tasks=50,
                metadata_={
                    "community_server_id": None,
                    "batch_size": 100,
                    "chunk_type": "fact_check",
                },
                created_at=datetime.now(UTC) - timedelta(hours=1),
                started_at=datetime.now(UTC) - timedelta(hours=1),
                updated_at=datetime.now(UTC),
            )
            session.add(active_job)
            await session.commit()
            active_job_id = active_job.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            cleaned_jobs = await service.cleanup_stale_jobs(stale_threshold_hours=2)

            assert len(cleaned_jobs) == 0

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == active_job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    async def test_get_stuck_jobs_info_identifies_stuck_jobs(self) -> None:
        """
        Test that get_stuck_jobs_info correctly identifies stuck jobs.

        This helps with monitoring and alerting for jobs that need attention.
        """
        async with get_session_maker()() as session:
            stuck_job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                completed_tasks=0,
                metadata_={"community_server_id": None},
                created_at=datetime.now(UTC) - timedelta(hours=1),
                started_at=datetime.now(UTC) - timedelta(hours=1),
                updated_at=datetime.now(UTC) - timedelta(minutes=45),
            )
            session.add(stuck_job)
            await session.commit()
            stuck_job_id = stuck_job.id

        async with get_session_maker()() as session:
            stuck_jobs = await get_stuck_jobs_info(session, threshold_minutes=30)

            assert len(stuck_jobs) >= 1
            stuck_job_info = next((j for j in stuck_jobs if j.job_id == stuck_job_id), None)
            assert stuck_job_info is not None
            assert stuck_job_info.status == BatchJobStatus.IN_PROGRESS.value
            assert stuck_job_info.stuck_duration_seconds > 30 * 60

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == stuck_job_id))
            await cleanup_session.commit()


@pytest.mark.integration
class TestRechunkJobCompletion:
    """Tests for successful job completion (SC-001)."""

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_job_completes_successfully(self, mock_task: AsyncMock) -> None:
        """
        Test that a batch job transitions through states correctly to completion.

        SC-001: Rechunk job completes successfully with proper state transitions.
        """
        mock_task.kiq = AsyncMock()

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            job = await service.start_fact_check_rechunk_job(
                community_server_id=None,
                batch_size=100,
            )
            job_id = job.id

            assert job.status == BatchJobStatus.IN_PROGRESS.value
            assert job.started_at is not None

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            completed_job = await batch_job_service.complete_job(
                job_id=job_id,
                completed_tasks=100,
                failed_tasks=0,
            )

            assert completed_job is not None
            assert completed_job.status == BatchJobStatus.COMPLETED.value
            assert completed_job.completed_tasks == 100
            assert completed_job.failed_tasks == 0
            assert completed_job.completed_at is not None

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_job_records_partial_progress_on_failure(self, mock_task: AsyncMock) -> None:
        """
        Test that partial progress is preserved when a job fails.

        This ensures we can resume from where we left off.
        """
        mock_task.kiq = AsyncMock()

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            job = await service.start_fact_check_rechunk_job(
                community_server_id=None,
                batch_size=100,
            )
            job_id = job.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)

            await batch_job_service.update_progress(
                job_id=job_id,
                completed_tasks=50,
                failed_tasks=5,
            )

            failed_job = await batch_job_service.fail_job(
                job_id=job_id,
                error_summary={"error": "Test error", "reason": "Simulated failure"},
                completed_tasks=50,
                failed_tasks=5,
            )

            assert failed_job is not None
            assert failed_job.status == BatchJobStatus.FAILED.value
            assert failed_job.completed_tasks == 50
            assert failed_job.failed_tasks == 5
            assert failed_job.error_summary is not None
            assert "Test error" in failed_job.error_summary.get("error", "")

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()


@pytest.mark.integration
class TestRechunkAPICompatibility:
    """Tests for API compatibility (SC-003, SC-004)."""

    @pytest.mark.asyncio
    async def test_batch_job_response_shape(self) -> None:
        """
        Test that BatchJob API response includes all expected fields.

        SC-003 & SC-004: Verify API response shape is correct for all consumers.
        """
        async with get_session_maker()() as session:
            job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                completed_tasks=25,
                failed_tasks=5,
                metadata_={
                    "community_server_id": None,
                    "batch_size": 100,
                    "chunk_type": "fact_check",
                },
                error_summary=None,
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

            from src.batch_jobs.schemas import BatchJobResponse

            response = BatchJobResponse.model_validate(job)

            required_fields = [
                "id",
                "job_type",
                "status",
                "total_tasks",
                "completed_tasks",
                "failed_tasks",
                "metadata_",
                "error_summary",
                "started_at",
                "completed_at",
                "created_at",
                "updated_at",
                "progress_percentage",
            ]

            response_dict = response.model_dump()
            for field in required_fields:
                assert field in response_dict, f"Missing required field: {field}"

            assert response.progress_percentage == 25.0
            assert response.status == BatchJobStatus.IN_PROGRESS.value

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    async def test_job_metadata_preserved(self) -> None:
        """
        Test that job metadata is correctly stored and retrieved.

        This is important for job resume functionality.
        """
        test_metadata = {
            "community_server_id": str(uuid4()),
            "batch_size": 50,
            "chunk_type": "fact_check",
            "custom_field": "test_value",
        }

        async with get_session_maker()() as session:
            job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.PENDING.value,
                total_tasks=100,
                metadata_=test_metadata,
                created_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            retrieved_job = await batch_job_service.get_job(job_id)

            assert retrieved_job is not None
            assert retrieved_job.metadata_ == test_metadata
            assert retrieved_job.metadata_.get("custom_field") == "test_value"

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()


@pytest.mark.integration
class TestConcurrentJobExecution:
    """Tests for concurrent job handling (SC-008)."""

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_concurrent_job_creation_blocked(self, mock_task: AsyncMock) -> None:
        """
        Test that only one job of each type can be active at a time.

        SC-008: System handles concurrent requests by blocking duplicates.
        """
        mock_task.kiq = AsyncMock()

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            job = await service.start_fact_check_rechunk_job(
                community_server_id=None,
                batch_size=100,
            )
            job_id = job.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            with pytest.raises(ActiveJobExistsError) as exc_info:
                await service.start_fact_check_rechunk_job(
                    community_server_id=None,
                    batch_size=100,
                )

            assert exc_info.value.active_job_id == job_id

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_different_job_types_can_run_concurrently(self, mock_fc_task: AsyncMock) -> None:
        """
        Test that different job types can run concurrently.

        fact_check and previously_seen jobs should be able to run in parallel.
        """
        mock_fc_task.kiq = AsyncMock()

        async with get_session_maker()() as session:
            fc_job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                metadata_={"community_server_id": None, "chunk_type": "fact_check"},
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
            )
            session.add(fc_job)
            await session.commit()
            fc_job_id = fc_job.id

            ps_job = BatchJob(
                job_type=RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=50,
                metadata_={"community_server_id": str(uuid4()), "chunk_type": "previously_seen"},
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
            )
            session.add(ps_job)
            await session.commit()
            ps_job_id = ps_job.id

            result = await session.execute(
                select(BatchJob).where(
                    BatchJob.status == BatchJobStatus.IN_PROGRESS.value,
                    BatchJob.job_type.in_(
                        [RECHUNK_FACT_CHECK_JOB_TYPE, RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE]
                    ),
                )
            )
            active_jobs = list(result.scalars().all())
            assert len(active_jobs) == 2

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(
                delete(BatchJob).where(BatchJob.id.in_([fc_job_id, ps_job_id]))
            )
            await cleanup_session.commit()

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_completed_job_allows_new_job(self, mock_task: AsyncMock) -> None:
        """
        Test that completing a job allows a new job of the same type to start.
        """
        mock_task.kiq = AsyncMock()

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            job1 = await service.start_fact_check_rechunk_job(
                community_server_id=None,
                batch_size=100,
            )
            job1_id = job1.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            await batch_job_service.complete_job(job1_id, completed_tasks=100, failed_tasks=0)

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)
            service = RechunkBatchJobService(
                session=session,
                batch_job_service=batch_job_service,
            )

            job2 = await service.start_fact_check_rechunk_job(
                community_server_id=None,
                batch_size=100,
            )
            job2_id = job2.id

            assert job2.status == BatchJobStatus.IN_PROGRESS.value

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(
                delete(BatchJob).where(BatchJob.id.in_([job1_id, job2_id]))
            )
            await cleanup_session.commit()


@pytest.mark.integration
class TestBatchJobProgressTracking:
    """Tests for progress tracking accuracy (T032)."""

    @pytest.mark.asyncio
    async def test_progress_increments_correctly(self) -> None:
        """
        Test that progress updates are tracked correctly.
        """
        async with get_session_maker()() as session:
            job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                completed_tasks=0,
                failed_tasks=0,
                metadata_={"community_server_id": None},
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        async with get_session_maker()() as session:
            batch_job_service = BatchJobService(session)

            updated_job = await batch_job_service.update_progress(
                job_id=job_id,
                completed_tasks=25,
                failed_tasks=2,
            )

            assert updated_job is not None
            assert updated_job.completed_tasks == 25
            assert updated_job.failed_tasks == 2

            updated_job = await batch_job_service.update_progress(
                job_id=job_id,
                completed_tasks=50,
                failed_tasks=5,
            )

            assert updated_job is not None
            assert updated_job.completed_tasks == 50
            assert updated_job.failed_tasks == 5

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    async def test_progress_percentage_calculation(self) -> None:
        """
        Test that progress percentage is calculated correctly.
        """
        async with get_session_maker()() as session:
            job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=200,
                completed_tasks=50,
                failed_tasks=0,
                metadata_={"community_server_id": None},
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

            from src.batch_jobs.schemas import BatchJobResponse

            response = BatchJobResponse.model_validate(job)

            assert response.progress_percentage == 25.0

            job.completed_tasks = 150
            await session.commit()
            await session.refresh(job)

            response = BatchJobResponse.model_validate(job)
            assert response.progress_percentage == 75.0

            job_id = job.id

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()

    @pytest.mark.asyncio
    async def test_zero_total_tasks_progress(self) -> None:
        """
        Test that progress percentage handles zero total tasks gracefully.
        """
        async with get_session_maker()() as session:
            job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.PENDING.value,
                total_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
                metadata_={"community_server_id": None},
                created_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

            from src.batch_jobs.schemas import BatchJobResponse

            response = BatchJobResponse.model_validate(job)

            assert response.progress_percentage == 0.0

            job_id = job.id

        async with get_session_maker()() as cleanup_session:
            await cleanup_session.execute(delete(BatchJob).where(BatchJob.id == job_id))
            await cleanup_session.commit()
