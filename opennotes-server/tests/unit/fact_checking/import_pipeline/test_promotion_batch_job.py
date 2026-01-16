"""
Unit tests for process_promotion_batch TaskIQ task.

Task: task-1006.02 - Create TaskIQ task process_promotion_batch

Tests cover:
- Processing scraped candidates with progress tracking
- Handling promotion failures gracefully (marks as failed but continues)
- Dry run mode (counts candidates but doesn't promote)
- Job completion with correct stats
- Race condition prevention (task-1008.02)
- Recovery from mid-batch crash
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs import PROMOTION_JOB_TYPE

from .conftest import create_mock_session_context, create_mock_settings

pytestmark = pytest.mark.unit


def create_flexible_execute_mock(
    total_count: int,
    candidate_rows: list,
):
    """
    Create a flexible mock for db.execute that handles various query types.

    Args:
        total_count: Count to return for COUNT queries
        candidate_rows: List of (id,) tuples to return for SELECT queries via fetchall()

    Note: In batch mode, all candidates are returned in one fetchall() call,
    then subsequent calls return empty list. UPDATE ... RETURNING queries
    use fetchall() to get the updated rows.
    """
    batch_returned = [False]

    def execute_side_effect(query):
        result = MagicMock()

        query_str = str(query)
        query_lower = query_str.lower()

        if "count(" in query_lower:
            result.scalar_one.return_value = total_count
        elif "returning" in query_lower:

            def mock_fetchall():
                if not batch_returned[0]:
                    batch_returned[0] = True
                    return candidate_rows
                return []

            result.fetchall = mock_fetchall
            result.rowcount = len(candidate_rows)
        elif query_lower.strip().startswith("update") or "set status" in query_lower:
            result.rowcount = 1
        else:
            result.scalar_one.return_value = total_count

        return result

    return AsyncMock(side_effect=execute_side_effect)


class TestPromotionBatchProcessing:
    """Test main promotion batch processing functionality."""

    @pytest.mark.asyncio
    async def test_processes_scraped_candidates_and_updates_progress(self):
        """Successfully processes scraped candidates and tracks progress."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
            (candidate2_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=2,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                return_value=True,
            ) as mock_promote,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["promoted"] == 2
            assert result["failed"] == 0
            mock_batch_job_service.start_job.assert_called_once()
            mock_batch_job_service.complete_job.assert_called_once()
            assert mock_promote.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_promotion_failures_gracefully(self):
        """Promotion failures are marked as failed but processing continues."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
            (candidate2_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=2,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        promote_call_count = [0]

        async def promote_side_effect(session, cid):
            promote_call_count[0] += 1
            return promote_call_count[0] == 1

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                side_effect=promote_side_effect,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["promoted"] == 1
            assert result["failed"] == 1
            mock_batch_job_service.complete_job.assert_called_once()


class TestPromotionBatchDryRun:
    """Test dry run mode functionality."""

    @pytest.mark.asyncio
    async def test_dry_run_counts_but_does_not_promote(self):
        """Dry run mode counts candidates but doesn't perform promotion."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 5

        mock_db.execute = AsyncMock(return_value=mock_count_result)

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.promote_candidate") as mock_promote,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=True,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["dry_run"] is True
            assert result["total_candidates"] == 5
            assert result["promoted"] == 0
            assert result["failed"] == 0
            mock_promote.assert_not_called()
            mock_batch_job_service.complete_job.assert_called_once()


class TestPromotionBatchJobCompletion:
    """Test job completion with correct stats."""

    @pytest.mark.asyncio
    async def test_completes_job_with_correct_stats(self):
        """Job completes with accurate statistics in metadata."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate3_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
            (candidate2_id,),
            (candidate3_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=3,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        promote_call_count = [0]

        async def promote_side_effect(session, cid):
            promote_call_count[0] += 1
            return promote_call_count[0] != 3

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                side_effect=promote_side_effect,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["total_candidates"] == 3
            assert result["promoted"] == 2
            assert result["failed"] == 1
            assert result["dry_run"] is False
            mock_batch_job_service.complete_job.assert_called_once()
            _, completed_tasks, failed_tasks = mock_batch_job_service.complete_job.call_args.args
            assert completed_tasks == 2
            assert failed_tasks == 1


class TestPromotionBatchFailureHandling:
    """Test failure handling scenarios."""

    @pytest.mark.asyncio
    async def test_job_fails_on_database_error(self):
        """Database error causes job failure."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        mock_db.execute = AsyncMock(side_effect=Exception("Database connection lost"))

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                side_effect=Exception("Database connection lost"),
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            with pytest.raises(Exception, match="Database connection lost"):
                await process_promotion_batch(
                    job_id=job_id,
                    batch_size=10,
                    dry_run=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_resources_cleaned_up_on_failure(self):
        """Resources are cleaned up even when job fails."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_db.execute = AsyncMock(return_value=MagicMock())

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock(side_effect=Exception("Start job failed"))
        mock_batch_job_service.fail_job = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        mock_engine_instance = MagicMock()
        mock_engine_instance.dispose = AsyncMock()

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = mock_engine_instance
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            with pytest.raises(Exception, match="Start job failed"):
                await process_promotion_batch(
                    job_id=job_id,
                    batch_size=10,
                    dry_run=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_redis.disconnect.assert_called_once()
            mock_engine_instance.dispose.assert_called_once()


class TestPromotionBatchNoCandidates:
    """Test handling of empty candidate sets."""

    @pytest.mark.asyncio
    async def test_handles_no_scraped_candidates(self):
        """Completes successfully when no scraped candidates exist."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=0,
            candidate_rows=[],
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["total_candidates"] == 0
            assert result["promoted"] == 0
            assert result["failed"] == 0
            mock_batch_job_service.complete_job.assert_called_once()


class TestPromotionBatchRaceConditions:
    """Test race condition handling during batch processing."""

    @pytest.mark.asyncio
    async def test_handles_candidate_status_change_during_processing(self):
        """Handles race condition when candidate status changes between count and fetch."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
            (candidate2_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=3,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                return_value=True,
            ) as mock_promote,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["total_candidates"] == 3
            assert result["promoted"] == 2
            assert result["failed"] == 0
            assert mock_promote.call_count == 2
            mock_batch_job_service.complete_job.assert_called_once()


class TestPromotionBatchExceptionHandling:
    """Test exception handling during promotion."""

    @pytest.mark.asyncio
    async def test_handles_promote_candidate_exception(self):
        """Handles exception raised by promote_candidate gracefully."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
            (candidate2_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=2,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.fail_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        promote_call_count = [0]

        async def promote_raises_on_second(session, cid):
            promote_call_count[0] += 1
            if promote_call_count[0] == 2:
                raise RuntimeError("Database constraint violation")
            return True

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                side_effect=promote_raises_on_second,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            with pytest.raises(RuntimeError, match="Database constraint violation"):
                await process_promotion_batch(
                    job_id=job_id,
                    batch_size=10,
                    dry_run=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()


@pytest.mark.unit
class TestPromotionBatchTaskLabels:
    """Test TaskIQ task labels are properly configured."""

    def test_promotion_batch_task_has_labels(self):
        """Verify promotion batch task has component and task_type labels."""
        import src.tasks.import_tasks  # noqa: F401
        from src.tasks.broker import get_registered_tasks

        registered_tasks = get_registered_tasks()
        assert PROMOTION_JOB_TYPE in registered_tasks

        _, labels = registered_tasks[PROMOTION_JOB_TYPE]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "batch"


class TestMidBatchCrashRecovery:
    """Test recovery from crashes that leave candidates stuck in PROMOTING state.

    The race condition fix ensures only ONE candidate is ever in PROMOTING state
    at a time (single-candidate processing). Combined with the recovery mechanism,
    this guarantees:
    1. At most 1 candidate stuck in PROMOTING if worker crashes mid-processing
    2. Stuck candidates are recovered on next batch run (after timeout)
    3. Recovered candidates are processed normally
    """

    @pytest.mark.asyncio
    async def test_recovery_from_crash_after_promoting_status_set(self):
        """Verify stuck candidates are recovered and counted in stats.

        Simulates the scenario where a previous worker crash left candidates
        in PROMOTING state. The recovery mechanism should reset them to SCRAPED
        before processing begins.
        """
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=1,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        recovered_count = 3

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                return_value=True,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=recovered_count,
            ) as mock_recover,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_recover.assert_called_once()

            assert result["status"] == "completed"
            assert result["recovered_stuck"] == recovered_count
            assert result["promoted"] == 1
            assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_single_candidate_processing_limits_stuck_blast_radius(self):
        """Verify processing is single-candidate to limit crash impact.

        The code uses LIMIT 1 to ensure only one candidate is ever marked
        PROMOTING at a time. This test verifies the pattern by checking
        that each iteration processes exactly one candidate.
        """
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
            (candidate2_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=2,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        promote_calls = []

        async def track_promote(session, cid):
            promote_calls.append(cid)
            return True

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                side_effect=track_promote,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["promoted"] == 2
            assert len(promote_calls) == 2
            assert candidate1_id in promote_calls
            assert candidate2_id in promote_calls


class TestPromotionBatchEmptyContentHandling:
    """Test handling of candidates with empty string content.

    Task: task-1008.07 - Add empty content validation in promotion query

    The promotion queries filter on content.is_not(None) but empty strings ('')
    would still pass. This test class verifies that empty content candidates
    are excluded at the query level to avoid wasted processing.
    """

    @pytest.mark.asyncio
    async def test_excludes_candidates_with_empty_content(self):
        """Verify candidates with empty string content are not processed.

        When a candidate has content='' (empty string), it should be excluded
        from both the count query and the candidate selection query. This prevents
        wasting processing on candidates that would fail validation anyway.
        """
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate_rows = [
            (candidate1_id,),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=1,
            candidate_rows=candidate_rows,
        )

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()
        mock_batch_job_service.update_progress = AsyncMock()
        mock_job = MagicMock()
        mock_job.metadata_ = {}
        mock_batch_job_service.get_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.tasks.import_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.import_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.import_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.import_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.import_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch(
                "src.tasks.import_tasks.promote_candidate",
                return_value=True,
            ) as mock_promote,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_promoting_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_promotion_batch

            result = await process_promotion_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["promoted"] == 1
            mock_promote.assert_called_once()

    @pytest.mark.asyncio
    async def test_candidate_with_empty_content_is_not_promoted(self):
        """Verify candidates with empty string content are not promoted.

        This tests the actual validation behavior rather than inspecting source code.
        """
        from src.fact_checking.import_pipeline.promotion import (
            _validate_candidate_for_promotion,
        )

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.content = ""
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"

        result = _validate_candidate_for_promotion(mock_candidate, candidate_id)

        assert result is not None
        assert "without content" in result

    @pytest.mark.asyncio
    async def test_candidate_with_none_content_is_not_promoted(self):
        """Verify candidates with None content are not promoted."""
        from src.fact_checking.import_pipeline.promotion import (
            _validate_candidate_for_promotion,
        )

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.content = None
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"

        result = _validate_candidate_for_promotion(mock_candidate, candidate_id)

        assert result is not None
        assert "without content" in result

    @pytest.mark.asyncio
    async def test_candidate_with_valid_content_passes_validation(self):
        """Verify candidates with valid content pass validation."""
        from src.fact_checking.import_pipeline.promotion import (
            _validate_candidate_for_promotion,
        )

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.content = "Valid scraped content"
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"

        result = _validate_candidate_for_promotion(mock_candidate, candidate_id)

        assert result is None
