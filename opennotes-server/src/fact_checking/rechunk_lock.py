"""
Shared lock management for rechunk operations.

This module provides distributed locking for rechunk operations using Redis.
The lock manager prevents multiple concurrent rechunk operations for the same
resource (e.g., fact checks or previously seen messages for a community).

Lock TTL Strategy:
    The lock TTL is set to 30 minutes (1800 seconds) to balance:
    - Long enough for typical rechunk operations to complete
    - Short enough to recover from failed tasks without excessive waiting
    - The TTL acts as a safety net; tasks should release locks explicitly

Usage:
    API Endpoints (chunk_router.py):
        Uses the full RechunkLockManager with acquire/release/is_locked

    TaskIQ Workers (rechunk_tasks.py):
        Uses release_lock() only - locks are acquired in API endpoints
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis

from src.monitoring import get_logger

if TYPE_CHECKING:
    from src.cache.redis_client import RedisClient

logger = get_logger(__name__)

RECHUNK_LOCK_TTL_SECONDS = 1800
RECHUNK_LOCK_PREFIX = "rechunk:lock"


class RechunkLockManager:
    """
    Distributed lock manager for rechunk operations using Redis.

    Prevents multiple concurrent rechunk operations for the same resource.
    Uses Redis SET NX (set if not exists) with TTL for distributed locking.

    Redis Unavailability Behavior:
        When Redis is unavailable (e.g., during startup, network issues, or in
        test environments without Redis), this lock manager operates in "permissive"
        mode:
        - acquire_lock() returns True (allows operation to proceed)
        - release_lock() returns True (no-op)
        - is_locked() returns False (reports unlocked)

        This is intentional for development and graceful degradation, but means
        concurrent operations are not prevented when Redis is down. In production,
        ensure Redis is available for proper concurrency control.

        A warning is logged when operating without Redis so this behavior is
        visible in logs.
    """

    def __init__(self, redis: Redis | None = None):
        self._redis = redis

    @property
    def redis(self) -> Redis | None:
        """Get Redis client."""
        return self._redis

    def _get_lock_key(self, operation: str, resource_id: str | None = None) -> str:
        """Generate lock key for an operation."""
        if resource_id:
            return f"{RECHUNK_LOCK_PREFIX}:{operation}:{resource_id}"
        return f"{RECHUNK_LOCK_PREFIX}:{operation}"

    async def acquire_lock(
        self,
        operation: str,
        resource_id: str | None = None,
        ttl: int = RECHUNK_LOCK_TTL_SECONDS,
    ) -> bool:
        """
        Attempt to acquire a lock for a rechunk operation.

        Args:
            operation: Operation type (e.g., 'fact_check', 'previously_seen')
            resource_id: Resource identifier (e.g., community_server_id)
            ttl: Lock TTL in seconds (default: 30 minutes)

        Returns:
            True if lock was acquired, False if already locked
        """
        if not self.redis:
            logger.warning("Redis not available, allowing operation without lock")
            return True

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self.redis.set(key, "locked", nx=True, ex=ttl)
            if result:
                logger.info(
                    "Acquired rechunk lock",
                    extra={"operation": operation, "resource_id": resource_id, "key": key},
                )
            return result is not None
        except Exception as e:
            logger.error(
                "Failed to acquire rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return True

    async def release_lock(self, operation: str, resource_id: str | None = None) -> bool:
        """
        Release a lock for a rechunk operation.

        Args:
            operation: Operation type (e.g., 'fact_check', 'previously_seen')
            resource_id: Resource identifier (e.g., community_server_id)

        Returns:
            True if lock was released, False otherwise
        """
        if not self.redis:
            return True

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self.redis.delete(key)
            logger.info(
                "Released rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "key": key},
            )
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to release rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return False

    async def is_locked(self, operation: str, resource_id: str | None = None) -> bool:
        """
        Check if a rechunk operation is currently locked.

        Args:
            operation: Operation type (e.g., 'fact_check', 'previously_seen')
            resource_id: Resource identifier (e.g., community_server_id)

        Returns:
            True if locked, False otherwise
        """
        if not self.redis:
            return False

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self.redis.exists(key)
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to check rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return False


class TaskRechunkLockManager:
    """
    Simplified lock manager for use within TaskIQ tasks.

    Tasks only need to release locks (acquisition happens in API endpoints).
    This class wraps a RedisClient instance which may be created fresh in
    each task for distributed worker isolation.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis_client = redis_client

    def _get_lock_key(self, operation: str, resource_id: str | None = None) -> str:
        """Generate lock key for an operation."""
        if resource_id:
            return f"{RECHUNK_LOCK_PREFIX}:{operation}:{resource_id}"
        return f"{RECHUNK_LOCK_PREFIX}:{operation}"

    async def release_lock(self, operation: str, resource_id: str | None = None) -> bool:
        """Release a lock for a rechunk operation."""
        if not self._redis_client.client:
            return True

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self._redis_client.client.delete(key)
            logger.info(
                "Released rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "key": key},
            )
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to release rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return False


__all__ = [
    "RECHUNK_LOCK_PREFIX",
    "RECHUNK_LOCK_TTL_SECONDS",
    "RechunkLockManager",
    "TaskRechunkLockManager",
]
