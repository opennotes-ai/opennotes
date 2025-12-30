"""
Redis-based tracker for rechunk background task status.

This module provides persistent tracking of rechunk task progress using Redis,
enabling clients to poll for completion status and progress metrics.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
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

VALID_STATUS_TRANSITIONS: dict[RechunkTaskStatus, set[RechunkTaskStatus]] = {
    RechunkTaskStatus.PENDING: {RechunkTaskStatus.IN_PROGRESS, RechunkTaskStatus.FAILED},
    RechunkTaskStatus.IN_PROGRESS: {RechunkTaskStatus.COMPLETED, RechunkTaskStatus.FAILED},
    RechunkTaskStatus.COMPLETED: set(),
    RechunkTaskStatus.FAILED: set(),
}


class TaskLookupErrorReason(str, Enum):
    """Reason for task lookup failure."""

    NOT_FOUND = "not_found"
    REDIS_ERROR = "redis_error"
    PARSE_ERROR = "parse_error"


@dataclass
class TaskLookupError:
    """Structured error for task lookup failures."""

    reason: TaskLookupErrorReason
    message: str
    task_id: UUID


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_status: RechunkTaskStatus, target_status: RechunkTaskStatus) -> None:
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Invalid state transition from {current_status.value} to {target_status.value}"
        )


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
            RuntimeError: If Redis fails to persist the task
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

        success = await self._save_task(task)
        if not success:
            raise RuntimeError(f"Failed to persist task {task_id} to Redis")

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
            csi = task_dict.get("community_server_id")
            # Handle both JSON null and legacy "None" string from str(None)
            task_dict["community_server_id"] = UUID(csi) if csi and csi != "None" else None
            task_dict["created_at"] = datetime.fromisoformat(task_dict["created_at"])
            task_dict["updated_at"] = datetime.fromisoformat(task_dict["updated_at"])
            return RechunkTaskResponse(**task_dict)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(
                "Failed to parse task data from Redis",
                extra={"task_id": str(task_id), "error": str(e)},
            )
            return None

    async def get_task_or_error(self, task_id: UUID) -> RechunkTaskResponse | TaskLookupError:
        """
        Retrieve a task by its ID with structured error information.

        Unlike get_task which returns None for all failure cases, this method
        returns structured error information to help diagnose the failure reason.

        Args:
            task_id: The task's unique identifier

        Returns:
            The task if found, or a TaskLookupError with the reason for failure
        """
        key = self._task_key(task_id)

        try:
            data = await self._redis.get(key)
        except Exception as e:
            return TaskLookupError(
                reason=TaskLookupErrorReason.REDIS_ERROR,
                message=f"Redis error while fetching task: {e}",
                task_id=task_id,
            )

        if data is None:
            return TaskLookupError(
                reason=TaskLookupErrorReason.NOT_FOUND,
                message=f"Task {task_id} not found",
                task_id=task_id,
            )

        try:
            task_dict = json.loads(data)
            task_dict["task_id"] = UUID(task_dict["task_id"])
            csi = task_dict.get("community_server_id")
            # Handle both JSON null and legacy "None" string from str(None)
            task_dict["community_server_id"] = UUID(csi) if csi and csi != "None" else None
            task_dict["created_at"] = datetime.fromisoformat(task_dict["created_at"])
            task_dict["updated_at"] = datetime.fromisoformat(task_dict["updated_at"])
            return RechunkTaskResponse(**task_dict)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return TaskLookupError(
                reason=TaskLookupErrorReason.PARSE_ERROR,
                message=f"Failed to parse task data: {e}",
                task_id=task_id,
            )

    def _validate_transition(
        self, current_status: RechunkTaskStatus, target_status: RechunkTaskStatus
    ) -> None:
        """
        Validate that a status transition is allowed.

        Args:
            current_status: Current task status
            target_status: Target status to transition to

        Raises:
            InvalidStateTransitionError: If the transition is not allowed
        """
        if current_status == target_status:
            return

        valid_targets = VALID_STATUS_TRANSITIONS.get(current_status, set())
        if target_status not in valid_targets:
            raise InvalidStateTransitionError(current_status, target_status)

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

        Raises:
            InvalidStateTransitionError: If the status transition is invalid
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        current_status = (
            RechunkTaskStatus(task.status) if isinstance(task.status, str) else task.status
        )
        target_status = RechunkTaskStatus(status) if isinstance(status, str) else status

        self._validate_transition(current_status, target_status)

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

    async def mark_in_progress(
        self,
        task_id: UUID,
    ) -> RechunkTaskResponse | None:
        """
        Mark a task as in progress.

        This method validates that the task is in PENDING status before
        transitioning to IN_PROGRESS.

        Args:
            task_id: The task's unique identifier

        Returns:
            The updated task if found, None otherwise

        Raises:
            InvalidStateTransitionError: If task is not in PENDING status
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        current_status = (
            RechunkTaskStatus(task.status) if isinstance(task.status, str) else task.status
        )
        self._validate_transition(current_status, RechunkTaskStatus.IN_PROGRESS)

        task.status = RechunkTaskStatus.IN_PROGRESS
        task.updated_at = datetime.now(UTC)

        await self._save_task(task)

        logger.info(
            "Task started",
            extra={
                "task_id": str(task_id),
                "total_count": task.total_count,
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

        Raises:
            InvalidStateTransitionError: If task is not in IN_PROGRESS status
        """
        task = await self.get_task(task_id)
        if task is None:
            return None

        current_status = (
            RechunkTaskStatus(task.status) if isinstance(task.status, str) else task.status
        )
        self._validate_transition(current_status, RechunkTaskStatus.COMPLETED)

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

        If Redis is unavailable or the task cannot be found, logs the error
        for recovery purposes and returns None.

        Args:
            task_id: The task's unique identifier
            error: Error message describing the failure
            processed_count: Number of items processed before failure

        Returns:
            The updated task if found and updated, None otherwise

        Raises:
            InvalidStateTransitionError: If task is already COMPLETED or FAILED
        """
        try:
            task = await self.get_task(task_id)
        except Exception as e:
            logger.error(
                "Failed to retrieve task for mark_failed - error details logged for recovery",
                extra={
                    "task_id": str(task_id),
                    "original_error": error,
                    "redis_error": str(e),
                    "processed_count": processed_count,
                },
            )
            return None

        if task is None:
            logger.error(
                "Task not found for mark_failed - error details logged for recovery",
                extra={
                    "task_id": str(task_id),
                    "original_error": error,
                    "processed_count": processed_count,
                },
            )
            return None

        current_status = (
            RechunkTaskStatus(task.status) if isinstance(task.status, str) else task.status
        )
        self._validate_transition(current_status, RechunkTaskStatus.FAILED)

        task.status = RechunkTaskStatus.FAILED
        task.error = error
        task.processed_count = processed_count
        task.updated_at = datetime.now(UTC)

        try:
            await self._save_task(task)
        except Exception as e:
            logger.error(
                "Failed to persist task failure - error details logged for recovery",
                extra={
                    "task_id": str(task_id),
                    "original_error": error,
                    "redis_error": str(e),
                    "processed_count": processed_count,
                },
            )
            return None

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

    async def mark_failed_force(
        self,
        task_id: UUID,
        error: str,
        processed_count: int,
        task_type: RechunkTaskType,
        community_server_id: UUID | None,
        batch_size: int,
        total_items: int,
    ) -> RechunkTaskResponse | None:
        """
        Force-create a failed task record even if the original task doesn't exist.

        This is used when a background task fails during startup before it can
        update the task status. It creates a new FAILED task record with the
        original task_id so that clients polling for status can see the error.

        Args:
            task_id: The task's unique identifier (must match the original)
            error: Error message describing the failure
            processed_count: Number of items processed before failure
            task_type: Type of rechunk operation
            community_server_id: Community server ID for LLM credentials
            batch_size: Original batch size
            total_items: Original total items count

        Returns:
            The created failed task if successful, None if Redis is unavailable
        """
        now = datetime.now(UTC)

        task = RechunkTaskResponse(
            task_id=task_id,
            task_type=task_type,
            community_server_id=community_server_id,
            batch_size=batch_size,
            status=RechunkTaskStatus.FAILED,
            processed_count=processed_count,
            total_count=total_items,
            error=error,
            created_at=now,
            updated_at=now,
        )

        try:
            success = await self._save_task(task)
            if not success:
                logger.error(
                    "Failed to force-persist failed task - error details logged for recovery",
                    extra={
                        "task_id": str(task_id),
                        "error": error,
                        "processed_count": processed_count,
                    },
                )
                return None
        except Exception as e:
            logger.error(
                "Exception during force-persist of failed task - error details logged for recovery",
                extra={
                    "task_id": str(task_id),
                    "error": error,
                    "redis_error": str(e),
                    "processed_count": processed_count,
                },
            )
            return None

        logger.error(
            "Force-created failed task record",
            extra={
                "task_id": str(task_id),
                "error": error,
                "processed_count": processed_count,
                "total_count": total_items,
            },
        )

        return task

    async def _save_task(self, task: RechunkTaskResponse) -> bool:
        """
        Save task to Redis with TTL.

        Args:
            task: The task to save

        Returns:
            True if save succeeded, False otherwise
        """
        key = self._task_key(task.task_id)

        task_dict = {
            "task_id": str(task.task_id),
            "task_type": (
                task.task_type.value
                if isinstance(task.task_type, RechunkTaskType)
                else task.task_type
            ),
            # Serialize None as JSON null, not string "None"
            "community_server_id": str(task.community_server_id)
            if task.community_server_id
            else None,
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

        result = await self._redis.set(key, json.dumps(task_dict), ttl=RECHUNK_TASK_TTL_SECONDS)
        return result is not False

    async def delete_task(self, task_id: UUID) -> bool:
        """
        Delete a task from Redis.

        Args:
            task_id: The task's unique identifier

        Returns:
            True if task was deleted, False if not found or error occurred
        """
        key = self._task_key(task_id)
        try:
            result = await self._redis.delete(key)
            if result > 0:
                logger.info(
                    "Deleted rechunk task",
                    extra={"task_id": str(task_id)},
                )
                return True
            return False
        except Exception as e:
            logger.error(
                "Failed to delete rechunk task",
                extra={"task_id": str(task_id), "error": str(e)},
            )
            return False

    async def list_tasks(
        self, status: RechunkTaskStatus | None = None
    ) -> list[RechunkTaskResponse]:
        """
        List all rechunk tasks, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            List of tasks matching the filter
        """
        tasks: list[RechunkTaskResponse] = []
        pattern = f"{RECHUNK_TASK_KEY_PREFIX}*"

        try:
            keys: list[str] = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if not keys:
                return tasks

            values = await self._redis.mget(keys)

            for data in values:
                if data is None:
                    continue
                try:
                    task_dict = json.loads(data)
                    task_dict["task_id"] = UUID(task_dict["task_id"])
                    csi = task_dict.get("community_server_id")
                    task_dict["community_server_id"] = UUID(csi) if csi and csi != "None" else None
                    task_dict["created_at"] = datetime.fromisoformat(task_dict["created_at"])
                    task_dict["updated_at"] = datetime.fromisoformat(task_dict["updated_at"])

                    task = RechunkTaskResponse(**task_dict)

                    if status is not None:
                        task_status = (
                            RechunkTaskStatus(task.status)
                            if isinstance(task.status, str)
                            else task.status
                        )
                        if task_status != status:
                            continue

                    tasks.append(task)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(
                        "Failed to parse task data during list",
                        extra={"error": str(e)},
                    )
                    continue

        except Exception as e:
            logger.error(
                "Failed to list rechunk tasks",
                extra={"error": str(e)},
            )

        return tasks


def get_rechunk_task_tracker() -> RechunkTaskTracker:
    """Get a RechunkTaskTracker instance using the global Redis client."""
    return RechunkTaskTracker(redis_client)
