"""
Unit tests for TaskIQ rechunk tasks.

Task: task-909.06 - Add test coverage for TaskIQ rechunk tasks
AC#2: Create tests/unit/test_rechunk_tasks.py for task logic
AC#3: Test batch iteration logic
AC#4: Test progress tracking updates (update_progress, mark_completed, mark_failed)
AC#5: Test lock release on success and failure paths
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.fact_checking.chunk_task_schemas import RechunkTaskStatus


class TestFactCheckRechunkTaskBatchIteration:
    """Test batch iteration logic for fact check rechunk task (AC#3)."""

    @pytest.mark.asyncio
    async def test_processes_items_in_batches(self):
        """Task processes items in batches according to batch_size."""
        task_id = str(uuid4())
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
                result.scalar.return_value = 3  # Total items count
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.update_progress = AsyncMock()
        mock_tracker.mark_completed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
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
                task_id=task_id,
                community_server_id=community_server_id,
                batch_size=batch_size,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["processed_count"] == 3

            assert mock_service.chunk_and_embed_fact_check.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_empty_result_set(self):
        """Task handles case when no items to process."""
        task_id = str(uuid4())
        batch_size = 10

        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 0  # Total items count
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.update_progress = AsyncMock()
        mock_tracker.mark_completed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
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
                task_id=task_id,
                community_server_id=None,
                batch_size=batch_size,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            assert result["status"] == "completed"
            assert result["processed_count"] == 0
            mock_service.chunk_and_embed_fact_check.assert_not_called()


class TestRechunkTaskProgressTracking:
    """Test progress tracking updates (AC#4)."""

    @pytest.mark.asyncio
    async def test_updates_status_to_in_progress(self):
        """Task updates status to IN_PROGRESS on start."""
        task_id = str(uuid4())
        task_uuid = uuid4()

        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 0  # Total items count
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.update_progress = AsyncMock()
        mock_tracker.mark_completed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service"),
            patch("src.tasks.rechunk_tasks.get_settings") as mock_settings,
            patch("src.tasks.rechunk_tasks.UUID", return_value=task_uuid),
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
                task_id=task_id,
                community_server_id=None,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_tracker.update_status.assert_called_once()
            call_args = mock_tracker.update_status.call_args
            assert call_args[0][1] == RechunkTaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_calls_mark_completed_on_success(self):
        """Task calls mark_completed with correct count on success."""
        task_id = str(uuid4())

        mock_items = [
            MagicMock(id=uuid4(), content="item1"),
            MagicMock(id=uuid4(), content="item2"),
        ]
        call_count = [0]

        async def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar.return_value = 2  # COUNT query returns total items
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.update_progress = AsyncMock()
        mock_tracker.mark_completed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
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
                task_id=task_id,
                community_server_id=None,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_tracker.mark_completed.assert_called_once()
            call_args = mock_tracker.mark_completed.call_args
            assert call_args[0][1] == 2

    @pytest.mark.asyncio
    async def test_does_not_call_mark_failed_directly_on_error(self):
        """Task does NOT call mark_failed directly - that's the callback's job."""
        task_id = str(uuid4())

        mock_items = [MagicMock(id=uuid4(), content="item1")]
        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 1  # Total items count
                return result
            result.scalars.return_value.all.return_value = mock_items
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.update_progress = AsyncMock()
        mock_tracker.mark_failed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock(
            side_effect=Exception("Embedding API error")
        )

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
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

            with pytest.raises(Exception, match="Embedding API error"):
                await process_fact_check_rechunk_task(
                    task_id=task_id,
                    community_server_id=None,
                    batch_size=10,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_tracker.mark_failed.assert_not_called()


class TestRechunkTaskLockRelease:
    """Test lock release on success and failure paths (AC#5)."""

    @pytest.mark.asyncio
    async def test_releases_lock_on_success(self):
        """Lock is released when task completes successfully."""
        task_id = str(uuid4())

        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 0  # Total items count
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.mark_completed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service"),
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
                task_id=task_id,
                community_server_id=None,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_lock_manager.release_lock.assert_called_once_with("fact_check")

    @pytest.mark.asyncio
    async def test_does_not_release_lock_on_failure(self):
        """Lock is NOT released on task failure - that's the callback's job."""
        task_id = str(uuid4())

        mock_items = [MagicMock(id=uuid4(), content="item1")]
        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 1  # Total items count
                return result
            result.scalars.return_value.all.return_value = mock_items
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.mark_failed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = AsyncMock(
            side_effect=Exception("Processing error")
        )

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
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

            with pytest.raises(Exception, match="Processing error"):
                await process_fact_check_rechunk_task(
                    task_id=task_id,
                    community_server_id=None,
                    batch_size=10,
                    db_url="postgresql+asyncpg://test:test@localhost/test",
                    redis_url="redis://localhost:6379",
                )

            mock_lock_manager.release_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_previously_seen_releases_lock_with_community_id(self):
        """Previously seen task releases lock with community_server_id."""
        task_id = str(uuid4())
        community_server_id = str(uuid4())

        is_count_query = [True]

        async def mock_execute(query):
            result = MagicMock()
            if is_count_query[0]:
                is_count_query[0] = False
                result.scalar.return_value = 0  # Total items count
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

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.update_status = AsyncMock()
        mock_tracker.mark_completed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.create_async_engine") as mock_engine,
            patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker),
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
            patch("src.tasks.rechunk_tasks.get_chunk_embedding_service"),
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

            from src.tasks.rechunk_tasks import process_previously_seen_rechunk_task

            await process_previously_seen_rechunk_task(
                task_id=task_id,
                community_server_id=community_server_id,
                batch_size=10,
                db_url="postgresql+asyncpg://test:test@localhost/test",
                redis_url="redis://localhost:6379",
            )

            mock_lock_manager.release_lock.assert_called_once_with(
                "previously_seen", community_server_id
            )


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

    @pytest.mark.asyncio
    async def test_creates_fresh_session_for_each_retry(self):
        """Creates a fresh database session for each retry attempt."""
        from asyncpg.exceptions import DeadlockDetectedError

        from src.tasks.rechunk_tasks import _process_fact_check_item_with_retry

        item_id = uuid4()
        item_content = "test content"
        community_server_id = uuid4()

        call_count = [0]
        session_instances = []

        async def mock_chunk_and_embed(db, fact_check_id, text, community_server_id):
            call_count[0] += 1
            session_instances.append(db)
            if call_count[0] < 2:
                raise DeadlockDetectedError("")
            return []

        def create_new_mock_session():
            mock_db = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            return mock_session

        mock_engine = MagicMock()

        mock_service = MagicMock()
        mock_service.chunk_and_embed_fact_check = mock_chunk_and_embed

        mock_session_maker = MagicMock(
            side_effect=[create_new_mock_session(), create_new_mock_session()]
        )

        with patch("src.tasks.rechunk_tasks.async_sessionmaker", return_value=mock_session_maker):
            await _process_fact_check_item_with_retry(
                engine=mock_engine,
                service=mock_service,
                item_id=item_id,
                item_content=item_content,
                community_server_id=community_server_id,
            )

        assert len(session_instances) == 2
        assert session_instances[0] is not session_instances[1]


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
    """Test the final-retry callback handlers for rechunk tasks (task-933)."""

    @pytest.mark.asyncio
    async def test_fact_check_callback_marks_failed_and_releases_lock(self):
        """Fact check callback marks task failed and releases lock."""
        from uuid import UUID

        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_fact_check_rechunk_final_failure

        task_id = str(uuid4())
        redis_url = "redis://localhost:6379"
        error = Exception("All retries exhausted")

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {"task_id": task_id, "redis_url": redis_url}

        result = MagicMock(spec=TaskiqResult)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.mark_failed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
        ):
            await _handle_fact_check_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_called_once_with(redis_url)
            mock_tracker.mark_failed.assert_called_once()
            call_args = mock_tracker.mark_failed.call_args
            assert call_args[0][0] == UUID(task_id)
            assert "All retries exhausted" in call_args[0][1]

            mock_lock_manager.release_lock.assert_called_once_with("fact_check")
            mock_redis.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_fact_check_callback_retrieves_processed_count(self):
        """Fact check callback retrieves processed_count from existing task."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_fact_check_rechunk_final_failure

        task_id = str(uuid4())
        redis_url = "redis://localhost:6379"
        error = Exception("Error occurred")

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {"task_id": task_id, "redis_url": redis_url}

        result = MagicMock(spec=TaskiqResult)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_existing_task = MagicMock()
        mock_existing_task.processed_count = 42

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=mock_existing_task)
        mock_tracker.mark_failed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
        ):
            await _handle_fact_check_rechunk_final_failure(message, result, error)

            call_args = mock_tracker.mark_failed.call_args
            assert call_args[0][2] == 42

    @pytest.mark.asyncio
    async def test_fact_check_callback_handles_missing_params(self):
        """Fact check callback handles missing task_id or redis_url gracefully."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_fact_check_rechunk_final_failure

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {}  # Missing task_id and redis_url

        result = MagicMock(spec=TaskiqResult)
        error = Exception("Error")

        mock_redis = AsyncMock()

        with patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis):
            await _handle_fact_check_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_previously_seen_callback_marks_failed_and_releases_lock(self):
        """Previously seen callback marks task failed and releases lock with community_id."""
        from uuid import UUID

        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_previously_seen_rechunk_final_failure

        task_id = str(uuid4())
        community_server_id = str(uuid4())
        redis_url = "redis://localhost:6379"
        error = Exception("All retries exhausted")

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {
            "task_id": task_id,
            "community_server_id": community_server_id,
            "redis_url": redis_url,
        }

        result = MagicMock(spec=TaskiqResult)

        mock_redis = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)
        mock_tracker.mark_failed = AsyncMock()

        mock_lock_manager = MagicMock()
        mock_lock_manager.release_lock = AsyncMock()

        with (
            patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis),
            patch("src.tasks.rechunk_tasks.RechunkTaskTracker", return_value=mock_tracker),
            patch("src.tasks.rechunk_tasks.TaskRechunkLockManager", return_value=mock_lock_manager),
        ):
            await _handle_previously_seen_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_called_once_with(redis_url)
            mock_tracker.mark_failed.assert_called_once()
            call_args = mock_tracker.mark_failed.call_args
            assert call_args[0][0] == UUID(task_id)
            assert "All retries exhausted" in call_args[0][1]

            mock_lock_manager.release_lock.assert_called_once_with(
                "previously_seen", community_server_id
            )
            mock_redis.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_previously_seen_callback_handles_missing_params(self):
        """Previously seen callback handles missing params gracefully."""
        from taskiq import TaskiqMessage, TaskiqResult

        from src.tasks.rechunk_tasks import _handle_previously_seen_rechunk_final_failure

        message = MagicMock(spec=TaskiqMessage)
        message.kwargs = {"task_id": str(uuid4())}  # Missing community_server_id and redis_url

        result = MagicMock(spec=TaskiqResult)
        error = Exception("Error")

        mock_redis = AsyncMock()

        with patch("src.tasks.rechunk_tasks.RedisClient", return_value=mock_redis):
            await _handle_previously_seen_rechunk_final_failure(message, result, error)

            mock_redis.connect.assert_not_called()
