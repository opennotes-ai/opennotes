"""
Redis-based tracker for rechunk background task status.

This module provides persistent tracking of rechunk task progress using Redis,
enabling clients to poll for completion status and progress metrics.
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.cache.redis_client import RedisClient, redis_client
from src.fact_checking.chunk_task_schemas import (
    RechunkTaskCreate,
    RechunkTaskResponse,
    RechunkTaskStatus,
    RechunkTaskType,
)
from src.monitoring import get_logger

logger = get_logger(__name__)

RECHUNK_TASK_KEY_PREFIX = "rechunk:task:"
RECHUNK_TASK_TTL_SECONDS = 86400  # 24 hours


class RechunkTaskTracker:
    """
    Service for tracking rechunk background task status via Redis.

    Provides methods to create, update, and query task status, enabling
    clients to poll for completion and view progress metrics.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        """
        Initialize the tracker with a Redis client.

        Args:
            redis_client: RedisClient instance for persistence
        """
        self._redis = redis_client

    def _task_key(self, task_id: UUID) -> str:
        """Generate Redis key for a task."""
        return f"{RECHUNK_TASK_KEY_PREFIX}{task_id}"

    async def create_task(self, task_data: RechunkTaskCreate) -> RechunkTaskResponse:
        """
        Create a new rechunk task entry.

        Args:
            task_data: Task creation data

        Returns:
            The created task with assigned ID and timestamps

        Raises:
            RuntimeError: If Redis is not connected
        """
        now = datetime.now(UTC)
        task_id = uuid4()

        task = RechunkTaskResponse(
            task_id=task_id,
            task_type=task_data.task_type,
            community_server_id=task_data.community_server_id,
            batch_size=task_data.batch_size,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=task_data.total_items,
            error=None,
            created_at=now,
            updated_at=now,
        )

        await self._save_task(task)

        logger.info(
            "Created rechunk task",
            extra={
                "task_id": str(task_id),
                "task_type": task_data.task_type,
                "community_server_id": str(task_data.community_server_id),
                "total_items": task_data.total_items,
            },
        )

        return task

    async def get_task(self, task_id: UUID) -> RechunkTaskResponse | None:
        """
        Retrieve a task by its ID.

        Args:
            task_id: The task's unique identifier

        Returns:
            The task status if found, None otherwise
        """
        key = self._task_key(task_id)
        data = await self._redis.get(key)

        if data is None:
            return None

        try:
            task_dict = json.loads(data)
            task_dict["task_id"] = UUID(task_dict["task_id"])
            task_dict["community_server_id"] = UUID(task_dict["community_server_id"])
            task_dict["created_at"] = datetime.fromisoformat(task_dict["created_at"])
            task_dict["updated_at"] = datetime.fromisoformat(task_dict["updated_at"])
            return RechunkTaskResponse(**task_dict)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(
                "Failed to parse task data from Redis",
                extra={"task_id": str(task_id), "error": str(e)},
            )
            return None

    async def update_status(
        self,
        task_id: UUID,
        status: RechunkTaskStatus,
        error: str | None = None,
    ) -> RechunkTaskResponse | None:
        """
        Update task status.

        Args:
            task_id: The task's unique identifier
            status: New status value
            error: Optional error message (for failed status)

        Returns:
            The updated task if found, None otherwise
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        task.status = status
        task.error = error
        task.updated_at = datetime.now(UTC)

        await self._save_task(task)

        logger.info(
            "Updated task status",
            extra={
                "task_id": str(task_id),
                "status": status.value if isinstance(status, RechunkTaskStatus) else status,
                "error": error,
            },
        )

        return task

    async def update_progress(
        self,
        task_id: UUID,
        processed_count: int,
    ) -> RechunkTaskResponse | None:
        """
        Update task progress count.

        Args:
            task_id: The task's unique identifier
            processed_count: Number of items processed so far

        Returns:
            The updated task if found, None otherwise
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        task.processed_count = processed_count
        task.updated_at = datetime.now(UTC)

        await self._save_task(task)

        return task

    async def mark_completed(
        self,
        task_id: UUID,
        processed_count: int,
    ) -> RechunkTaskResponse | None:
        """
        Mark a task as completed.

        Args:
            task_id: The task's unique identifier
            processed_count: Final count of processed items

        Returns:
            The updated task if found, None otherwise
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        task.status = RechunkTaskStatus.COMPLETED
        task.processed_count = processed_count
        task.updated_at = datetime.now(UTC)

        await self._save_task(task)

        logger.info(
            "Task completed",
            extra={
                "task_id": str(task_id),
                "processed_count": processed_count,
                "total_count": task.total_count,
            },
        )

        return task

    async def mark_failed(
        self,
        task_id: UUID,
        error: str,
        processed_count: int = 0,
    ) -> RechunkTaskResponse | None:
        """
        Mark a task as failed.

        Args:
            task_id: The task's unique identifier
            error: Error message describing the failure
            processed_count: Number of items processed before failure

        Returns:
            The updated task if found, None otherwise
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        task.status = RechunkTaskStatus.FAILED
        task.error = error
        task.processed_count = processed_count
        task.updated_at = datetime.now(UTC)

        await self._save_task(task)

        logger.error(
            "Task failed",
            extra={
                "task_id": str(task_id),
                "error": error,
                "processed_count": processed_count,
                "total_count": task.total_count,
            },
        )

        return task

    async def _save_task(self, task: RechunkTaskResponse) -> None:
        """
        Save task to Redis with TTL.

        Args:
            task: The task to save
        """
        key = self._task_key(task.task_id)

        task_dict = {
            "task_id": str(task.task_id),
            "task_type": (
                task.task_type.value
                if isinstance(task.task_type, RechunkTaskType)
                else task.task_type
            ),
            "community_server_id": str(task.community_server_id),
            "batch_size": task.batch_size,
            "status": (
                task.status.value if isinstance(task.status, RechunkTaskStatus) else task.status
            ),
            "processed_count": task.processed_count,
            "total_count": task.total_count,
            "error": task.error,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

        await self._redis.set(key, json.dumps(task_dict), ttl=RECHUNK_TASK_TTL_SECONDS)


def get_rechunk_task_tracker() -> RechunkTaskTracker:
    """Get a RechunkTaskTracker instance using the global Redis client."""
    return RechunkTaskTracker(redis_client)
