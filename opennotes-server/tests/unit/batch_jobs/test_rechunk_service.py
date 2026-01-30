"""
Unit tests for RechunkBatchJobService.

Tests rechunk job creation and cancellation, with focus on null community_server_id
handling to ensure task-896 and task-898 regressions are prevented.

Note: Rate limiting for concurrent jobs is now handled by DistributedRateLimitMiddleware,
not by the service layer. Lock management tests have been moved to middleware tests.

Task: task-986.10 - Restore deleted test coverage
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs.constants import (
    PROMOTION_JOB_TYPE,
    RECHUNK_FACT_CHECK_JOB_TYPE,
    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
    SCRAPE_JOB_TYPE,
)
from src.batch_jobs.models import BatchJob
from src.batch_jobs.rechunk_service import (
    RechunkBatchJobService,
    RechunkType,
    enqueue_single_fact_check_chunk,
    get_stuck_jobs_info,
)


def _make_execute_side_effect(active_job=None, count_result=100):
    """Create a side effect function for session.execute that handles different queries.

    Args:
        active_job: Value to return for scalar_one_or_none() (active job check)
        count_result: Value to return for scalar_one() (count queries)
    """

    async def side_effect(query):
        result = MagicMock()
        result.scalar_one_or_none.return_value = active_job
        result.scalar_one.return_value = count_result
        return result

    return side_effect


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy async session."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=_make_execute_side_effect(active_job=None))
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
    service.cancel_job = AsyncMock()
    service.get_job = AsyncMock()
    service.fail_job = AsyncMock()
    return service


@pytest.fixture
def rechunk_service(mock_session, mock_batch_job_service):
    """Create a RechunkBatchJobService with mocked dependencies."""
    return RechunkBatchJobService(
        session=mock_session,
        batch_job_service=mock_batch_job_service,
    )


@pytest.mark.unit
class TestRechunkServiceNullCommunityServerId:
    """Tests for null community_server_id handling (task-896 regression)."""

    @pytest.mark.asyncio
    @patch("src.dbos_workflows.rechunk_workflow.dispatch_dbos_rechunk_workflow")
    async def test_start_fact_check_rechunk_job_with_null_community_server_id(
        self,
        mock_dispatch,
        rechunk_service,
        mock_batch_job_service,
        mock_session,
    ):
        """Start fact check rechunk with null community_server_id passes None to DBOS dispatch."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_dispatch.return_value = job_id
        mock_batch_job_service.get_job.return_value = mock_job

        result = await rechunk_service.start_fact_check_rechunk_job(
            community_server_id=None,
            batch_size=50,
        )

        assert result == mock_job
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["community_server_id"] is None
        assert call_kwargs["batch_size"] == 50

    @pytest.mark.asyncio
    async def test_cancel_rechunk_job_with_null_community_server_id(
        self,
        rechunk_service,
        mock_batch_job_service,
    ):
        """Cancel rechunk job with null community_server_id works correctly."""
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
        mock_batch_job_service.cancel_job.assert_called_once_with(job_id)


@pytest.mark.unit
class TestRechunkServiceMetadataSerialization:
    """Tests for metadata serialization (task-898 regression)."""

    @pytest.mark.asyncio
    @patch("src.dbos_workflows.rechunk_workflow.dispatch_dbos_rechunk_workflow")
    async def test_dispatch_receives_null_community_server_id(
        self,
        mock_dispatch,
        rechunk_service,
        mock_batch_job_service,
        mock_session,
    ):
        """DBOS dispatch receives None community_server_id, not string 'None'."""
        job_id = uuid4()
        mock_job = MagicMock(spec=BatchJob)
        mock_job.id = job_id
        mock_dispatch.return_value = job_id
        mock_batch_job_service.get_job.return_value = mock_job

        await rechunk_service.start_fact_check_rechunk_job(
            community_server_id=None,
            batch_size=100,
        )

        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["community_server_id"] is None
        assert call_kwargs["community_server_id"] != "None"

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

        result = await rechunk_service.start_previously_seen_rechunk_job(
            community_server_id=community_server_id,
            batch_size=100,
        )

        assert result == mock_job
        create_call = mock_batch_job_service.create_job.call_args
        job_create = create_call[0][0]

        assert job_create.job_type == RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE
        assert job_create.metadata_["community_server_id"] == str(community_server_id)
        assert job_create.metadata_["chunk_type"] == RechunkType.PREVIOUSLY_SEEN.value

    @pytest.mark.asyncio
    async def test_cancel_previously_seen_job_works_correctly(
        self,
        rechunk_service,
        mock_batch_job_service,
    ):
        """Cancel previously_seen job works correctly."""
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
        mock_batch_job_service.cancel_job.assert_called_once_with(job_id)


@pytest.mark.unit
class TestRechunkServiceTaskDispatchFailure:
    """Tests for task dispatch failure scenarios."""

    @pytest.mark.asyncio
    @patch("src.dbos_workflows.rechunk_workflow.dispatch_dbos_rechunk_workflow")
    async def test_dispatch_failure_raises_exception(
        self,
        mock_dispatch,
        rechunk_service,
        mock_batch_job_service,
        mock_session,
    ):
        """DBOS dispatch failure raises exception."""
        mock_dispatch.side_effect = Exception("DBOS dispatch error")

        with pytest.raises(Exception, match="DBOS dispatch error"):
            await rechunk_service.start_fact_check_rechunk_job(
                community_server_id=None,
            )

    @pytest.mark.asyncio
    async def test_cancel_job_not_found_returns_none(
        self,
        rechunk_service,
        mock_batch_job_service,
    ):
        """Cancel returns None when job not found."""
        mock_batch_job_service.get_job.return_value = None

        result = await rechunk_service.cancel_rechunk_job(uuid4())

        assert result is None


@pytest.mark.unit
class TestRechunkServiceEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_cancel_job_with_empty_metadata(
        self,
        rechunk_service,
        mock_batch_job_service,
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

    @pytest.mark.asyncio
    async def test_cancel_job_with_none_metadata(
        self,
        rechunk_service,
        mock_batch_job_service,
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


@pytest.mark.unit
class TestRechunkServiceActiveJobCheck:
    """Tests for active job check before creating new jobs (task-1010.04)."""

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_fact_check_rechunk_task")
    async def test_active_job_blocks_new_fact_check_job(
        self,
        mock_task,
        mock_batch_job_service,
    ):
        """Creating a fact check job fails when one is already active."""
        from src.batch_jobs.rechunk_service import ActiveJobExistsError

        existing_job_id = uuid4()
        existing_job = MagicMock(spec=BatchJob)
        existing_job.id = existing_job_id
        existing_job.status = "in_progress"

        session = MagicMock()
        session.execute = AsyncMock(side_effect=_make_execute_side_effect(active_job=existing_job))
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        with pytest.raises(ActiveJobExistsError) as exc_info:
            await service.start_fact_check_rechunk_job(
                community_server_id=None,
            )

        assert exc_info.value.active_job_id == existing_job_id
        mock_batch_job_service.create_job.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.tasks.rechunk_tasks.process_previously_seen_rechunk_task")
    async def test_active_job_blocks_new_previously_seen_job(
        self,
        mock_task,
        mock_batch_job_service,
    ):
        """Creating a previously seen job fails when one is already active."""
        from src.batch_jobs.rechunk_service import ActiveJobExistsError

        existing_job_id = uuid4()
        existing_job = MagicMock(spec=BatchJob)
        existing_job.id = existing_job_id
        existing_job.status = "pending"

        session = MagicMock()
        session.execute = AsyncMock(side_effect=_make_execute_side_effect(active_job=existing_job))
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        with pytest.raises(ActiveJobExistsError) as exc_info:
            await service.start_previously_seen_rechunk_job(
                community_server_id=uuid4(),
            )

        assert exc_info.value.active_job_id == existing_job_id
        mock_batch_job_service.create_job.assert_not_called()


@pytest.mark.unit
class TestRechunkServiceStaleJobCleanup:
    """Tests for stale job cleanup (task-1010.04)."""

    @pytest.mark.asyncio
    async def test_cleanup_stale_jobs_marks_old_jobs_as_failed(
        self,
        mock_batch_job_service,
    ):
        """Cleanup marks stale jobs as failed."""
        from datetime import UTC, datetime, timedelta

        stale_job_id = uuid4()
        stale_job = MagicMock(spec=BatchJob)
        stale_job.id = stale_job_id
        stale_job.status = "in_progress"
        stale_job.created_at = datetime.now(UTC) - timedelta(hours=3)

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stale_job]
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        mock_batch_job_service.fail_job = AsyncMock(return_value=stale_job)

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        result = await service.cleanup_stale_jobs(stale_threshold_hours=2)

        assert len(result) == 1
        assert result[0].id == stale_job_id
        mock_batch_job_service.fail_job.assert_called_once()
        call_args = mock_batch_job_service.fail_job.call_args
        assert call_args[0][0] == stale_job_id
        assert "stale" in call_args[1]["error_summary"]["error"].lower()

    @pytest.mark.asyncio
    async def test_cleanup_stale_jobs_no_stale_jobs(
        self,
        mock_batch_job_service,
    ):
        """Cleanup does nothing when no stale jobs exist."""
        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        result = await service.cleanup_stale_jobs()

        assert len(result) == 0
        mock_batch_job_service.fail_job.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_stale_jobs_marks_stale_scrape_job_as_failed(
        self,
        mock_batch_job_service,
    ):
        """Cleanup marks stale scrape jobs as failed (task-1010.11)."""
        from datetime import UTC, datetime, timedelta

        stale_job_id = uuid4()
        stale_job = MagicMock(spec=BatchJob)
        stale_job.id = stale_job_id
        stale_job.job_type = SCRAPE_JOB_TYPE
        stale_job.status = "in_progress"
        stale_job.created_at = datetime.now(UTC) - timedelta(hours=3)

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stale_job]
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        mock_batch_job_service.fail_job = AsyncMock(return_value=stale_job)

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        result = await service.cleanup_stale_jobs(stale_threshold_hours=2)

        assert len(result) == 1
        assert result[0].id == stale_job_id
        mock_batch_job_service.fail_job.assert_called_once()
        call_args = mock_batch_job_service.fail_job.call_args
        assert call_args[0][0] == stale_job_id
        assert "stale" in call_args[1]["error_summary"]["error"].lower()

    @pytest.mark.asyncio
    async def test_cleanup_stale_jobs_marks_stale_promotion_job_as_failed(
        self,
        mock_batch_job_service,
    ):
        """Cleanup marks stale promotion jobs as failed (task-1010.11)."""
        from datetime import UTC, datetime, timedelta

        stale_job_id = uuid4()
        stale_job = MagicMock(spec=BatchJob)
        stale_job.id = stale_job_id
        stale_job.job_type = PROMOTION_JOB_TYPE
        stale_job.status = "pending"
        stale_job.created_at = datetime.now(UTC) - timedelta(hours=5)

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stale_job]
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        mock_batch_job_service.fail_job = AsyncMock(return_value=stale_job)

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        result = await service.cleanup_stale_jobs(stale_threshold_hours=2)

        assert len(result) == 1
        assert result[0].id == stale_job_id
        mock_batch_job_service.fail_job.assert_called_once()
        call_args = mock_batch_job_service.fail_job.call_args
        assert call_args[0][0] == stale_job_id
        assert "stale" in call_args[1]["error_summary"]["error"].lower()

    @pytest.mark.asyncio
    async def test_cleanup_stale_jobs_handles_all_job_types(
        self,
        mock_batch_job_service,
    ):
        """Cleanup processes stale jobs of all supported types (task-1010.11)."""
        from datetime import UTC, datetime, timedelta

        stale_jobs = []
        for job_type in [
            RECHUNK_FACT_CHECK_JOB_TYPE,
            RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
            SCRAPE_JOB_TYPE,
            PROMOTION_JOB_TYPE,
        ]:
            job = MagicMock(spec=BatchJob)
            job.id = uuid4()
            job.job_type = job_type
            job.status = "in_progress"
            job.created_at = datetime.now(UTC) - timedelta(hours=3)
            stale_jobs.append(job)

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = stale_jobs
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        mock_batch_job_service.fail_job = AsyncMock(
            side_effect=lambda job_id, **kwargs: next(
                (j for j in stale_jobs if j.id == job_id), None
            )
        )

        service = RechunkBatchJobService(
            session=session,
            batch_job_service=mock_batch_job_service,
        )

        result = await service.cleanup_stale_jobs(stale_threshold_hours=2)

        assert len(result) == 4
        assert mock_batch_job_service.fail_job.call_count == 4


@pytest.mark.unit
class TestGetStuckJobsInfo:
    """Tests for get_stuck_jobs_info standalone function (task-1043)."""

    @pytest.mark.asyncio
    async def test_get_stuck_jobs_info_returns_stuck_jobs(self):
        """get_stuck_jobs_info returns jobs stuck with zero progress."""
        from datetime import UTC, datetime, timedelta

        stuck_job_id = uuid4()
        stuck_job = MagicMock(spec=BatchJob)
        stuck_job.id = stuck_job_id
        stuck_job.job_type = RECHUNK_FACT_CHECK_JOB_TYPE
        stuck_job.status = "in_progress"
        stuck_job.updated_at = datetime.now(UTC) - timedelta(minutes=40)
        stuck_job.created_at = datetime.now(UTC) - timedelta(hours=1)

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stuck_job]
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_stuck_jobs_info(session)

        assert len(result) == 1
        assert result[0].job_id == stuck_job_id
        assert result[0].job_type == RECHUNK_FACT_CHECK_JOB_TYPE
        assert result[0].status == "in_progress"
        assert result[0].stuck_duration_seconds > 0

    @pytest.mark.asyncio
    async def test_get_stuck_jobs_info_returns_empty_when_no_stuck_jobs(self):
        """get_stuck_jobs_info returns empty list when no jobs are stuck."""
        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_stuck_jobs_info(session)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_stuck_jobs_info_respects_custom_threshold(self):
        """get_stuck_jobs_info respects custom threshold_minutes parameter."""

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        await get_stuck_jobs_info(session, threshold_minutes=60)

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stuck_jobs_info_handles_multiple_job_types(self):
        """get_stuck_jobs_info handles all supported batch job types."""
        from datetime import UTC, datetime, timedelta

        stuck_jobs = []
        for i, job_type in enumerate(
            [
                RECHUNK_FACT_CHECK_JOB_TYPE,
                RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
                SCRAPE_JOB_TYPE,
                PROMOTION_JOB_TYPE,
            ]
        ):
            job = MagicMock(spec=BatchJob)
            job.id = uuid4()
            job.job_type = job_type
            job.status = "in_progress"
            job.updated_at = datetime.now(UTC) - timedelta(minutes=40 + i * 10)
            job.created_at = datetime.now(UTC) - timedelta(hours=1 + i)
            stuck_jobs.append(job)

        session = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = stuck_jobs
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_stuck_jobs_info(session)

        assert len(result) == 4
        job_types = {info.job_type for info in result}
        assert RECHUNK_FACT_CHECK_JOB_TYPE in job_types
        assert RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE in job_types
        assert SCRAPE_JOB_TYPE in job_types
        assert PROMOTION_JOB_TYPE in job_types


@pytest.mark.unit
class TestEnqueueSingleFactCheckChunk:
    """Tests for enqueue_single_fact_check_chunk routing function (task-1056.01)."""

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.USE_DBOS_RECHUNK", False)
    @patch("src.dbos_workflows.rechunk_workflow.enqueue_single_fact_check_chunk")
    async def test_always_routes_to_dbos_regardless_of_flag(self, mock_dbos_enqueue):
        """Always routes to DBOS regardless of USE_DBOS_RECHUNK flag (TaskIQ removed)."""
        fact_check_id = uuid4()
        community_server_id = uuid4()
        mock_dbos_enqueue.return_value = "test-workflow-id"

        result = await enqueue_single_fact_check_chunk(
            fact_check_id=fact_check_id,
            community_server_id=community_server_id,
        )

        assert result is True
        mock_dbos_enqueue.assert_called_once_with(
            fact_check_id=fact_check_id,
            community_server_id=community_server_id,
        )

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.USE_DBOS_RECHUNK", True)
    @patch("src.dbos_workflows.rechunk_workflow.enqueue_single_fact_check_chunk")
    async def test_routes_to_dbos_when_flag_enabled(self, mock_dbos_enqueue):
        """Routes to DBOS when USE_DBOS_RECHUNK is True."""
        fact_check_id = uuid4()
        community_server_id = uuid4()
        mock_dbos_enqueue.return_value = "test-workflow-id"

        result = await enqueue_single_fact_check_chunk(
            fact_check_id=fact_check_id,
            community_server_id=community_server_id,
        )

        assert result is True
        mock_dbos_enqueue.assert_called_once_with(
            fact_check_id=fact_check_id,
            community_server_id=community_server_id,
        )

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.USE_DBOS_RECHUNK", False)
    @patch("src.dbos_workflows.rechunk_workflow.enqueue_single_fact_check_chunk")
    async def test_explicit_use_dbos_true_overrides_flag(self, mock_dbos_enqueue):
        """Explicit use_dbos=True overrides USE_DBOS_RECHUNK flag."""
        fact_check_id = uuid4()
        mock_dbos_enqueue.return_value = "test-workflow-id"

        result = await enqueue_single_fact_check_chunk(
            fact_check_id=fact_check_id,
            use_dbos=True,
        )

        assert result is True
        mock_dbos_enqueue.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.USE_DBOS_RECHUNK", True)
    @patch("src.dbos_workflows.rechunk_workflow.enqueue_single_fact_check_chunk")
    async def test_explicit_use_dbos_false_logs_warning_but_uses_dbos(
        self, mock_dbos_enqueue, caplog
    ):
        """Explicit use_dbos=False logs deprecation warning but still uses DBOS."""
        import logging

        fact_check_id = uuid4()
        mock_dbos_enqueue.return_value = "test-workflow-id"

        with caplog.at_level(logging.WARNING):
            result = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                use_dbos=False,
            )

        assert result is True
        mock_dbos_enqueue.assert_called_once()
        assert "deprecated" in caplog.text.lower()

    @pytest.mark.asyncio
    @patch("src.batch_jobs.rechunk_service.USE_DBOS_RECHUNK", True)
    @patch("src.dbos_workflows.rechunk_workflow.enqueue_single_fact_check_chunk")
    async def test_returns_false_on_dbos_failure(self, mock_dbos_enqueue):
        """Returns False when DBOS enqueue returns None."""
        fact_check_id = uuid4()
        mock_dbos_enqueue.return_value = None

        result = await enqueue_single_fact_check_chunk(
            fact_check_id=fact_check_id,
        )

        assert result is False

    @pytest.mark.asyncio
    @patch("src.dbos_workflows.rechunk_workflow.enqueue_single_fact_check_chunk")
    async def test_handles_null_community_server_id(self, mock_dbos_enqueue):
        """Handles null community_server_id correctly."""
        fact_check_id = uuid4()
        mock_dbos_enqueue.return_value = "test-workflow-id"

        result = await enqueue_single_fact_check_chunk(
            fact_check_id=fact_check_id,
            community_server_id=None,
        )

        assert result is True
        mock_dbos_enqueue.assert_called_once_with(
            fact_check_id=fact_check_id,
            community_server_id=None,
        )
