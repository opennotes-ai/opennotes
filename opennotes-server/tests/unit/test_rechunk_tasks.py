"""
Unit tests for TaskIQ rechunk tasks using BatchJob infrastructure.

Task: task-909.06 - Add test coverage for TaskIQ rechunk tasks
Task: task-986 - Refactor to use BatchJob infrastructure

AC#2: Create tests/unit/test_rechunk_tasks.py for task logic
AC#3: Test batch iteration logic
AC#4: Test progress tracking updates (via BatchJobProgressTracker)
AC#5: Test lock release on success and failure paths
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs.models import BatchJobStatus


class TestFactCheckRechunkTaskBatchIteration:
    """Test batch iteration logic for fact check rechunk task (AC#3)."""

    @pytest.mark.asyncio
    async def test_processes_items_in_batches(self):
        """Task processes items in batches according to batch_size."""
        job_id = str(uuid4())
        community_server_id = str(uuid4())
        batch_size = 2

        mock_items_batch1 = [
            MagicMock(id=uuid4(), content="item1"),
            MagicMock(id=uuid4(), content="item2"),
        ]
        mock_items_batch2 = [MagicMock(id=uuid4(), content="item3")]
        mock_items_empty = []

        query_results = [mock_items_batch1, mock_items_batch2, mock_items_empty]
        query_call_count = [0]
        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 3
                return result
            result.scalars.return_value.all.return_value = query_results[query_call_count[0]]
            query_call_count[0] += 1
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.complete_job = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service", return_value=mock_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.rechunk_tasks import process_fact_check_rechunk_task

            result = await process_fact_check_rechunk_task(
                job_id=job_id,
                community_server_id=community_server_id,
                batch_size=batch_size,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == BatchJobStatus.COMPLETED.value
            assert result["processed_count"] == 3

            assert mock_service.chunk_and_embed_fact_check.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_empty_result_set(self):
        """Task handles case when no items to process."""
        job_id = str(uuid4())
        batch_size = 10

        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 0
                return result
            result.scalars.return_value.all.return_value = []
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.complete_job = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service", return_value=mock_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.rechunk_tasks import process_fact_check_rechunk_task

            result = await process_fact_check_rechunk_task(
                job_id=job_id,
                community_server_id=None,
                batch_size=batch_size,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == BatchJobStatus.COMPLETED.value
            assert result["processed_count"] == 0
            mock_service.chunk_and_embed_fact_check.assert_not_called()


class TestRechunkTaskProgressTracking:
    """Test progress tracking updates using BatchJobProgressTracker (AC#4)."""

    @pytest.mark.asyncio
    async def test_updates_progress_via_progress_tracker(self):
        """Task updates progress via BatchJobProgressTracker after each item."""
        job_id = str(uuid4())

        mock_items = [
            MagicMock(id=uuid4(), content="item1"),
            MagicMock(id=uuid4(), content="item2"),
        ]
        call_count = [0]

        async def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar.return_value = 2
                return result
            if call_count[0] == 2:
                result.scalars.return_value.all.return_value = mock_items
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.complete_job = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service", return_value=mock_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.rechunk_tasks import process_fact_check_rechunk_task

            await process_fact_check_rechunk_task(
                job_id=job_id,
                community_server_id=None,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert mock_progress_tracker.update_progress.call_count == 2

    @pytest.mark.asyncio
    async def test_calls_complete_job_on_success(self):
        """Task calls complete_job with correct counts on success."""
        job_id = str(uuid4())

        mock_items = [
            MagicMock(id=uuid4(), content="item1"),
            MagicMock(id=uuid4(), content="item2"),
        ]
        call_count = [0]

        async def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar.return_value = 2
                return result
            if call_count[0] == 2:
                result.scalars.return_value.all.return_value = mock_items
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.complete_job = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service", return_value=mock_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.rechunk_tasks import process_fact_check_rechunk_task

            await process_fact_check_rechunk_task(
                job_id=job_id,
                community_server_id=None,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_batch_job_service.complete_job.assert_called_once()
            call_args = mock_batch_job_service.complete_job.call_args
            assert call_args.kwargs["completed_tasks"] == 2
            assert call_args.kwargs["failed_tasks"] == 0

    @pytest.mark.asyncio
    async def test_item_errors_are_counted_as_failed_not_propagated(self):
        """Individual item errors are counted as failed, not propagated to fail the whole task.

        In the refactored code, individual item failures:
        1. Are logged and counted in failed_count
        2. Do NOT propagate to fail the whole task
        3. Task completes with completed_tasks=0, failed_tasks=N
        4. This is different from task-level failures (e.g., DB connection issues)
           which DO propagate and are handled by the callback
        """
        job_id = str(uuid4())

        mock_items = [MagicMock(id=uuid4(), content="item1")]
        call_count = [0]

        async def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar.return_value = 1
                return result
            if call_count[0] == 2:
                result.scalars.return_value.all.return_value = mock_items
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)
        mock_progress_tracker.update_progress = AsyncMock()

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.fail_job = AsyncMock()
        mock_batch_job_service.complete_job = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock(
            side_effect=Exception("Embedding API error")
        )

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service", return_value=mock_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            settings.DB_POOL_TIMEOUT = 30
            settings.DB_POOL_RECYCLE = 1800
            mock_settings.return_value = settings

            from src.tasks.rechunk_tasks import process_fact_check_rechunk_task

            result = await process_fact_check_rechunk_task(
                job_id=job_id,
                community_server_id=None,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == BatchJobStatus.COMPLETED.value
            assert result["processed_count"] == 0
            assert result["failed_count"] == 1

            mock_batch_job_service.fail_job.assert_not_called()
            mock_batch_job_service.complete_job.assert_called_once()
            call_args = mock_batch_job_service.complete_job.call_args
            assert call_args.kwargs["completed_tasks"] == 0
            assert call_args.kwargs["failed_tasks"] == 1


class TestTaskIQLabels:
    """Test TaskIQ labels are properly configured (task-909.07)."""

    def test_fact_check_task_has_labels(self):
        """Verify fact check rechunk task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "rechunk:fact_check" in _all_registered_tasks

        _, labels = _all_registered_tasks["rechunk:fact_check"]
        assert labels.get("component") == "rechunk"
        assert labels.get("task_type") == "batch"

    def test_previously_seen_task_has_labels(self):
        """Verify previously seen rechunk task has component and task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "rechunk:previously_seen" in _all_registered_tasks

        _, labels = _all_registered_tasks["rechunk:previously_seen"]
        assert labels.get("component") == "rechunk"
        assert labels.get("task_type") == "batch"


class TestDeadlockRetryForFactCheckItem:
    """Test deadlock retry logic for fact check item processing (task-924)."""

    @pytest.mark.asyncio
    async def test_retries_on_deadlock_and_succeeds(self):
        """Retries on deadlock and eventually succeeds."""
        from asyncpg.exceptions import DeadlockDetectedError

        from src.tasks.rechunk_tasks import _process_fact_check_item_with_retry

        item_id = uuid4()
        item_content = "test content"
        community_server_id = uuid4()

        call_count = [0]

        async def mock_chunk_and_embed(db, fact_check_id, text, community_server_id):
            call_count[0] += 1
            if call_count[0] < 3:
                raise DeadlockDetectedError("")
            return []

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = mock_chunk_and_embed

        with patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker):
            await _process_fact_check_item_with_retry(
                engine=mock_engine,
                service=mock_service,
                item_id=item_id,
                item_content=item_content,
                community_server_id=community_server_id,
            )

        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        """Raises deadlock error after max retries exhausted."""
        from asyncpg.exceptions import DeadlockDetectedError

        from src.tasks.rechunk_tasks import _process_fact_check_item_with_retry

        item_id = uuid4()
        item_content = "test content"
        community_server_id = uuid4()

        call_count = [0]

        async def mock_chunk_and_embed(db, fact_check_id, text, community_server_id):
            call_count[0] += 1
            raise DeadlockDetectedError("")

        mock_db = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = mock_chunk_and_embed

        with (
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            pytest.raises(DeadlockDetectedError),
        ):
            await _process_fact_check_item_with_retry(
                engine=mock_engine,
                service=mock_service,
                item_id=item_id,
                item_content=item_content,
                community_server_id=community_server_id,
            )

        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_non_deadlock_errors(self):
        """Does not retry on non-deadlock exceptions."""
        from src.tasks.rechunk_tasks import _process_fact_check_item_with_retry

        item_id = uuid4()
        item_content = "test content"
        community_server_id = uuid4()

        call_count = [0]

        async def mock_chunk_and_embed(db, fact_check_id, text, community_server_id):
            call_count[0] += 1
            raise ValueError("not a deadlock")

        mock_db = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = mock_chunk_and_embed

        with (
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            pytest.raises(ValueError, match="not a deadlock"),
        ):
            await _process_fact_check_item_with_retry(
                engine=mock_engine,
                service=mock_service,
                item_id=item_id,
                item_content=item_content,
                community_server_id=community_server_id,
            )

        assert call_count[0] == 1


class TestDeadlockRetryForPreviouslySeenItem:
    """Test deadlock retry logic for previously seen message processing (task-924)."""

    @pytest.mark.asyncio
    async def test_retries_on_deadlock_and_succeeds(self):
        """Retries on deadlock and eventually succeeds."""
        from asyncpg.exceptions import DeadlockDetectedError

        from src.tasks.rechunk_tasks import _process_previously_seen_item_with_retry

        item_id = uuid4()
        item_content = "test content"
        community_server_id = uuid4()

        call_count = [0]

        async def mock_chunk_and_embed(db, previously_seen_id, text, community_server_id):
            call_count[0] += 1
            if call_count[0] < 2:
                raise DeadlockDetectedError("")
            return []

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_previously_seen = mock_chunk_and_embed

        with patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker):
            await _process_previously_seen_item_with_retry(
                engine=mock_engine,
                service=mock_service,
                item_id=item_id,
                item_content=item_content,
                community_server_id=community_server_id,
            )

        assert call_count[0] == 2


class TestFinalRetryCallbackHandlers:
    """Test the final-retry callback handlers for rechunk tasks (task-933).

    Note: These tests verify the callback handlers call BatchJobService.fail_job
    instead of the old RechunkTaskTracker.mark_failed.
    """

    @pytest.mark.asyncio
    async def test_fact_check_callback_marks_job_failed(self):
        """Fact check callback marks job failed."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_fact_check_rechunk_final_failure

        job_id = str(uuid4())
        redis_url = "redis://localhost:6379"
        db_url = "postgresql+asyncpg://test:test@localhost/test"
        error = Exception("All retries exhausted")

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {"job_id": job_id, "redis_url": redis_url, "db_url": db_url}

        result = MagicMock(spec=TaskiqResult)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.fail_job = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            mock_settings.return_value = settings

            await _handle_fact_check_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_called_once_with(redis_url)
            mock_batch_job_service.fail_job.assert_called_once()
            mock_redis.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_fact_check_callback_handles_missing_params(self):
        """Fact check callback handles missing job_id, redis_url, or db_url gracefully."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_fact_check_rechunk_final_failure

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {}

        result = MagicMock(spec=TaskiqResult)
        error = Exception("Error")

        mock_redis = AsyncMock()

        with patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis):
            await _handle_fact_check_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_previously_seen_callback_marks_job_failed(self):
        """Previously seen callback marks job failed."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_previously_seen_rechunk_final_failure

        job_id = str(uuid4())
        community_server_id = str(uuid4())
        redis_url = "redis://localhost:6379"
        db_url = "postgresql+asyncpg://test:test@localhost/test"
        error = Exception("All retries exhausted")

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {
            "job_id": job_id,
            "community_server_id": community_server_id,
            "redis_url": redis_url,
            "db_url": db_url,
        }

        result = MagicMock(spec=TaskiqResult)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_progress_tracker = MagicMock()
        mock_progress_tracker.get_progress = AsyncMock(return_value=None)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_batch_job_service = MagicMock()
        mock_batch_job_service.fail_job = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch(
                "src.tasks.rechunk_tasks.BatchJobProgressTracker",
                return_value=mock_progress_tracker,
            ),
            patch("src.tasks.rechunk_tasks.BatchJobService", return_value=mock_batch_job_service),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
        ):
            mock_engine.return_value = MagicMock()
            mock_engine.return_value.dispose = AsyncMock()
            settings = MagicMock()
            settings.DB_POOL_SIZE = 5
            settings.DB_POOL_MAX_OVERFLOW = 10
            mock_settings.return_value = settings

            await _handle_previously_seen_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_called_once_with(redis_url)
            mock_batch_job_service.fail_job.assert_called_once()
            mock_redis.disconnect.assert_called_once()
