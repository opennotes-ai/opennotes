"""
Integration tests for RechunkBatchJobService concurrency control.

Tests verify that SELECT FOR UPDATE prevents TOCTOU race conditions
when concurrent requests attempt to create jobs while one is active.

Task: task-1010.10 - Fix TOCTOU race in _check_no_active_job
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.batch_jobs.constants import RECHUNK_FACT_CHECK_JOB_TYPE
from src.batch_jobs.models import BatchJob
from src.batch_jobs.rechunk_service import ActiveJobExistsError, RechunkBatchJobService
from src.batch_jobs.schemas import BatchJobStatus
from src.batch_jobs.service import BatchJobService


@pytest.mark.integration
class TestRechunkServiceConcurrencyControl:
    """Tests for concurrent job creation being blocked by SELECT FOR UPDATE."""

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.process_fact_check_rechunk_task")
    async def test_concurrent_job_creation_with_existing_active_job_blocked(
        self,
        mock_task: AsyncMock,
    ) -> None:
        """
        Test that concurrent requests to create jobs all fail when an active job exists.

        When an active job exists, the SELECT FOR UPDATE acquires a row-level lock,
        serializing concurrent checks. All concurrent requests should fail with
        ActiveJobExistsError.
        """
        from src.database import get_session_maker

        mock_task.kiq = AsyncMock()
        concurrent_requests = 5

        async with get_session_maker()() as setup_session:
            active_job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.IN_PROGRESS.value,
                total_tasks=100,
                metadata_={
                    "community_server_id": None,
                    "batch_size": 100,
                    "chunk_type": "fact_check",
                },
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
            )
            setup_session.add(active_job)
            await setup_session.commit()
            active_job_id = active_job.id

        async def attempt_create_job(
            request_num: int,
        ) -> tuple[int, Exception | None]:
            """Attempt to create a job and return result."""
            async with get_session_maker()() as session:
                batch_job_service = BatchJobService(session)
                service = RechunkBatchJobService(
                    session=session,
                    batch_job_service=batch_job_service,
                )
                try:
                    await service.start_fact_check_rechunk_job(
                        community_server_id=None,
                        batch_size=100,
                    )
                    await session.commit()
                    return (request_num, None)
                except ActiveJobExistsError as e:
                    return (request_num, e)

        tasks = [attempt_create_job(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if isinstance(r, tuple) and r[1] is None]
        failures = [
            r for r in results if isinstance(r, tuple) and isinstance(r[1], ActiveJobExistsError)
        ]
        exceptions = [r for r in results if not isinstance(r, tuple)]

        assert len(exceptions) == 0, f"Unexpected exceptions: {exceptions}"
        assert len(successes) == 0, (
            f"Expected all requests to fail when active job exists, "
            f"but {len(successes)} succeeded. SELECT FOR UPDATE may not be working."
        )
        assert len(failures) == concurrent_requests, (
            f"Expected all {concurrent_requests} requests to fail with ActiveJobExistsError, "
            f"but got {len(failures)} failures."
        )

        for _, error in failures:
            assert error.active_job_id == active_job_id

        async with get_session_maker()() as cleanup_session:
            stmt = select(BatchJob).where(BatchJob.job_type == RECHUNK_FACT_CHECK_JOB_TYPE)
            result = await cleanup_session.execute(stmt)
            all_jobs = result.scalars().all()
            assert len(all_jobs) == 1, (
                f"Expected only the original active job, but found {len(all_jobs)} jobs. "
                "Concurrent job creation may have bypassed the check."
            )

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.process_fact_check_rechunk_task")
    async def test_concurrent_job_creation_with_pending_job_blocked(
        self,
        mock_task: AsyncMock,
    ) -> None:
        """
        Test that concurrent requests are blocked when a PENDING job exists.

        Both PENDING and IN_PROGRESS statuses should block new job creation.
        """
        from src.database import get_session_maker

        mock_task.kiq = AsyncMock()
        concurrent_requests = 3

        async with get_session_maker()() as setup_session:
            pending_job = BatchJob(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                status=BatchJobStatus.PENDING.value,
                total_tasks=50,
                metadata_={
                    "community_server_id": None,
                    "batch_size": 50,
                    "chunk_type": "fact_check",
                },
                created_at=datetime.now(UTC),
            )
            setup_session.add(pending_job)
            await setup_session.commit()
            pending_job_id = pending_job.id

        async def attempt_create_job(
            request_num: int,
        ) -> tuple[int, Exception | None]:
            """Attempt to create a job and return result."""
            async with get_session_maker()() as session:
                batch_job_service = BatchJobService(session)
                service = RechunkBatchJobService(
                    session=session,
                    batch_job_service=batch_job_service,
                )
                try:
                    await service.start_fact_check_rechunk_job(
                        community_server_id=None,
                        batch_size=100,
                    )
                    await session.commit()
                    return (request_num, None)
                except ActiveJobExistsError as e:
                    return (request_num, e)

        tasks = [attempt_create_job(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if isinstance(r, tuple) and r[1] is None]
        failures = [
            r for r in results if isinstance(r, tuple) and isinstance(r[1], ActiveJobExistsError)
        ]

        assert len(successes) == 0, (
            f"Expected all requests to fail with PENDING job, but {len(successes)} succeeded."
        )
        assert len(failures) == concurrent_requests

        for _, error in failures:
            assert error.active_job_id == pending_job_id
