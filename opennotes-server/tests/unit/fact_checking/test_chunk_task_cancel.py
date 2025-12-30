"""
Unit tests for rechunk task cancellation and listing functionality.

Task: task-917 - Add cancel/clear endpoint for rechunk tasks

These tests verify:
1. RechunkTaskCancelResponse schema
2. delete_task method in RechunkTaskTracker
3. list_tasks method in RechunkTaskTracker
"""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.fact_checking.chunk_task_schemas import (
    RechunkTaskCancelResponse,
    RechunkTaskStatus,
)
from src.fact_checking.chunk_task_tracker import (
    RECHUNK_TASK_KEY_PREFIX,
    RechunkTaskTracker,
)


class TestRechunkTaskCancelResponseSchema:
    """Tests for RechunkTaskCancelResponse Pydantic schema."""

    def test_cancel_response_schema_valid(self):
        """Valid cancel response schema is accepted."""
        task_id = uuid4()
        response = RechunkTaskCancelResponse(
            task_id=task_id,
            message="Task cancelled successfully",
            lock_released=True,
        )

        assert response.task_id == task_id
        assert response.message == "Task cancelled successfully"
        assert response.lock_released is True

    def test_cancel_response_with_lock_not_released(self):
        """Cancel response with lock_released=False is valid."""
        task_id = uuid4()
        response = RechunkTaskCancelResponse(
            task_id=task_id,
            message="Task cancelled, lock was already released",
            lock_released=False,
        )

        assert response.lock_released is False


class TestRechunkTaskTrackerDeleteTask:
    """Tests for RechunkTaskTracker.delete_task method."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a tracker with mock Redis."""
        return RechunkTaskTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_delete_task_success(self, tracker, mock_redis):
        """Delete task removes the task from Redis."""
        task_id = uuid4()

        result = await tracker.delete_task(task_id)

        assert result is True
        expected_key = f"{RECHUNK_TASK_KEY_PREFIX}{task_id}"
        mock_redis.delete.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, tracker, mock_redis):
        """Delete task returns False when task doesn't exist."""
        mock_redis.delete.return_value = 0
        task_id = uuid4()

        result = await tracker.delete_task(task_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_task_handles_redis_error(self, tracker, mock_redis):
        """Delete task handles Redis errors gracefully."""
        mock_redis.delete.side_effect = Exception("Redis connection error")
        task_id = uuid4()

        result = await tracker.delete_task(task_id)

        assert result is False


class TestRechunkTaskTrackerListTasks:
    """Tests for RechunkTaskTracker.list_tasks method."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client with scan support."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.scan = AsyncMock()
        redis.mget = AsyncMock(return_value=[])
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a tracker with mock Redis."""
        return RechunkTaskTracker(mock_redis)

    def _create_task_json(
        self,
        task_id=None,
        task_type="fact_check",
        status="in_progress",
        community_server_id=None,
    ):
        """Helper to create task JSON data."""
        if task_id is None:
            task_id = uuid4()
        return json.dumps(
            {
                "task_id": str(task_id),
                "task_type": task_type,
                "community_server_id": str(community_server_id) if community_server_id else None,
                "batch_size": 100,
                "status": status,
                "processed_count": 25,
                "total_count": 50,
                "error": None,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        )

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, tracker, mock_redis):
        """List tasks returns empty list when no tasks exist."""

        async def mock_scan_iter(*args, **kwargs):
            return
            yield  # Make this an async generator that yields nothing

        mock_redis.scan_iter = mock_scan_iter

        result = await tracker.list_tasks()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_tasks_returns_all_tasks(self, tracker, mock_redis):
        """List tasks returns all tasks in Redis."""
        task_id_1 = uuid4()
        task_id_2 = uuid4()
        key_1 = f"{RECHUNK_TASK_KEY_PREFIX}{task_id_1}"
        key_2 = f"{RECHUNK_TASK_KEY_PREFIX}{task_id_2}"

        async def mock_scan_iter(*args, **kwargs):
            yield key_1
            yield key_2

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = [
            self._create_task_json(task_id_1, status="in_progress"),
            self._create_task_json(task_id_2, status="pending"),
        ]

        result = await tracker.list_tasks()

        assert len(result) == 2
        task_ids = {task.task_id for task in result}
        assert task_id_1 in task_ids
        assert task_id_2 in task_ids

    @pytest.mark.asyncio
    async def test_list_tasks_filters_by_status(self, tracker, mock_redis):
        """List tasks filters by status when provided."""
        task_id_1 = uuid4()
        task_id_2 = uuid4()
        key_1 = f"{RECHUNK_TASK_KEY_PREFIX}{task_id_1}"
        key_2 = f"{RECHUNK_TASK_KEY_PREFIX}{task_id_2}"

        async def mock_scan_iter(*args, **kwargs):
            yield key_1
            yield key_2

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = [
            self._create_task_json(task_id_1, status="in_progress"),
            self._create_task_json(task_id_2, status="pending"),
        ]

        result = await tracker.list_tasks(status=RechunkTaskStatus.IN_PROGRESS)

        assert len(result) == 1
        assert result[0].task_id == task_id_1
        assert result[0].status == RechunkTaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_list_tasks_handles_redis_error(self, tracker, mock_redis):
        """List tasks returns empty list on Redis error."""

        async def mock_scan_iter(*args, **kwargs):
            raise Exception("Redis connection error")
            yield  # Make it an async generator

        mock_redis.scan_iter = mock_scan_iter

        result = await tracker.list_tasks()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_tasks_skips_malformed_data(self, tracker, mock_redis):
        """List tasks skips tasks with malformed data."""
        task_id_1 = uuid4()
        key_1 = f"{RECHUNK_TASK_KEY_PREFIX}{task_id_1}"
        key_2 = f"{RECHUNK_TASK_KEY_PREFIX}{uuid4()}"

        async def mock_scan_iter(*args, **kwargs):
            yield key_1
            yield key_2

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = [
            self._create_task_json(task_id_1, status="in_progress"),
            "invalid json{{{",  # Malformed data
        ]

        result = await tracker.list_tasks()

        assert len(result) == 1
        assert result[0].task_id == task_id_1
