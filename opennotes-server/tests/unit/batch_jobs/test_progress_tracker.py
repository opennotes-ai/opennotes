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
    async def test_mark_item_processed_uses_setbit(self, tracker, mock_redis):
        """mark_item_processed uses SETBIT with correct key and offset."""
        job_id = uuid4()
        item_index = 42

        result = await tracker.mark_item_processed(job_id, item_index)

        assert result is True
        mock_redis.setbit.assert_called_once_with(
            f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}",
            item_index,
            1,
        )
        mock_redis.expire.assert_called_with(
            f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}",
            BATCH_JOB_PROCESSED_BITMAP_TTL_SECONDS,
        )

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_true_when_newly_set(self, tracker, mock_redis):
        """mark_item_processed returns True when item was not previously processed."""
        mock_redis.setbit.return_value = 0
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, 0)

        assert result is True

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_false_when_already_set(self, tracker, mock_redis):
        """mark_item_processed returns False when item was already processed."""
        mock_redis.setbit.return_value = 1
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, 0)

        assert result is False

    @pytest.mark.asyncio
    async def test_mark_item_processed_returns_false_on_error(self, tracker, mock_redis):
        """mark_item_processed returns False when Redis operation fails."""
        mock_redis.setbit.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.mark_item_processed(job_id, 0)

        assert result is False

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
    async def test_is_item_processed_returns_false_on_error(self, tracker, mock_redis):
        """is_item_processed returns False when Redis operation fails."""
        mock_redis.getbit.side_effect = Exception("Redis error")
        job_id = uuid4()

        result = await tracker.is_item_processed(job_id, 0)

        assert result is False

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
