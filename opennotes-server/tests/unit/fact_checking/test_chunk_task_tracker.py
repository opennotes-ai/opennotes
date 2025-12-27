"""
Unit tests for RechunkTaskTracker and related schemas.

These tests verify:
1. Task creation and storage in Redis
2. Task status updates (pending -> in_progress -> completed/failed)
3. Progress updates during processing
4. Task retrieval by ID
5. TTL expiration behavior
6. Error handling for missing tasks

Task: task-871.19 - Add background task status tracking for rechunk endpoints
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.fact_checking.chunk_task_schemas import (
    RechunkTaskCreate,
    RechunkTaskResponse,
    RechunkTaskStartResponse,
    RechunkTaskStatus,
    RechunkTaskType,
)
from src.fact_checking.chunk_task_tracker import (
    RECHUNK_TASK_KEY_PREFIX,
    RECHUNK_TASK_TTL_SECONDS,
    RechunkTaskTracker,
)


class TestRechunkTaskSchemas:
    """Tests for RechunkTask Pydantic schemas."""

    def test_task_create_schema_valid(self):
        """Valid task create schema is accepted."""
        task = RechunkTaskCreate(
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            total_items=50,
        )

        assert task.task_type == RechunkTaskType.FACT_CHECK
        assert task.batch_size == 100
        assert task.total_items == 50

    def test_task_create_schema_batch_size_limits(self):
        """Batch size must be between 1 and 1000."""
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            RechunkTaskCreate(
                task_type=RechunkTaskType.FACT_CHECK,
                community_server_id=uuid4(),
                batch_size=0,
                total_items=50,
            )

        with pytest.raises(ValueError, match="less than or equal to 1000"):
            RechunkTaskCreate(
                task_type=RechunkTaskType.FACT_CHECK,
                community_server_id=uuid4(),
                batch_size=1001,
                total_items=50,
            )

    def test_task_response_progress_percentage(self):
        """Progress percentage is calculated correctly."""
        task = RechunkTaskResponse(
            task_id=uuid4(),
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            status=RechunkTaskStatus.IN_PROGRESS,
            processed_count=25,
            total_count=100,
            error=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert task.progress_percentage == 25.0

    def test_task_response_progress_percentage_zero_total(self):
        """Progress percentage is 0 when total is 0."""
        task = RechunkTaskResponse(
            task_id=uuid4(),
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=0,
            error=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert task.progress_percentage == 0.0

    def test_task_start_response_schema(self):
        """Task start response contains required fields."""
        response = RechunkTaskStartResponse(
            task_id=uuid4(),
            status=RechunkTaskStatus.PENDING,
            total_items=100,
            batch_size=50,
            message="Starting rechunk",
        )

        assert response.status == RechunkTaskStatus.PENDING
        assert response.total_items == 100
        assert response.batch_size == 50


class TestRechunkTaskTracker:
    """Tests for RechunkTaskTracker service."""

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
    async def test_create_task_returns_response_with_id(self, tracker, mock_redis):
        """Create task returns a response with assigned task ID."""
        task_data = RechunkTaskCreate(
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=uuid4(),
            batch_size=100,
            total_items=50,
        )

        result = await tracker.create_task(task_data)

        assert result.task_id is not None
        assert result.status == RechunkTaskStatus.PENDING
        assert result.total_count == 50
        assert result.processed_count == 0
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_stores_in_redis_with_ttl(self, tracker, mock_redis):
        """Task is stored in Redis with correct key prefix and TTL."""
        task_data = RechunkTaskCreate(
            task_type=RechunkTaskType.PREVIOUSLY_SEEN,
            community_server_id=uuid4(),
            batch_size=50,
            total_items=100,
        )

        result = await tracker.create_task(task_data)

        call_args = mock_redis.set.call_args
        key = call_args.args[0]
        ttl = call_args.kwargs.get("ttl")

        assert key.startswith(RECHUNK_TASK_KEY_PREFIX)
        assert str(result.task_id) in key
        assert ttl == RECHUNK_TASK_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_get_task_returns_none_when_not_found(self, tracker, mock_redis):
        """Get task returns None when task doesn't exist."""
        mock_redis.get.return_value = None

        result = await tracker.get_task(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_returns_deserialized_task(self, tracker, mock_redis):
        """Get task deserializes and returns stored task."""
        import json

        task_id = uuid4()
        community_id = uuid4()
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": str(community_id),
            "batch_size": 100,
            "status": "in_progress",
            "processed_count": 25,
            "total_count": 50,
            "error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.get_task(task_id)

        assert result is not None
        assert result.task_id == task_id
        assert result.status == RechunkTaskStatus.IN_PROGRESS
        assert result.processed_count == 25
        assert result.total_count == 50

    @pytest.mark.asyncio
    async def test_update_status_changes_status(self, tracker, mock_redis):
        """Update status changes the task status."""
        import json

        task_id = uuid4()
        community_id = uuid4()
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": str(community_id),
            "batch_size": 100,
            "status": "pending",
            "processed_count": 0,
            "total_count": 50,
            "error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.update_status(task_id, RechunkTaskStatus.IN_PROGRESS)

        assert result is not None
        assert result.status == RechunkTaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_update_status_returns_none_for_missing_task(self, tracker, mock_redis):
        """Update status returns None when task doesn't exist."""
        mock_redis.get.return_value = None

        result = await tracker.update_status(uuid4(), RechunkTaskStatus.IN_PROGRESS)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_progress_updates_count(self, tracker, mock_redis):
        """Update progress updates the processed count."""
        import json

        task_id = uuid4()
        community_id = uuid4()
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": str(community_id),
            "batch_size": 100,
            "status": "in_progress",
            "processed_count": 0,
            "total_count": 100,
            "error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.update_progress(task_id, 50)

        assert result is not None
        assert result.processed_count == 50

    @pytest.mark.asyncio
    async def test_mark_completed_sets_status_and_count(self, tracker, mock_redis):
        """Mark completed sets status to completed and final count."""
        import json

        task_id = uuid4()
        community_id = uuid4()
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": str(community_id),
            "batch_size": 100,
            "status": "in_progress",
            "processed_count": 90,
            "total_count": 100,
            "error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.mark_completed(task_id, 100)

        assert result is not None
        assert result.status == RechunkTaskStatus.COMPLETED
        assert result.processed_count == 100

    @pytest.mark.asyncio
    async def test_mark_failed_sets_status_and_error(self, tracker, mock_redis):
        """Mark failed sets status to failed and stores error message."""
        import json

        task_id = uuid4()
        community_id = uuid4()
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": str(community_id),
            "batch_size": 100,
            "status": "in_progress",
            "processed_count": 25,
            "total_count": 100,
            "error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.mark_failed(task_id, "Connection lost", 25)

        assert result is not None
        assert result.status == RechunkTaskStatus.FAILED
        assert result.error == "Connection lost"
        assert result.processed_count == 25

    @pytest.mark.asyncio
    async def test_get_task_handles_null_community_server_id(self, tracker, mock_redis):
        """Get task correctly deserializes when community_server_id is null.

        Bug: task-896 - The deserialization code unconditionally called UUID()
        on community_server_id, causing 'badly formed hexadecimal UUID string'
        when the field was None (for global credentials fallback).
        """
        import json

        task_id = uuid4()
        stored_data = {
            "task_id": str(task_id),
            "task_type": "fact_check",
            "community_server_id": None,  # Using global credentials fallback
            "batch_size": 100,
            "status": "in_progress",
            "processed_count": 25,
            "total_count": 50,
            "error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        result = await tracker.get_task(task_id)

        assert result is not None
        assert result.task_id == task_id
        assert result.community_server_id is None
        assert result.status == RechunkTaskStatus.IN_PROGRESS
        assert result.processed_count == 25
