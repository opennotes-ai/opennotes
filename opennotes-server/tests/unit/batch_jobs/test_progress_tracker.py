"""
Unit tests for BatchJobProgressTracker.

Tests Redis-based real-time progress tracking for batch jobs, ensuring
equivalent coverage to the deleted chunk_task_tracker tests.

Task: task-986.10 - Restore deleted test coverage
"""

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.batch_jobs.progress_tracker import (
    BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX,
    BATCH_JOB_PROCESSED_BITMAP_TTL_SECONDS,
    BATCH_JOB_PROGRESS_KEY_PREFIX,
    BATCH_JOB_PROGRESS_TTL_SECONDS,
    BatchJobProgressData,
    BatchJobProgressTracker,
    MarkItemResult,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client with hash and bitmap operations."""
    redis = MagicMock()
    redis.hset = AsyncMock(return_value=True)
    redis.hgetall = AsyncMock(return_value=None)
    redis.hincrby = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.setbit = AsyncMock(return_value=0)
    redis.getbit = AsyncMock(return_value=0)
    redis.bitcount = AsyncMock(return_value=0)

    mock_pipeline = MagicMock()
    mock_pipeline.setbit = MagicMock(return_value=mock_pipeline)
    mock_pipeline.expire = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(return_value=[0, True])
    redis.pipeline = MagicMock(return_value=mock_pipeline)

    return redis


@pytest.fixture
def tracker(mock_redis):
    """Create a BatchJobProgressTracker with mocked Redis."""
    return BatchJobProgressTracker(mock_redis)


@pytest.mark.unit
class TestBatchJobProgressData:
    """Tests for BatchJobProgressData dataclass."""

    def test_to_hash_serializes_all_fields(self):
        """to_hash includes all fields with correct types."""
        job_id = uuid4()
        start_time = time.time()
        update_time = start_time + 10

        data = BatchJobProgressData(
            job_id=job_id,
            processed_count=50,
            error_count=5,
            current_item="item_123",
            started_at=start_time,
            last_update_at=update_time,
        )

        result = data.to_hash()

        assert result["job_id"] == str(job_id)
        assert result["processed_count"] == 50
        assert result["error_count"] == 5
        assert result["current_item"] == "item_123"
        assert result["started_at"] == start_time
        assert result["last_update_at"] == update_time

    def test_to_hash_excludes_none_current_item(self):
        """to_hash excludes current_item when None."""
        job_id = uuid4()
        data = BatchJobProgressData(
            job_id=job_id,
            current_item=None,
        )

        result = data.to_hash()

        assert "current_item" not in result
        assert result["job_id"] == str(job_id)

    def test_from_hash_parses_valid_data(self):
        """from_hash correctly parses valid dictionary."""
        job_id = uuid4()
        data = {
            "job_id": str(job_id),
            "processed_count": "100",
            "error_count": "10",
            "current_item": "item_456",
            "started_at": "1000.0",
            "last_update_at": "1100.0",
        }

        result = BatchJobProgressData.from_hash(data)

        assert result.job_id == job_id
        assert result.processed_count == 100
        assert result.error_count == 10
        assert result.current_item == "item_456"
        assert result.started_at == 1000.0
        assert result.last_update_at == 1100.0

    def test_from_hash_handles_valid_uuid(self):
        """from_hash correctly handles valid UUID strings (null-safety regression)."""
        job_id = uuid4()
        data = {"job_id": str(job_id)}

        result = BatchJobProgressData.from_hash(data)

        assert isinstance(result.job_id, UUID)
        assert result.job_id == job_id

    def test_from_hash_uses_defaults_for_missing_fields(self):
        """from_hash uses sensible defaults for missing optional fields."""
        job_id = uuid4()
        data = {"job_id": str(job_id)}

        result = BatchJobProgressData.from_hash(data)

        assert result.processed_count == 0
        assert result.error_count == 0
        assert result.current_item is None
        assert result.started_at > 0
        assert result.last_update_at > 0

    def test_rate_calculation(self):
        """rate property calculates items per second."""
        start_time = time.time() - 10
        data = BatchJobProgressData(
            job_id=uuid4(),
            processed_count=100,
            started_at=start_time,
            last_update_at=time.time(),
        )

        rate = data.rate
        assert rate == pytest.approx(10.0, rel=0.1)

    def test_rate_returns_zero_when_no_elapsed_time(self):
        """rate returns 0 when no time has elapsed."""
        now = time.time()
        data = BatchJobProgressData(
            job_id=uuid4(),
            processed_count=100,
            started_at=now,
            last_update_at=now,
        )

        assert data.rate == 0.0


@pytest.mark.unit
class TestBatchJobProgressTracker:
    """Tests for BatchJobProgressTracker methods."""

    @pytest.mark.asyncio
    async def test_start_tracking_creates_progress_data(self, tracker, mock_redis):
        """start_tracking creates new progress data in Redis hash."""
        job_id = uuid4()

        result = await tracker.start_tracking(job_id, current_item="first_item")

        assert result is True
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        key = call_args[0][0]
        data = call_args[0][1]

        assert key == f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}"
        assert data["job_id"] == str(job_id)
        assert data["current_item"] == "first_item"
        assert data["processed_count"] == 0
        assert data["error_count"] == 0

        mock_redis.expire.assert_called_once_with(
            f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}",
            BATCH_JOB_PROGRESS_TTL_SECONDS,
        )

    @pytest.mark.asyncio
    async def test_start_tracking_returns_false_on_error(self, tracker, mock_redis):
        """start_tracking returns False when Redis operation fails."""
        mock_redis.hset.side_effect = Exception("Redis connection error")
        job_id = uuid4()

        result = await tracker.start_tracking(job_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_progress_returns_none_when_not_found(self, tracker, mock_redis):
        """get_progress returns None for non-existent job."""
        mock_redis.hgetall.return_value = {}
        job_id = uuid4()

        result = await tracker.get_progress(job_id)

        assert result is None
        mock_redis.hgetall.assert_called_once_with(f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}")

    @pytest.mark.asyncio
    async def test_get_progress_returns_none_when_no_job_id(self, tracker, mock_redis):
        """get_progress returns None when hash exists but has no job_id."""
        mock_redis.hgetall.return_value = {"processed_count": "10"}
        job_id = uuid4()

        result = await tracker.get_progress(job_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_progress_returns_data_when_found(self, tracker, mock_redis):
        """get_progress returns progress data for existing job."""
        job_id = uuid4()
        stored_data = {
            "job_id": str(job_id),
            "processed_count": "50",
            "error_count": "5",
            "current_item": "item_50",
            "started_at": "1000.0",
            "last_update_at": "1050.0",
        }
        mock_redis.hgetall.return_value = stored_data

        result = await tracker.get_progress(job_id)

        assert result is not None
        assert result.job_id == job_id
        assert result.processed_count == 50
        assert result.error_count == 5
        assert result.current_item == "item_50"

    @pytest.mark.asyncio
    async def test_update_progress_uses_hincrby_for_increments(self, tracker, mock_redis):
        """update_progress uses atomic HINCRBY for increment operations."""
        job_id = uuid4()
        stored_data = {
            "job_id": str(job_id),
            "processed_count": "10",
            "error_count": "2",
            "started_at": "1000.0",
            "last_update_at": "1050.0",
        }
        mock_redis.hgetall.return_value = stored_data

        await tracker.update_progress(job_id, increment_processed=True, increment_errors=True)

        assert mock_redis.hincrby.call_count == 2
        calls = mock_redis.hincrby.call_args_list
        key = f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}"
        assert calls[0][0] == (key, "processed_count", 1)
        assert calls[1][0] == (key, "error_count", 1)

    @pytest.mark.asyncio
    async def test_update_progress_sets_absolute_counts(self, tracker, mock_redis):
        """update_progress with absolute values uses hset."""
        job_id = uuid4()
        stored_data = {
            "job_id": str(job_id),
            "processed_count": "100",
            "error_count": "5",
            "current_item": "item_100",
            "started_at": "1000.0",
            "last_update_at": "1050.0",
        }
        mock_redis.hgetall.return_value = stored_data

        result = await tracker.update_progress(
            job_id, processed_count=100, error_count=5, current_item="item_100"
        )

        assert result is not None
        mock_redis.hset.assert_called()
        call_args = mock_redis.hset.call_args
        updates = call_args[0][1]
        assert updates["processed_count"] == 100
        assert updates["error_count"] == 5
        assert updates["current_item"] == "item_100"
        assert "last_update_at" in updates

    @pytest.mark.asyncio
    async def test_update_progress_returns_none_on_error(self, tracker, mock_redis):
        """update_progress returns None when Redis operation fails."""
        mock_redis.hset.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.update_progress(job_id, processed_count=10)

        assert result is None

    @pytest.mark.asyncio
    async def test_stop_tracking_removes_data(self, tracker, mock_redis):
        """stop_tracking deletes progress data from Redis."""
        job_id = uuid4()
        mock_redis.delete.return_value = 1

        result = await tracker.stop_tracking(job_id)

        assert result is True
        mock_redis.delete.assert_called_once_with(f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}")

    @pytest.mark.asyncio
    async def test_stop_tracking_returns_false_when_not_found(self, tracker, mock_redis):
        """stop_tracking returns False when job progress not found."""
        mock_redis.delete.return_value = 0
        job_id = uuid4()

        result = await tracker.stop_tracking(job_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_stop_tracking_returns_false_on_error(self, tracker, mock_redis):
        """stop_tracking returns False when Redis operation fails."""
        mock_redis.delete.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.stop_tracking(job_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_progress_key_format(self, tracker):
        """_progress_key generates correct Redis key format."""
        job_id = uuid4()

        key = tracker._progress_key(job_id)

        assert key == f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}"
        assert key.startswith("batch_job:progress:")


@pytest.mark.unit
class TestBatchJobProgressTrackerBitmapOperations:
    """Tests for bitmap-based idempotent processing methods."""

    @pytest.mark.asyncio
    async def test_mark_item_processed_uses_pipeline_for_atomicity(self, tracker, mock_redis):
        """mark_item_processed uses pipeline for atomic SETBIT+EXPIRE (TASK-1042.03)."""
        job_id = uuid4()
        item_index = 42

        result = await tracker.mark_item_processed(job_id, item_index)

        assert result == MarkItemResult.NEWLY_MARKED
        mock_redis.pipeline.assert_called_once()
        mock_pipeline = mock_redis.pipeline.return_value
        mock_pipeline.setbit.assert_called_once_with(
            f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}",
            item_index,
            1,
        )
        mock_pipeline.expire.assert_called_once_with(
            f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}",
            BATCH_JOB_PROCESSED_BITMAP_TTL_SECONDS,
        )
        mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_newly_marked_when_first_set(
        self, tracker, mock_redis
    ):
        """mark_item_processed returns NEWLY_MARKED when item was not previously processed."""
        mock_redis.pipeline.return_value.execute = AsyncMock(return_value=[0, True])
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, 0)

        assert result == MarkItemResult.NEWLY_MARKED

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_already_processed_when_set(
        self, tracker, mock_redis
    ):
        """mark_item_processed returns ALREADY_PROCESSED when item was already marked."""
        mock_redis.pipeline.return_value.execute = AsyncMock(return_value=[1, True])
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, 0)

        assert result == MarkItemResult.ALREADY_PROCESSED

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_error_on_exception(self, tracker, mock_redis):
        """mark_item_processed returns ERROR when Redis operation fails (TASK-1042.05)."""
        mock_redis.pipeline.return_value.execute.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, 0)

        assert result == MarkItemResult.ERROR

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_error_for_negative_index(self, tracker, mock_redis):
        """mark_item_processed returns ERROR for negative item_index."""
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, -1)

        assert result == MarkItemResult.ERROR
        mock_redis.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_is_item_processed_uses_getbit(self, tracker, mock_redis):
        """is_item_processed uses GETBIT with correct key and offset."""
        job_id = uuid4()
        item_index = 42

        await tracker.is_item_processed(job_id, item_index)

        mock_redis.getbit.assert_called_once_with(
            f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}",
            item_index,
        )

    @pytest.mark.asyncio
    async def test_is_item_processed_returns_true_when_bit_is_set(self, tracker, mock_redis):
        """is_item_processed returns True when bit is 1."""
        mock_redis.getbit.return_value = 1
        job_id = uuid4()

        result = await tracker.is_item_processed(job_id, 0)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_item_processed_returns_false_when_bit_is_unset(self, tracker, mock_redis):
        """is_item_processed returns False when bit is 0."""
        mock_redis.getbit.return_value = 0
        job_id = uuid4()

        result = await tracker.is_item_processed(job_id, 0)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_item_processed_returns_none_on_error(self, tracker, mock_redis):
        """is_item_processed returns None on Redis error (TASK-1042.06)."""
        mock_redis.getbit.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.is_item_processed(job_id, 0)

        assert result is None

    @pytest.mark.asyncio
    async def test_is_item_processed_returns_none_for_negative_index(self, tracker, mock_redis):
        """is_item_processed returns None for negative item_index."""
        job_id = uuid4()

        result = await tracker.is_item_processed(job_id, -1)

        assert result is None
        mock_redis.getbit.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_processed_bitmap_deletes_key(self, tracker, mock_redis):
        """clear_processed_bitmap deletes the bitmap key."""
        job_id = uuid4()
        mock_redis.delete.return_value = 1

        result = await tracker.clear_processed_bitmap(job_id)

        assert result is True
        mock_redis.delete.assert_called_with(
            f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}",
        )

    @pytest.mark.asyncio
    async def test_clear_processed_bitmap_returns_false_when_not_found(self, tracker, mock_redis):
        """clear_processed_bitmap returns False when key doesn't exist."""
        mock_redis.delete.return_value = 0
        job_id = uuid4()

        result = await tracker.clear_processed_bitmap(job_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_clear_processed_bitmap_returns_false_on_error(self, tracker, mock_redis):
        """clear_processed_bitmap returns False when Redis operation fails."""
        mock_redis.delete.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.clear_processed_bitmap(job_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_processed_bitmap_key_format(self, tracker):
        """_processed_bitmap_key generates correct Redis key format."""
        job_id = uuid4()

        key = tracker._processed_bitmap_key(job_id)

        assert key == f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}"
        assert key.startswith("batch_job:processed:")


@pytest.mark.unit
class TestBitmapIntegrationWithProcessingLoop:
    """
    Integration tests for bitmap operations in the context of batch job processing loops.

    These tests verify the full bitmap workflow as it would be used by rechunk tasks,
    ensuring items are correctly skipped, indices increment properly, and cleanup
    happens after job completion.

    Addresses: TASK-1042.04
    """

    @pytest.fixture
    def processing_mock_redis(self):
        """Create mock Redis with stateful bitmap tracking for integration tests."""
        redis = MagicMock()
        processed_items: dict[str, set[int]] = {}
        pending_ops: list[tuple[str, str, tuple]] = []

        def mock_setbit_enqueue(key: str, offset: int, value: int):
            pending_ops.append(("setbit", key, (offset, value)))
            return MagicMock()

        def mock_expire_enqueue(key: str, ttl: int):
            pending_ops.append(("expire", key, (ttl,)))
            return MagicMock()

        async def mock_execute():
            results = []
            for op_type, key, args in pending_ops:
                if op_type == "setbit":
                    offset, value = args
                    if key not in processed_items:
                        processed_items[key] = set()
                    was_set = offset in processed_items[key]
                    if value == 1:
                        processed_items[key].add(offset)
                    else:
                        processed_items[key].discard(offset)
                    results.append(1 if was_set else 0)
                elif op_type == "expire":
                    results.append(True)
            pending_ops.clear()
            return results

        def mock_pipeline():
            pending_ops.clear()
            pipe = MagicMock()
            pipe.setbit = MagicMock(side_effect=mock_setbit_enqueue)
            pipe.expire = MagicMock(side_effect=mock_expire_enqueue)
            pipe.execute = AsyncMock(side_effect=mock_execute)
            return pipe

        async def mock_getbit(key: str, offset: int) -> int:
            if key not in processed_items:
                return 0
            return 1 if offset in processed_items[key] else 0

        async def mock_delete(key: str) -> int:
            if key in processed_items:
                del processed_items[key]
                return 1
            return 0

        async def mock_bitcount(key: str, start: int | None = None, end: int | None = None) -> int:
            if key not in processed_items:
                return 0
            return len(processed_items[key])

        redis.pipeline = MagicMock(side_effect=mock_pipeline)
        redis.getbit = AsyncMock(side_effect=mock_getbit)
        redis.delete = AsyncMock(side_effect=mock_delete)
        redis.bitcount = AsyncMock(side_effect=mock_bitcount)
        redis.expire = AsyncMock(return_value=True)
        redis.hset = AsyncMock(return_value=True)
        redis.hincrby = AsyncMock(return_value=1)
        redis.hgetall = AsyncMock(return_value=None)
        redis._processed_items = processed_items
        return redis

    @pytest.fixture
    def stateful_tracker(self, processing_mock_redis):
        """Create tracker with stateful mock Redis for integration tests."""
        return BatchJobProgressTracker(processing_mock_redis)

    @pytest.mark.asyncio
    async def test_items_skipped_when_already_processed(
        self, stateful_tracker, processing_mock_redis
    ):
        """Items marked as processed are correctly identified and skipped on restart."""
        job_id = uuid4()
        items = ["item_0", "item_1", "item_2", "item_3", "item_4"]
        processed_on_first_run = []
        processed_on_second_run = []

        for idx, item in enumerate(items[:3]):
            if not await stateful_tracker.is_item_processed(job_id, idx):
                await stateful_tracker.mark_item_processed(job_id, idx)
                processed_on_first_run.append(item)

        for idx, item in enumerate(items):
            if not await stateful_tracker.is_item_processed(job_id, idx):
                await stateful_tracker.mark_item_processed(job_id, idx)
                processed_on_second_run.append(item)

        assert processed_on_first_run == ["item_0", "item_1", "item_2"]
        assert processed_on_second_run == ["item_3", "item_4"]
        assert len(processed_on_first_run) + len(processed_on_second_run) == len(items)

    @pytest.mark.asyncio
    async def test_item_index_increments_correctly_with_skips(
        self, stateful_tracker, processing_mock_redis
    ):
        """item_index correctly tracks position including skipped items."""
        job_id = uuid4()
        items = list(range(10))
        pre_processed_indices = {2, 5, 7}
        expected_process_order = []
        actual_process_order = []

        for idx in pre_processed_indices:
            await stateful_tracker.mark_item_processed(job_id, idx)

        for idx in items:
            if idx not in pre_processed_indices:
                expected_process_order.append(idx)

        for item_index, _item in enumerate(items):
            was_already_processed = await stateful_tracker.is_item_processed(job_id, item_index)
            if was_already_processed:
                continue
            result = await stateful_tracker.mark_item_processed(job_id, item_index)
            assert result == MarkItemResult.NEWLY_MARKED
            actual_process_order.append(item_index)

        assert actual_process_order == expected_process_order
        assert len(actual_process_order) == len(items) - len(pre_processed_indices)

    @pytest.mark.asyncio
    async def test_clear_processed_bitmap_after_job_completion(
        self, stateful_tracker, processing_mock_redis
    ):
        """clear_processed_bitmap correctly cleans up after job completion."""
        job_id = uuid4()
        items = list(range(5))

        for idx in items:
            await stateful_tracker.mark_item_processed(job_id, idx)

        for idx in items:
            assert await stateful_tracker.is_item_processed(job_id, idx) is True

        result = await stateful_tracker.clear_processed_bitmap(job_id)
        assert result is True

        for idx in items:
            assert await stateful_tracker.is_item_processed(job_id, idx) is False

    @pytest.mark.asyncio
    async def test_is_item_processed_returns_none_on_redis_error(
        self, stateful_tracker, processing_mock_redis
    ):
        """is_item_processed returns None on Redis error (TASK-1042.06).

        Callers MUST handle None as 'unknown state' and NOT assume item is unprocessed.
        This test verifies the return value is None, not False.
        """
        job_id = uuid4()
        original_getbit = processing_mock_redis.getbit.side_effect

        async def failing_getbit(key: str, offset: int) -> int:
            if offset == 2:
                raise Exception("Redis connection error")
            return await original_getbit(key, offset)

        processing_mock_redis.getbit.side_effect = failing_getbit

        assert await stateful_tracker.is_item_processed(job_id, 0) is False
        assert await stateful_tracker.is_item_processed(job_id, 2) is None
        assert await stateful_tracker.is_item_processed(job_id, 3) is False

    @pytest.mark.asyncio
    async def test_processing_loop_handles_none_from_is_item_processed(
        self, stateful_tracker, processing_mock_redis
    ):
        """Processing loop must handle None from is_item_processed correctly.

        When is_item_processed returns None (Redis error), the caller should
        NOT process the item (to avoid duplicate processing with side effects).
        """
        job_id = uuid4()
        items = list(range(5))
        processed_items = []
        skipped_due_to_error = []
        original_getbit = processing_mock_redis.getbit.side_effect

        async def failing_getbit(key: str, offset: int) -> int:
            if offset == 2:
                raise Exception("Redis connection error")
            return await original_getbit(key, offset)

        processing_mock_redis.getbit.side_effect = failing_getbit

        for idx, item in enumerate(items):
            is_processed = await stateful_tracker.is_item_processed(job_id, idx)
            if is_processed is None:
                skipped_due_to_error.append(item)
                continue
            if not is_processed:
                result = await stateful_tracker.mark_item_processed(job_id, idx)
                if result == MarkItemResult.NEWLY_MARKED:
                    processed_items.append(item)

        assert len(processed_items) == 4
        assert 2 not in processed_items
        assert skipped_due_to_error == [2]

    @pytest.mark.asyncio
    async def test_full_job_lifecycle_with_interrupt_and_resume(
        self, stateful_tracker, processing_mock_redis
    ):
        """Test complete job lifecycle: start, interrupt, resume, complete."""
        job_id = uuid4()
        total_items = 10
        interrupt_at = 4
        all_processed = []

        for idx in range(interrupt_at):
            await stateful_tracker.mark_item_processed(job_id, idx)
            all_processed.append(idx)

        for idx in range(total_items):
            is_processed = await stateful_tracker.is_item_processed(job_id, idx)
            if not is_processed:
                await stateful_tracker.mark_item_processed(job_id, idx)
                all_processed.append(idx)

        assert len(all_processed) == total_items
        assert sorted(all_processed) == list(range(total_items))

        cleared = await stateful_tracker.clear_processed_bitmap(job_id)
        assert cleared is True

        for idx in range(total_items):
            assert await stateful_tracker.is_item_processed(job_id, idx) is False


@pytest.mark.unit
class TestConcurrentBitmapAccess:
    """
    Tests for concurrent access to bitmap operations.

    These tests verify behavior when multiple workers access the same bitmap
    concurrently, including race condition detection and rapid consecutive operations.

    Addresses: TASK-1042.12
    """

    @pytest.fixture
    def concurrent_mock_redis(self):
        """Create mock Redis that simulates concurrent access patterns with pipeline."""
        import threading

        redis = MagicMock()
        bitmap_state: dict[str, dict[int, int]] = {}
        pipeline_calls: list[tuple[str, str, tuple, float]] = []
        lock = threading.Lock()

        def create_pipeline():
            pending_ops: list[tuple[str, str, tuple]] = []

            def mock_setbit_enqueue(key: str, offset: int, value: int):
                pending_ops.append(("setbit", key, (offset, value)))
                return MagicMock()

            def mock_expire_enqueue(key: str, ttl: int):
                pending_ops.append(("expire", key, (ttl,)))
                return MagicMock()

            async def mock_execute():
                results = []
                with lock:
                    for op_type, key, args in pending_ops:
                        pipeline_calls.append((op_type, key, args, time.time()))
                        if op_type == "setbit":
                            offset, value = args
                            if key not in bitmap_state:
                                bitmap_state[key] = {}
                            original = bitmap_state[key].get(offset, 0)
                            bitmap_state[key][offset] = value
                            results.append(original)
                        elif op_type == "expire":
                            results.append(True)
                pending_ops.clear()
                return results

            pipe = MagicMock()
            pipe.setbit = MagicMock(side_effect=mock_setbit_enqueue)
            pipe.expire = MagicMock(side_effect=mock_expire_enqueue)
            pipe.execute = AsyncMock(side_effect=mock_execute)
            return pipe

        async def mock_getbit(key: str, offset: int) -> int:
            with lock:
                if key not in bitmap_state:
                    return 0
                return bitmap_state[key].get(offset, 0)

        async def mock_delete(key: str) -> int:
            with lock:
                if key in bitmap_state:
                    del bitmap_state[key]
                    return 1
                return 0

        redis.pipeline = MagicMock(side_effect=create_pipeline)
        redis.getbit = AsyncMock(side_effect=mock_getbit)
        redis.delete = AsyncMock(side_effect=mock_delete)
        redis.hset = AsyncMock(return_value=True)
        redis.hincrby = AsyncMock(return_value=1)
        redis.hgetall = AsyncMock(return_value=None)
        redis._bitmap_state = bitmap_state
        redis._pipeline_calls = pipeline_calls
        return redis

    @pytest.fixture
    def concurrent_tracker(self, concurrent_mock_redis):
        """Create tracker with concurrent-aware mock Redis."""
        return BatchJobProgressTracker(concurrent_mock_redis)

    @pytest.mark.asyncio
    async def test_concurrent_marking_same_item_multiple_workers(
        self, concurrent_tracker, concurrent_mock_redis
    ):
        """Multiple workers marking the same item concurrently - only one should succeed as 'new'."""
        import asyncio

        job_id = uuid4()
        item_index = 42
        num_workers = 5
        results: list[MarkItemResult] = []

        async def worker_mark():
            result = await concurrent_tracker.mark_item_processed(job_id, item_index)
            results.append(result)

        await asyncio.gather(*[worker_mark() for _ in range(num_workers)])

        newly_marked_count = sum(1 for r in results if r == MarkItemResult.NEWLY_MARKED)
        already_processed_count = sum(1 for r in results if r == MarkItemResult.ALREADY_PROCESSED)

        assert newly_marked_count == 1
        assert already_processed_count == num_workers - 1

        assert await concurrent_tracker.is_item_processed(job_id, item_index) is True

    @pytest.mark.asyncio
    async def test_rapid_consecutive_marking_different_items(
        self, concurrent_tracker, concurrent_mock_redis
    ):
        """Rapid consecutive marking of different items maintains correctness."""
        import asyncio

        job_id = uuid4()
        num_items = 100

        async def mark_item(idx: int):
            return await concurrent_tracker.mark_item_processed(job_id, idx)

        results = await asyncio.gather(*[mark_item(i) for i in range(num_items)])

        assert all(r == MarkItemResult.NEWLY_MARKED for r in results)

        for idx in range(num_items):
            assert await concurrent_tracker.is_item_processed(job_id, idx) is True

        setbit_calls = [c for c in concurrent_mock_redis._pipeline_calls if c[0] == "setbit"]
        assert len(setbit_calls) == num_items

    @pytest.mark.asyncio
    async def test_setbit_expire_atomic_via_pipeline(self, concurrent_mock_redis):
        """
        Test that SETBIT and EXPIRE are executed atomically via pipeline (TASK-1042.03).

        This test verifies that each mark_item_processed call uses a pipeline
        that executes both SETBIT and EXPIRE atomically, preventing the race
        condition where a key could expire between SETBIT and EXPIRE.
        """
        job_id = uuid4()
        tracker = BatchJobProgressTracker(concurrent_mock_redis)

        for idx in range(10):
            await tracker.mark_item_processed(job_id, idx)

        pipeline_calls = concurrent_mock_redis._pipeline_calls
        setbit_calls = [c for c in pipeline_calls if c[0] == "setbit"]
        expire_calls = [c for c in pipeline_calls if c[0] == "expire"]

        assert len(setbit_calls) == 10
        assert len(expire_calls) == 10

        for i in range(10):
            setbit_idx = i * 2
            expire_idx = i * 2 + 1
            setbit_key = pipeline_calls[setbit_idx][1]
            expire_key = pipeline_calls[expire_idx][1]
            assert setbit_key == expire_key

    @pytest.mark.asyncio
    async def test_pipeline_failure_returns_error(self, concurrent_mock_redis):
        """
        Test that pipeline execution failure returns MarkItemResult.ERROR.
        """
        job_id = uuid4()

        def failing_pipeline():
            pipe = MagicMock()
            pipe.setbit = MagicMock(return_value=pipe)
            pipe.expire = MagicMock(return_value=pipe)
            pipe.execute = AsyncMock(side_effect=Exception("Pipeline execution failed"))
            return pipe

        concurrent_mock_redis.pipeline = MagicMock(side_effect=failing_pipeline)
        tracker = BatchJobProgressTracker(concurrent_mock_redis)

        result = await tracker.mark_item_processed(job_id, 0)

        assert result == MarkItemResult.ERROR

    @pytest.mark.asyncio
    async def test_concurrent_workers_different_jobs(
        self, concurrent_tracker, concurrent_mock_redis
    ):
        """Multiple workers processing different jobs should not interfere."""
        import asyncio

        num_jobs = 5
        items_per_job = 10
        job_ids = [uuid4() for _ in range(num_jobs)]

        async def process_job(job_id: UUID, job_num: int):
            for idx in range(items_per_job):
                result = await concurrent_tracker.mark_item_processed(job_id, idx)
                assert result == MarkItemResult.NEWLY_MARKED

        await asyncio.gather(
            *[process_job(job_id, job_num) for job_num, job_id in enumerate(job_ids)]
        )

        for job_id in job_ids:
            for idx in range(items_per_job):
                assert await concurrent_tracker.is_item_processed(job_id, idx) is True

        setbit_calls = [c for c in concurrent_mock_redis._pipeline_calls if c[0] == "setbit"]
        assert len(setbit_calls) == num_jobs * items_per_job

    @pytest.mark.asyncio
    async def test_interleaved_mark_and_check_operations(
        self, concurrent_tracker, concurrent_mock_redis
    ):
        """Interleaved mark and check operations from multiple workers maintain consistency."""
        import asyncio

        job_id = uuid4()
        num_items = 50
        operations_log: list[tuple[str, int, MarkItemResult | bool | None]] = []

        async def mark_then_check(idx: int):
            mark_result = await concurrent_tracker.mark_item_processed(job_id, idx)
            operations_log.append(("mark", idx, mark_result))
            check_result = await concurrent_tracker.is_item_processed(job_id, idx)
            operations_log.append(("check", idx, check_result))
            return mark_result, check_result

        results = await asyncio.gather(*[mark_then_check(i) for i in range(num_items)])

        for _mark_result, check_result in results:
            assert check_result is True

        check_operations = [op for op in operations_log if op[0] == "check"]
        assert all(op[2] is True for op in check_operations)


@pytest.mark.unit
class TestResumeHelperMethods:
    """
    Tests for resume logic helper methods (TASK-1042.02).

    These tests verify that the helper methods for proper resume work correctly,
    preventing data loss from offset-resume mechanism bugs.
    """

    @pytest.fixture
    def resume_mock_redis(self):
        """Create mock Redis with stateful bitmap tracking for resume tests."""
        redis = MagicMock()
        processed_items: dict[str, set[int]] = {}
        pending_ops: list[tuple[str, str, tuple]] = []

        def mock_setbit_enqueue(key: str, offset: int, value: int):
            pending_ops.append(("setbit", key, (offset, value)))
            return MagicMock()

        def mock_expire_enqueue(key: str, ttl: int):
            pending_ops.append(("expire", key, (ttl,)))
            return MagicMock()

        async def mock_execute():
            results = []
            for op_type, key, args in pending_ops:
                if op_type == "setbit":
                    offset, value = args
                    if key not in processed_items:
                        processed_items[key] = set()
                    was_set = offset in processed_items[key]
                    if value == 1:
                        processed_items[key].add(offset)
                    else:
                        processed_items[key].discard(offset)
                    results.append(1 if was_set else 0)
                elif op_type == "expire":
                    results.append(True)
            pending_ops.clear()
            return results

        def mock_pipeline():
            pending_ops.clear()
            pipe = MagicMock()
            pipe.setbit = MagicMock(side_effect=mock_setbit_enqueue)
            pipe.expire = MagicMock(side_effect=mock_expire_enqueue)
            pipe.execute = AsyncMock(side_effect=mock_execute)
            return pipe

        async def mock_getbit(key: str, offset: int) -> int:
            if key not in processed_items:
                return 0
            return 1 if offset in processed_items[key] else 0

        async def mock_bitcount(key: str, start: int | None = None, end: int | None = None) -> int:
            if key not in processed_items:
                return 0
            return len(processed_items[key])

        async def mock_delete(key: str) -> int:
            if key in processed_items:
                del processed_items[key]
                return 1
            return 0

        redis.pipeline = MagicMock(side_effect=mock_pipeline)
        redis.getbit = AsyncMock(side_effect=mock_getbit)
        redis.bitcount = AsyncMock(side_effect=mock_bitcount)
        redis.delete = AsyncMock(side_effect=mock_delete)
        redis.expire = AsyncMock(return_value=True)
        redis.hset = AsyncMock(return_value=True)
        redis.hincrby = AsyncMock(return_value=1)
        redis.hgetall = AsyncMock(return_value=None)
        redis._processed_items = processed_items
        return redis

    @pytest.fixture
    def resume_tracker(self, resume_mock_redis):
        """Create tracker for resume tests."""
        return BatchJobProgressTracker(resume_mock_redis)

    @pytest.mark.asyncio
    async def test_get_processed_count_from_bitmap(self, resume_tracker, resume_mock_redis):
        """get_processed_count_from_bitmap returns correct count from bitmap."""
        job_id = uuid4()

        await resume_tracker.mark_item_processed(job_id, 0)
        await resume_tracker.mark_item_processed(job_id, 2)
        await resume_tracker.mark_item_processed(job_id, 5)

        count = await resume_tracker.get_processed_count_from_bitmap(job_id)
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_processed_count_from_bitmap_returns_zero_for_new_job(self, resume_tracker):
        """get_processed_count_from_bitmap returns 0 for job with no processed items."""
        job_id = uuid4()

        count = await resume_tracker.get_processed_count_from_bitmap(job_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_processed_count_from_bitmap_returns_none_on_error(
        self, resume_tracker, resume_mock_redis
    ):
        """get_processed_count_from_bitmap returns None on Redis error."""
        resume_mock_redis.bitcount.side_effect = Exception("Redis error")
        job_id = uuid4()

        count = await resume_tracker.get_processed_count_from_bitmap(job_id)
        assert count is None

    @pytest.mark.asyncio
    async def test_get_unprocessed_indices(self, resume_tracker, resume_mock_redis):
        """get_unprocessed_indices returns correct list of unprocessed items."""
        job_id = uuid4()

        await resume_tracker.mark_item_processed(job_id, 1)
        await resume_tracker.mark_item_processed(job_id, 3)

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, 5)
        assert unprocessed == [0, 2, 4]

    @pytest.mark.asyncio
    async def test_get_unprocessed_indices_all_processed(self, resume_tracker, resume_mock_redis):
        """get_unprocessed_indices returns empty list when all items processed."""
        job_id = uuid4()

        for i in range(5):
            await resume_tracker.mark_item_processed(job_id, i)

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, 5)
        assert unprocessed == []

    @pytest.mark.asyncio
    async def test_get_unprocessed_indices_none_processed(self, resume_tracker):
        """get_unprocessed_indices returns all indices when none processed."""
        job_id = uuid4()

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, 5)
        assert unprocessed == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_get_unprocessed_indices_returns_none_on_error(
        self, resume_tracker, resume_mock_redis
    ):
        """get_unprocessed_indices returns None on Redis error."""
        resume_mock_redis.getbit.side_effect = Exception("Redis error")
        job_id = uuid4()

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, 5)
        assert unprocessed is None

    @pytest.mark.asyncio
    async def test_get_unprocessed_indices_zero_total(self, resume_tracker):
        """get_unprocessed_indices returns empty list for zero total_count."""
        job_id = uuid4()

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, 0)
        assert unprocessed == []

    @pytest.mark.asyncio
    async def test_get_unprocessed_indices_negative_total(self, resume_tracker):
        """get_unprocessed_indices returns empty list for negative total_count."""
        job_id = uuid4()

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, -5)
        assert unprocessed == []

    @pytest.mark.asyncio
    async def test_resume_scenario_failed_items_not_lost(self, resume_tracker, resume_mock_redis):
        """
        Test the data loss scenario described in TASK-1042.02.

        Scenario: Process [item0-fail, item1-ok, item2-fail, item3-ok]
        Old buggy offset logic: processed_count=2 -> offset=2 -> item0 and item2 lost
        Correct bitmap logic: get_unprocessed_indices returns [0, 2] -> retry both
        """
        job_id = uuid4()
        total_items = 4

        await resume_tracker.mark_item_processed(job_id, 1)
        await resume_tracker.mark_item_processed(job_id, 3)

        count = await resume_tracker.get_processed_count_from_bitmap(job_id)
        assert count == 2

        unprocessed = await resume_tracker.get_unprocessed_indices(job_id, total_items)
        assert unprocessed == [0, 2]

        for idx in unprocessed:
            result = await resume_tracker.mark_item_processed(job_id, idx)
            assert result == MarkItemResult.NEWLY_MARKED

        final_unprocessed = await resume_tracker.get_unprocessed_indices(job_id, total_items)
        assert final_unprocessed == []

        final_count = await resume_tracker.get_processed_count_from_bitmap(job_id)
        assert final_count == 4
