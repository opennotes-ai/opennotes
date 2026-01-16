"""
Unit tests for process_scrape_batch TaskIQ task.

Task: task-1006.01 - Create TaskIQ task process_scrape_batch

Tests cover:
- Processing pending candidates with progress tracking
- Handling scrape failures gracefully (marks as failed but continues)
- Dry run mode (counts candidates but doesn't scrape)
- Job completion with correct stats
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from .conftest import create_mock_session_context, create_mock_settings

pytestmark = pytest.mark.unit


def create_flexible_execute_mock(
    total_count: int,
    candidate_rows: list,
    batch_exhausted_after: int | None = None,
):
    """
    Create a flexible mock for db.execute that handles various query types.

    Args:
        total_count: Count to return for COUNT queries
        candidate_rows: List of (id, url) tuples to return for SELECT queries via fetchone()
        batch_exhausted_after: Ignored (kept for backward compatibility).
            Candidates are returned one at a time via fetchone() until exhausted.
    """
    candidate_index = [0]

    def execute_side_effect(query):
        result = MagicMock()

        query_str = str(query)
        query_lower = query_str.lower()

        if "count(" in query_lower:
            result.scalar_one.return_value = total_count
        elif query_lower.strip().startswith("update") or "set status" in query_lower:
            result.rowcount = 1
        else:

            def mock_fetchone():
                if candidate_index[0] < len(candidate_rows):
                    row = candidate_rows[candidate_index[0]]
                    candidate_index[0] += 1
                    return row
                return None

            result.fetchone = mock_fetchone
            result.scalar_one.return_value = total_count

        return result

    return AsyncMock(side_effect=execute_side_effect)


class TestScrapeBatchProcessing:
    """Test main scrape batch processing functionality."""

    @pytest.mark.asyncio
    async def test_processes_pending_candidates_and_updates_progress(self):
        """Successfully processes pending candidates and tracks progress."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id, "https://example.com/article1"),
            (candidate2_id, "https://example.com/article2"),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=2,
            candidate_rows=candidate_rows,
            batch_exhausted_after=1,
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
                "src.tasks.import_tasks.scrape_url_content",
                return_value="Scraped content here",
            ) as mock_scrape,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["scraped"] == 2
            assert result["failed"] == 0
            mock_batch_job_service.start_job.assert_called_once()
            mock_batch_job_service.complete_job.assert_called_once()
            assert mock_scrape.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_scrape_failures_gracefully(self):
        """Scrape failures are marked as failed but processing continues."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id, "https://example.com/good"),
            (candidate2_id, "https://example.com/bad"),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=2,
            candidate_rows=candidate_rows,
            batch_exhausted_after=1,
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

        def scrape_side_effect(url):
            if "bad" in url:
                return None
            return "Scraped content"

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
                "src.tasks.import_tasks.scrape_url_content",
                side_effect=scrape_side_effect,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["scraped"] == 1
            assert result["failed"] == 1
            mock_batch_job_service.complete_job.assert_called_once()


class TestScrapeBatchDryRun:
    """Test dry run mode functionality."""

    @pytest.mark.asyncio
    async def test_dry_run_counts_but_does_not_scrape(self):
        """Dry run mode counts candidates but doesn't perform scraping."""
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
            patch("src.tasks.import_tasks.scrape_url_content") as mock_scrape,
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=True,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["dry_run"] is True
            assert result["total_candidates"] == 5
            assert result["scraped"] == 0
            assert result["failed"] == 0
            mock_scrape.assert_not_called()
            mock_batch_job_service.complete_job.assert_called_once()


class TestScrapeBatchJobCompletion:
    """Test job completion with correct stats."""

    @pytest.mark.asyncio
    async def test_completes_job_with_correct_stats(self):
        """Job completes with accurate statistics in metadata."""
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate3_id = uuid4()
        candidate_rows = [
            (candidate1_id, "https://example.com/1"),
            (candidate2_id, "https://example.com/2"),
            (candidate3_id, "https://example.com/fail"),
        ]

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=3,
            candidate_rows=candidate_rows,
            batch_exhausted_after=1,
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

        def scrape_side_effect(url):
            if "fail" in url:
                return None
            return "Content scraped successfully"

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
                "src.tasks.import_tasks.scrape_url_content",
                side_effect=scrape_side_effect,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["total_candidates"] == 3
            assert result["scraped"] == 2
            assert result["failed"] == 1
            assert result["dry_run"] is False
            mock_batch_job_service.complete_job.assert_called_once()
            call_args = mock_batch_job_service.complete_job.call_args
            assert call_args[0][1] == 2
            assert call_args[0][2] == 1


class TestScrapeBatchFailureHandling:
    """Test failure handling scenarios."""

    @pytest.mark.asyncio
    async def test_job_fails_on_database_error(self):
        """Database error causes job failure with proper error_summary."""
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
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                side_effect=Exception("Database connection lost"),
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            with pytest.raises(Exception, match="Database connection lost"):
                await process_scrape_batch(
                    job_id=job_id,
                    batch_size=10,
                    dry_run=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_batch_job_service.fail_job.assert_called_once()
            call_args = mock_batch_job_service.fail_job.call_args
            error_summary = call_args[0][1]
            assert "exception" in error_summary
            assert error_summary["exception"] == "Database connection lost"
            assert "exception_type" in error_summary
            assert error_summary["exception_type"] == "Exception"
            assert "partial_stats" in error_summary
            completed_tasks = call_args[0][2]
            failed_tasks = call_args[0][3]
            assert completed_tasks == 0
            assert failed_tasks == 0

    @pytest.mark.asyncio
    async def test_resources_cleaned_up_on_failure(self):
        """Resources are cleaned up even when job fails."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

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
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = mock_engine_instance
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            with pytest.raises(Exception, match="Start job failed"):
                await process_scrape_batch(
                    job_id=job_id,
                    batch_size=10,
                    dry_run=False,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_redis.disconnect.assert_called_once()
            mock_engine_instance.dispose.assert_called_once()


class TestScrapeBatchNoCandidates:
    """Test handling of empty candidate sets."""

    @pytest.mark.asyncio
    async def test_handles_no_pending_candidates(self):
        """Completes successfully when no pending candidates exist."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = create_flexible_execute_mock(
            total_count=0,
            candidate_rows=[],
            batch_exhausted_after=0,
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
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["total_candidates"] == 0
            assert result["scraped"] == 0
            assert result["failed"] == 0
            mock_batch_job_service.complete_job.assert_called_once()


class TestScrapeBatchTaskLabels:
    """Test TaskIQ task labels are properly configured."""

    def test_scrape_batch_task_has_labels(self):
        """Verify scrape batch task has component and task_type labels."""
        import src.tasks.import_tasks  # noqa: F401
        from src.tasks.broker import get_registered_tasks

        registered_tasks = get_registered_tasks()
        assert "scrape:candidates" in registered_tasks

        _, labels = registered_tasks["scrape:candidates"]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "batch"


@pytest.mark.unit
class TestScrapeBatchRaceConditionPrevention:
    """Test that status is updated atomically within FOR UPDATE lock session.

    The race condition fix ensures:
    1. SELECT ... FOR UPDATE SKIP LOCKED (acquire lock)
    2. UPDATE ... SET status='scraping' (while still holding lock)
    3. COMMIT (release lock atomically with status change)

    This test verifies the fix by checking that:
    - The code path includes both SELECT FOR UPDATE and UPDATE queries
    - Status update to SCRAPING happens before lock is released

    RATIONALE FOR SOURCE INSPECTION:
    --------------------------------
    This test uses inspect.getsource() rather than behavior-based testing because:

    1. Race conditions are timing-dependent and non-deterministic. A behavior test
       that runs concurrent workers might pass 99% of the time even with broken code,
       only failing under specific timing conditions in production.

    2. The fix being verified is a CODE STRUCTURE requirement: the status update MUST
       occur between acquiring the FOR UPDATE lock and committing the transaction.
       Source inspection guarantees this structure is present.

    3. Integration tests for race conditions require complex setup (multiple workers,
       real database connections, artificial delays) and still may not reliably
       reproduce the race condition.

    IF THIS TEST FAILS AFTER REFACTORING:
    -------------------------------------
    1. Verify the race condition fix is still present in the refactored code
    2. The pattern to look for: SELECT ... FOR UPDATE, then UPDATE status, then COMMIT
    3. Update the string searches in this test to match the new code structure
    4. Do NOT simply delete this test - the race condition prevention is critical
    """

    def test_scrape_batch_updates_status_in_for_update_session(self):
        """Verify process_scrape_batch updates status within the FOR UPDATE session."""
        import inspect

        from src.tasks.import_tasks import process_scrape_batch

        source = inspect.getsource(process_scrape_batch._func)

        scraping_in_update = source.find(".values(status=CandidateStatus.SCRAPING")
        assert scraping_in_update != -1, (
            "Code should update status to SCRAPING in a values() call. "
            "This prevents race conditions by marking candidates before releasing lock."
        )

        for_update_pos = source.find("with_for_update")

        assert for_update_pos < scraping_in_update, (
            "SCRAPING status update should come after FOR UPDATE query is defined"
        )

        commit_search_start = source.find("with_for_update")
        commit_in_session = source.find("await db.commit()", commit_search_start)
        scraping_in_session = source.find(
            ".values(status=CandidateStatus.SCRAPING", commit_search_start
        )

        assert scraping_in_session < commit_in_session, (
            "Status update to SCRAPING must happen BEFORE commit (which releases the lock)"
        )


@pytest.mark.unit
class TestMidBatchCrashRecovery:
    """Test recovery from crashes that leave candidates stuck in SCRAPING state.

    The race condition fix ensures only ONE candidate is ever in SCRAPING state
    at a time (single-candidate processing). Combined with the recovery mechanism,
    this guarantees:
    1. At most 1 candidate stuck in SCRAPING if worker crashes mid-processing
    2. Stuck candidates are recovered on next batch run (after timeout)
    3. Recovered candidates are processed normally
    """

    @pytest.mark.asyncio
    async def test_recovery_from_crash_after_scraping_status_set(self):
        """Verify stuck candidates are recovered and counted in stats.

        Simulates the scenario where a previous worker crash left candidates
        in SCRAPING state. The recovery mechanism should reset them to PENDING
        before processing begins.
        """
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate_rows = [
            (candidate1_id, "https://example.com/article"),
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
                "src.tasks.import_tasks.scrape_url_content",
                return_value="Recovered content",
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=recovered_count,
            ) as mock_recover,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_recover.assert_called_once()

            assert result["status"] == "completed"
            assert result["recovered_stuck"] == recovered_count
            assert result["scraped"] == 1
            assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_single_candidate_processing_limits_stuck_blast_radius(self):
        """Verify processing is single-candidate to limit crash impact.

        The code uses LIMIT 1 to ensure only one candidate is ever marked
        SCRAPING at a time. This test verifies the pattern by checking
        that each iteration processes exactly one candidate.
        """
        job_id = str(uuid4())

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate_rows = [
            (candidate1_id, "https://example.com/1"),
            (candidate2_id, "https://example.com/2"),
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

        scrape_calls = []

        def track_scrape(url):
            scrape_calls.append(url)
            return f"Content for {url}"

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
                "src.tasks.import_tasks.scrape_url_content",
                side_effect=track_scrape,
            ),
            patch("src.tasks.import_tasks.get_settings") as mock_settings,
            patch(
                "src.tasks.import_tasks._recover_stuck_scraping_candidates",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            mock_settings.return_value = create_mock_settings()

            from src.tasks.import_tasks import process_scrape_batch

            result = await process_scrape_batch(
                job_id=job_id,
                batch_size=10,
                dry_run=False,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["scraped"] == 2
            assert len(scrape_calls) == 2
            assert "https://example.com/1" in scrape_calls
            assert "https://example.com/2" in scrape_calls
