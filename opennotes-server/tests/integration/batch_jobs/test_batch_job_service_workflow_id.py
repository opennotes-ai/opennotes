"""
Integration tests for BatchJobService.set_workflow_id method.

Task: task-1058.01 - Fix workflow_id shows N/A due to SQLAlchemy identity map cache

This test verifies that set_workflow_id properly refreshes the job object
after updating the workflow_id, ensuring that the returned object and any
references to it reflect the updated value.

Root cause: SQLAlchemy session identity map cache returns stale object
without workflow_id:
1. dispatch_dbos_rechunk_workflow creates BatchJob, commits (workflow_id=None)
2. DBOS workflow enqueued, workflow_id obtained
3. set_workflow_id updates DB and commits
4. Service re-fetches job using same session -> cached object with workflow_id=None

Fix: Add await self._session.refresh(job) in set_workflow_id after the flush.
"""

import pytest
from sqlalchemy import select

from src.batch_jobs.constants import RECHUNK_FACT_CHECK_JOB_TYPE
from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.database import get_session_maker


@pytest.mark.integration
class TestBatchJobServiceSetWorkflowId:
    """Tests for BatchJobService.set_workflow_id method."""

    @pytest.mark.asyncio
    async def test_set_workflow_id_returns_updated_job_object(self) -> None:
        """
        Test that set_workflow_id returns a job object with the updated workflow_id.

        This test reproduces the SQLAlchemy identity map cache issue where:
        1. A BatchJob is created (workflow_id=None)
        2. set_workflow_id is called to update the workflow_id
        3. The returned job object should have the updated workflow_id

        Without the fix (refresh after flush), the returned job object would
        have workflow_id=None due to identity map caching.
        """
        async with get_session_maker()() as session:
            service = BatchJobService(session)

            job = await service.create_job(
                BatchJobCreate(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    total_tasks=10,
                    metadata={"test": "data"},
                )
            )
            await session.commit()

            assert job.workflow_id is None

            expected_workflow_id = "test-workflow-12345"
            updated_job = await service.set_workflow_id(job.id, expected_workflow_id)
            await session.commit()

            assert updated_job is not None
            assert updated_job.workflow_id == expected_workflow_id, (
                f"Expected workflow_id to be '{expected_workflow_id}', "
                f"got '{updated_job.workflow_id}'. "
                "This indicates the identity map cache returned a stale object."
            )

    @pytest.mark.asyncio
    async def test_set_workflow_id_persists_to_database(self) -> None:
        """
        Test that set_workflow_id persists the workflow_id to the database.

        After the service call completes and we read with a fresh session,
        the workflow_id should be present in the database.
        """
        job_id = None
        expected_workflow_id = "persisted-workflow-67890"

        async with get_session_maker()() as session:
            service = BatchJobService(session)

            job = await service.create_job(
                BatchJobCreate(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    total_tasks=10,
                    metadata={"test": "persistence"},
                )
            )
            await session.commit()
            job_id = job.id

            await service.set_workflow_id(job.id, expected_workflow_id)
            await session.commit()

        async with get_session_maker()() as verify_session:
            result = await verify_session.execute(select(BatchJob).where(BatchJob.id == job_id))
            db_job = result.scalar_one_or_none()

            assert db_job is not None
            assert db_job.workflow_id == expected_workflow_id, (
                f"Expected workflow_id in database to be '{expected_workflow_id}', "
                f"got '{db_job.workflow_id}'."
            )

    @pytest.mark.asyncio
    async def test_set_workflow_id_updates_original_reference(self) -> None:
        """
        Test that set_workflow_id updates the original job reference via identity map.

        When set_workflow_id calls refresh(), the original job variable should
        also reflect the updated workflow_id because SQLAlchemy identity map
        ensures there is only one instance of each object in the session.

        This simulates the dispatch_dbos_rechunk_workflow pattern where:
        1. job = service.create_job(...)
        2. set_workflow_id(job.id, workflow_id) is called
        3. Code may later access job.workflow_id expecting the updated value
        """
        async with get_session_maker()() as session:
            service = BatchJobService(session)

            original_job = await service.create_job(
                BatchJobCreate(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    total_tasks=10,
                    metadata={"test": "original_reference"},
                )
            )
            await session.commit()

            assert original_job.workflow_id is None

            expected_workflow_id = "original-ref-workflow-11111"
            await service.set_workflow_id(original_job.id, expected_workflow_id)
            await session.commit()

            assert original_job.workflow_id == expected_workflow_id, (
                f"Expected original_job.workflow_id to be '{expected_workflow_id}', "
                f"got '{original_job.workflow_id}'. "
                "This indicates the identity map was not properly refreshed."
            )

    @pytest.mark.asyncio
    async def test_workflow_id_accessible_after_refetch_post_commit(self) -> None:
        """
        Test that workflow_id is accessible after a fresh fetch post-commit.

        This tests the specific scenario in dispatch_dbos_rechunk_workflow where:
        1. Job is created and started
        2. set_workflow_id is called
        3. Commit happens
        4. A fresh get_job is called

        After commit, SQLAlchemy expires all objects. If we re-fetch, we should
        see the workflow_id. This tests that the DB was properly updated.
        """
        async with get_session_maker()() as session:
            service = BatchJobService(session)

            job = await service.create_job(
                BatchJobCreate(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    total_tasks=10,
                    metadata={"test": "refetch"},
                )
            )
            await session.commit()
            job_id = job.id

            expected_workflow_id = "refetch-workflow-22222"
            await service.set_workflow_id(job_id, expected_workflow_id)
            await session.commit()

            refetched_job = await service.get_job(job_id)
            assert refetched_job is not None
            assert refetched_job.workflow_id == expected_workflow_id, (
                f"Expected workflow_id after refetch to be '{expected_workflow_id}', "
                f"got '{refetched_job.workflow_id}'. "
                "This indicates the workflow_id was not properly persisted."
            )

    @pytest.mark.asyncio
    async def test_workflow_id_expired_object_access(self) -> None:
        """
        Test that workflow_id is accessible even when object attributes are expired.

        SQLAlchemy's expire_on_commit=True (default in our async_sessionmaker)
        expires all attributes after commit. When accessing an expired attribute,
        SQLAlchemy issues a lazy load. This test verifies the workflow_id
        survives this pattern.

        This is the ACTUAL issue: After set_workflow_id commits, the original
        job object has expired attributes. If we access job.workflow_id, it
        should lazy-load the updated value from the database.
        """
        async with get_session_maker()() as session:
            service = BatchJobService(session)

            job = await service.create_job(
                BatchJobCreate(
                    job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                    total_tasks=10,
                    metadata={"test": "expired"},
                )
            )
            await session.commit()

            expected_workflow_id = "expired-workflow-33333"
            await service.set_workflow_id(job.id, expected_workflow_id)
            await session.commit()

            assert job.workflow_id == expected_workflow_id, (
                f"Expected job.workflow_id to be '{expected_workflow_id}' after commit, "
                f"got '{job.workflow_id}'. "
                "This indicates lazy loading returned stale data."
            )
