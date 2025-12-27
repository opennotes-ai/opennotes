"""
Unit tests for RechunkTaskTracker error handling.

These tests verify:
1. create_task verifies persistence succeeded
2. get_task returns structured error info (not just None)
3. mark_failed handles Redis failures gracefully
4. Background task startup failures are properly recorded

Task: task-893 - Rechunk task failure returns 'not found' instead of error details
"""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.fact_checking.chunk_task_schemas import (
    RechunkTaskCreate,
    RechunkTaskStatus,
    RechunkTaskType,
)
from src.fact_checking.chunk_task_tracker import (
    RechunkTaskTracker,
    TaskLookupError,
    TaskLookupErrorReason,
)


class TestTaskCreationVerification:
    """Tests for verifying task persistence during creation."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a tracker with mock Redis."""
        return RechunkTaskTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_create_task_raises_on_redis_failure(self, tracker, mock_redis):
        """When Redis set fails, create_task should raise an exception."""
        mock_redis.set = AsyncMock(side_effect=Exception("Redis connection lost"))

        task_data = RechunkTaskCreate(
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            total_items=50,
        )

        with pytest.raises(Exception, match="Redis connection lost"):
            await tracker.create_task(task_data)

    @pytest.mark.asyncio
    async def test_create_task_verifies_persistence(self, tracker, mock_redis):
        """create_task should verify the task was actually persisted."""
        # Redis set returns False (write failed silently)
        mock_redis.set = AsyncMock(return_value=False)

        task_data = RechunkTaskCreate(
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            total_items=50,
        )

        with pytest.raises(RuntimeError, match="Failed to persist task"):
            await tracker.create_task(task_data)


class TestTaskLookupErrorHandling:
    """Tests for structured error handling in get_task."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a tracker with mock Redis."""
        return RechunkTaskTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_get_task_or_error_returns_not_found_reason(self, tracker, mock_redis):
        """get_task_or_error returns structured error for missing task."""
        mock_redis.get.return_value = None

        result = await tracker.get_task_or_error(uuid4())

        assert isinstance(result, TaskLookupError)
        assert result.reason == TaskLookupErrorReason.NOT_FOUND
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_get_task_or_error_returns_redis_error_reason(self, tracker, mock_redis):
        """get_task_or_error returns structured error for Redis failures."""
        mock_redis.get = AsyncMock(side_effect=Exception("Connection refused"))

        result = await tracker.get_task_or_error(uuid4())

        assert isinstance(result, TaskLookupError)
        assert result.reason == TaskLookupErrorReason.REDIS_ERROR
        assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_get_task_or_error_returns_parse_error_reason(self, tracker, mock_redis):
        """get_task_or_error returns structured error for corrupted data."""
        mock_redis.get.return_value = "not valid json"

        result = await tracker.get_task_or_error(uuid4())

        assert isinstance(result, TaskLookupError)
        assert result.reason == TaskLookupErrorReason.PARSE_ERROR


class TestMarkFailedErrorHandling:
    """Tests for mark_failed resilience to Redis failures."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a tracker with mock Redis."""
        return RechunkTaskTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_mark_failed_logs_error_when_redis_unavailable(self, tracker, mock_redis):
        """When mark_failed can't persist, it should log the error for recovery."""
        task_id = uuid4()
        # Redis is down - can't get the task
        mock_redis.get = AsyncMock(side_effect=Exception("Redis unavailable"))

        with patch("src.fact_checking.chunk_task_tracker.logger") as mock_logger:
            result = await tracker.mark_failed(task_id, "Original error message", 10)

            # Should return None (couldn't persist)
            assert result is None

            # But should log the failure for recovery
            mock_logger.error.assert_called()
            call_args = str(mock_logger.error.call_args)
            assert str(task_id) in call_args or "Original error message" in call_args

    @pytest.mark.asyncio
    async def test_mark_failed_force_persists_error_when_task_missing(self, tracker, mock_redis):
        """mark_failed should create a failed task record even if task doesn't exist."""
        task_id = uuid4()
        mock_redis.get.return_value = None  # Task not found

        result = await tracker.mark_failed_force(
            task_id=task_id,
            error="Startup failure: Redis connection lost",
            processed_count=0,
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            total_items=50,
        )

        assert result is not None
        assert result.status == RechunkTaskStatus.FAILED
        assert result.error == "Startup failure: Redis connection lost"
        mock_redis.set.assert_called()


class TestTaskStatusEndpointErrorInfo:
    """Tests for improved error information in task status retrieval."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a tracker with mock Redis."""
        return RechunkTaskTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_get_task_with_startup_failure_shows_error(self, tracker, mock_redis):
        """When a task failed during startup, get_task should return the error."""
        task_id = uuid4()
        community_id = uuid4()
        # Task exists but is in FAILED status with error
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": str(community_id),
            "batch_size": 100,
            "status": "failed",
            "processed_count": 0,
            "total_count": 50,
            "error": "Startup failure: Could not connect to Redis in background task",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.get_task(task_id)

        assert result is not None
        assert result.status == RechunkTaskStatus.FAILED
        assert "Startup failure" in result.error
