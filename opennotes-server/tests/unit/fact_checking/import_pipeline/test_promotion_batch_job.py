"""
Unit tests for process_promotion_batch TaskIQ task.

Task: task-1006.02 - Create TaskIQ task process_promotion_batch

Tests cover:
- Processing scraped candidates with progress tracking
- Handling promotion failures gracefully (marks as failed but continues)
- Dry run mode (counts candidates but doesn't promote)
- Job completion with correct stats
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def create_mock_settings():
    """Create mock settings for tests."""
    settings = MagicMock()
    settings.DB_POOL_SIZE = 5
    settings.DB_POOL_MAX_OVERFLOW = 10
    settings.DB_POOL_TIMEOUT = 30
    settings.DB_POOL_RECYCLE = 1800
    return settings


def create_mock_session_context(mock_db):
    """Create a mock async session context manager."""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_session_maker


class TestPromotionBatchProcessing:
    """Test main promotion batch processing functionality."""

    @pytest.mark.asyncio
    async def test_processes_scraped_candidates_and_updates_progress(self):
        """Successfully processes scraped candidates and tracks progress."""
        job_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        candidate1_id = uuid4()
        candidate2_id = uuid4()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        mock_candidates_result_first = MagicMock()
        mock_candidates_result_first.fetchall.return_value = [(candidate1_id,), (candidate2_id,)]

        mock_candidates_result_empty = MagicMock()
        mock_candidates_result_empty.fetchall.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_count_result,
                mock_candidates_result_first,
                mock_candidates_result_empty,
            ]
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

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        candidate1_id = uuid4()
        candidate2_id = uuid4()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        mock_candidates_result_first = MagicMock()
        mock_candidates_result_first.fetchall.return_value = [(candidate1_id,), (candidate2_id,)]

        mock_candidates_result_empty = MagicMock()
        mock_candidates_result_empty.fetchall.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_count_result,
                mock_candidates_result_first,
                mock_candidates_result_empty,
            ]
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

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        candidate1_id = uuid4()
        candidate2_id = uuid4()
        candidate3_id = uuid4()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 3

        mock_candidates_result_first = MagicMock()
        mock_candidates_result_first.fetchall.return_value = [
            (candidate1_id,),
            (candidate2_id,),
            (candidate3_id,),
        ]

        mock_candidates_result_empty = MagicMock()
        mock_candidates_result_empty.fetchall.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_count_result,
                mock_candidates_result_first,
                mock_candidates_result_empty,
            ]
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
            call_args = mock_batch_job_service.complete_job.call_args
            assert call_args[0][1] == 2
            assert call_args[0][2] == 1


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

        mock_session_maker = create_mock_session_context(mock_db)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.start_job = AsyncMock(side_effect=Exception("Start job failed"))
        mock_batch_job_service.fail_job = AsyncMock()

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

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        empty_candidates_result = MagicMock()
        empty_candidates_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, empty_candidates_result])

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


class TestPromotionBatchTaskLabels:
    """Test TaskIQ task labels are properly configured."""

    def test_promotion_batch_task_has_labels(self):
        """Verify promotion batch task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "promote:candidates" in _all_registered_tasks

        _, labels = _all_registered_tasks["promote:candidates"]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "batch"
