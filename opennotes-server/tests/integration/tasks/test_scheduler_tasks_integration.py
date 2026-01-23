"""
Integration tests for scheduler tasks.

Tests cleanup_stale_batch_jobs functionality with real service and database.
Task: task-1043.06 - Add integration test for cleanup with real service
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from src.batch_jobs.constants import RECHUNK_FACT_CHECK_JOB_TYPE
from src.batch_jobs.models import BatchJob
from src.batch_jobs.rechunk_service import RechunkBatchJobService
from src.batch_jobs.schemas import BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.database import get_session_maker


@pytest.mark.integration
class TestCleanupStaleBatchJobsIntegration:
    """Integration tests for cleanup_stale_jobs with real service and database."""

    @pytest.mark.asyncio
    async def test_cleanup_stale_jobs_with_real_service(self) -> None:
        """
        Integration test: cleanup_stale_jobs marks stale jobs as FAILED end-to-end.

        Uses real RechunkBatchJobService and database session to verify
        actual cleanup behavior rather than just mock interactions.
        """
        stale_job_id = None
        active_job_id = None

        try:
            async with get_session_maker()() as setup_session:
                stale_time = datetime.now(UTC) - timedelta(hours=3)
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
                    created_at=stale_time,
                    started_at=stale_time,
                    updated_at=stale_time,
                )
                setup_session.add(stale_job)
                await setup_session.commit()
                stale_job_id = stale_job.id

            async with get_session_maker()() as setup_session2:
                recent_time = datetime.now(UTC) - timedelta(minutes=30)
                active_job = BatchJob(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    status=BatchJobStatus.IN_PROGRESS.value,
                    total_tasks=100,
                    completed_tasks=10,
                    metadata_={
                        "community_server_id": None,
                        "batch_size": 100,
                        "chunk_type": "fact_check",
                    },
                    created_at=recent_time,
                    started_at=recent_time,
                    updated_at=recent_time,
                )
                setup_session2.add(active_job)
                await setup_session2.commit()
                active_job_id = active_job.id

            async with get_session_maker()() as test_session:
                batch_job_service = BatchJobService(test_session)
                service = RechunkBatchJobService(
                    session=test_session,
                    batch_job_service=batch_job_service,
                )

                failed_jobs = await service.cleanup_stale_jobs(stale_threshold_hours=2.0)

            assert len(failed_jobs) == 1
            assert failed_jobs[0].id == stale_job_id
            assert failed_jobs[0].status == BatchJobStatus.FAILED.value
            assert failed_jobs[0].error_summary is not None
            assert "stale" in failed_jobs[0].error_summary.get("error", "").lower()

            async with get_session_maker()() as verify_session:
                result = await verify_session.execute(
                    select(BatchJob).where(BatchJob.id == active_job_id)
                )
                active_job_after = result.scalar_one()
                assert active_job_after.status == BatchJobStatus.IN_PROGRESS.value

        finally:
            async with get_session_maker()() as cleanup_session:
                if stale_job_id:
                    await cleanup_session.execute(
                        delete(BatchJob).where(BatchJob.id == stale_job_id)
                    )
                if active_job_id:
                    await cleanup_session.execute(
                        delete(BatchJob).where(BatchJob.id == active_job_id)
                    )
                await cleanup_session.commit()

    @pytest.mark.asyncio
    async def test_cleanup_respects_updated_at_not_created_at(self) -> None:
        """
        Integration test: cleanup uses updated_at (not created_at) to determine staleness.

        A job created long ago but recently updated should NOT be cleaned up,
        while a job created recently but not updated recently SHOULD be cleaned up.
        """
        old_created_recently_updated_job_id = None
        recent_created_stale_updated_job_id = None

        try:
            async with get_session_maker()() as setup_session:
                old_time = datetime.now(UTC) - timedelta(hours=10)
                recent_time = datetime.now(UTC) - timedelta(minutes=30)
                old_created_recently_updated_job = BatchJob(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    status=BatchJobStatus.IN_PROGRESS.value,
                    total_tasks=100,
                    completed_tasks=50,
                    metadata_={
                        "community_server_id": None,
                        "batch_size": 100,
                        "chunk_type": "fact_check",
                    },
                    created_at=old_time,
                    started_at=old_time,
                    updated_at=recent_time,
                )
                setup_session.add(old_created_recently_updated_job)
                await setup_session.commit()
                old_created_recently_updated_job_id = old_created_recently_updated_job.id

            async with get_session_maker()() as setup_session2:
                recent_created_time = datetime.now(UTC) - timedelta(hours=1)
                stale_updated_time = datetime.now(UTC) - timedelta(hours=5)
                recent_created_stale_updated_job = BatchJob(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    status=BatchJobStatus.IN_PROGRESS.value,
                    total_tasks=100,
                    completed_tasks=10,
                    metadata_={
                        "community_server_id": None,
                        "batch_size": 100,
                        "chunk_type": "fact_check",
                    },
                    created_at=recent_created_time,
                    started_at=recent_created_time,
                    updated_at=stale_updated_time,
                )
                setup_session2.add(recent_created_stale_updated_job)
                await setup_session2.commit()
                recent_created_stale_updated_job_id = recent_created_stale_updated_job.id

            async with get_session_maker()() as test_session:
                batch_job_service = BatchJobService(test_session)
                service = RechunkBatchJobService(
                    session=test_session,
                    batch_job_service=batch_job_service,
                )

                failed_jobs = await service.cleanup_stale_jobs(stale_threshold_hours=2.0)

            assert len(failed_jobs) == 1
            assert failed_jobs[0].id == recent_created_stale_updated_job_id

            async with get_session_maker()() as verify_session:
                result = await verify_session.execute(
                    select(BatchJob).where(BatchJob.id == old_created_recently_updated_job_id)
                )
                old_job_after = result.scalar_one()
                assert old_job_after.status == BatchJobStatus.IN_PROGRESS.value

        finally:
            async with get_session_maker()() as cleanup_session:
                if old_created_recently_updated_job_id:
                    await cleanup_session.execute(
                        delete(BatchJob).where(BatchJob.id == old_created_recently_updated_job_id)
                    )
                if recent_created_stale_updated_job_id:
                    await cleanup_session.execute(
                        delete(BatchJob).where(BatchJob.id == recent_created_stale_updated_job_id)
                    )
                await cleanup_session.commit()
