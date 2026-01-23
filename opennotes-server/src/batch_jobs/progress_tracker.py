"""
Redis-based real-time progress tracking for batch jobs.

Provides fast, ephemeral progress updates that complement the persistent
BatchJob database records. Used for real-time UI updates during job execution.

Uses Redis hashes with HINCRBY for atomic increment operations to prevent
race conditions during concurrent progress updates.
"""

import time
from dataclasses import dataclass, field
from uuid import UUID

from src.cache.redis_client import RedisClient, redis_client
from src.monitoring import get_logger

logger = get_logger(__name__)

BATCH_JOB_PROGRESS_KEY_PREFIX = "batch_job:progress:"
BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX = "batch_job:processed:"
BATCH_JOB_PROGRESS_TTL_SECONDS = 3600  # 1 hour
BATCH_JOB_PROCESSED_BITMAP_TTL_SECONDS = 86400  # 24 hours


@dataclass
class BatchJobProgressData:
    """Real-time progress data for a batch job."""

    job_id: UUID
    processed_count: int = 0
    error_count: int = 0
    current_item: str | None = None
    started_at: float = field(default_factory=time.time)
    last_update_at: float = field(default_factory=time.time)

    @property
    def rate(self) -> float:
        """Calculate processing rate (items per second)."""
        elapsed = self.last_update_at - self.started_at
        if elapsed <= 0:
            return 0.0
        return self.processed_count / elapsed

    @property
    def eta_seconds(self) -> float | None:
        """Estimate time to completion based on current rate."""
        if self.rate <= 0:
            return None
        return None  # Requires total_count which is in DB

    def to_hash(self) -> dict[str, str | int | float]:
        """Convert to dictionary for Redis hash storage."""
        result: dict[str, str | int | float] = {
            "job_id": str(self.job_id),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "started_at": self.started_at,
            "last_update_at": self.last_update_at,
        }
        if self.current_item is not None:
            result["current_item"] = self.current_item
        return result

    @classmethod
    def from_hash(cls, data: dict[str, str]) -> "BatchJobProgressData":
        """Create from Redis hash data."""
        return cls(
            job_id=UUID(data["job_id"]),
            processed_count=int(data.get("processed_count", 0)),
            error_count=int(data.get("error_count", 0)),
            current_item=data.get("current_item"),
            started_at=float(data.get("started_at", time.time())),
            last_update_at=float(data.get("last_update_at", time.time())),
        )


class BatchJobProgressTracker:
    """
    Redis-based tracker for real-time batch job progress.

    Provides fast, ephemeral progress updates that can be polled frequently
    without impacting database performance.

    Uses Redis hashes with HINCRBY for atomic increment operations to prevent
    race conditions when multiple workers update progress concurrently.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        """
        Initialize the tracker with a Redis client.

        Args:
            redis_client: RedisClient instance for persistence
        """
        self._redis = redis_client

    def _progress_key(self, job_id: UUID) -> str:
        """Generate Redis key for job progress."""
        return f"{BATCH_JOB_PROGRESS_KEY_PREFIX}{job_id}"

    def _processed_bitmap_key(self, job_id: UUID) -> str:
        """Generate Redis key for processed items bitmap."""
        return f"{BATCH_JOB_PROCESSED_BITMAP_KEY_PREFIX}{job_id}"

    async def start_tracking(self, job_id: UUID, current_item: str | None = None) -> bool:
        """
        Initialize progress tracking for a job.

        Args:
            job_id: The job's unique identifier
            current_item: Optional description of first item being processed

        Returns:
            True if tracking was initialized, False on error
        """
        progress = BatchJobProgressData(
            job_id=job_id,
            current_item=current_item,
        )

        try:
            key = self._progress_key(job_id)
            await self._redis.hset(key, progress.to_hash())
            await self._redis.expire(key, BATCH_JOB_PROGRESS_TTL_SECONDS)
            logger.debug(
                "Started progress tracking",
                extra={"job_id": str(job_id)},
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to start progress tracking",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            return False

    async def update_progress(
        self,
        job_id: UUID,
        processed_count: int | None = None,
        error_count: int | None = None,
        current_item: str | None = None,
        increment_processed: bool = False,
        increment_errors: bool = False,
    ) -> BatchJobProgressData | None:
        """
        Update progress for a job.

        Uses atomic HINCRBY for increment operations to prevent race conditions.

        Args:
            job_id: The job's unique identifier
            processed_count: Absolute processed count (overrides increment)
            error_count: Absolute error count (overrides increment)
            current_item: Description of current item being processed
            increment_processed: Increment processed_count by 1 (atomic)
            increment_errors: Increment error_count by 1 (atomic)

        Returns:
            Updated progress data, or None if not found/error
        """
        try:
            key = self._progress_key(job_id)

            # Handle atomic increments first
            if increment_processed and processed_count is None:
                await self._redis.hincrby(key, "processed_count", 1)

            if increment_errors and error_count is None:
                await self._redis.hincrby(key, "error_count", 1)

            # Build update hash for non-increment fields
            updates: dict[str, str | int | float] = {
                "last_update_at": time.time(),
            }

            if processed_count is not None:
                updates["processed_count"] = processed_count

            if error_count is not None:
                updates["error_count"] = error_count

            if current_item is not None:
                updates["current_item"] = current_item

            await self._redis.hset(key, updates)

            # Refresh TTL
            await self._redis.expire(key, BATCH_JOB_PROGRESS_TTL_SECONDS)

            # Return current state
            return await self.get_progress(job_id)
        except Exception as e:
            logger.error(
                "Failed to update progress",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            return None

    async def get_progress(self, job_id: UUID) -> BatchJobProgressData | None:
        """
        Get current progress for a job.

        Args:
            job_id: The job's unique identifier

        Returns:
            Progress data if found, None otherwise
        """
        try:
            key = self._progress_key(job_id)
            data = await self._redis.hgetall(key)
            if not data or "job_id" not in data:
                return None
            return BatchJobProgressData.from_hash(data)
        except Exception as e:
            logger.error(
                "Failed to get progress",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            return None

    async def mark_item_processed(self, job_id: UUID, item_index: int) -> bool:
        """
        Mark an item as processed using a Redis bitmap.

        Uses Redis SETBIT to atomically mark the item at the given index
        as processed. This enables idempotent processing - items already
        processed can be skipped on restart.

        Args:
            job_id: The job's unique identifier
            item_index: Zero-based index of the item being processed

        Returns:
            True if item was newly marked (was 0, now 1), False if already processed
        """
        try:
            key = self._processed_bitmap_key(job_id)
            original_value = await self._redis.setbit(key, item_index, 1)
            await self._redis.expire(key, BATCH_JOB_PROCESSED_BITMAP_TTL_SECONDS)
            return original_value == 0
        except Exception as e:
            logger.error(
                "Failed to mark item processed",
                extra={"job_id": str(job_id), "item_index": item_index, "error": str(e)},
            )
            return False

    async def is_item_processed(self, job_id: UUID, item_index: int) -> bool:
        """
        Check if an item has been processed using the Redis bitmap.

        Uses Redis GETBIT to check if the item at the given index has
        been marked as processed. This enables idempotent processing.

        Args:
            job_id: The job's unique identifier
            item_index: Zero-based index of the item to check

        Returns:
            True if item is already processed, False otherwise
        """
        try:
            key = self._processed_bitmap_key(job_id)
            result = await self._redis.getbit(key, item_index)
            return result == 1
        except Exception as e:
            logger.error(
                "Failed to check if item processed",
                extra={"job_id": str(job_id), "item_index": item_index, "error": str(e)},
            )
            return False

    async def clear_processed_bitmap(self, job_id: UUID) -> bool:
        """
        Clear the processed items bitmap for a completed job.

        Should be called when a job completes successfully to clean up
        the bitmap from Redis.

        Args:
            job_id: The job's unique identifier

        Returns:
            True if cleared, False if not found/error
        """
        try:
            key = self._processed_bitmap_key(job_id)
            result = await self._redis.delete(key)
            if result > 0:
                logger.debug(
                    "Cleared processed bitmap",
                    extra={"job_id": str(job_id)},
                )
                return True
            return False
        except Exception as e:
            logger.error(
                "Failed to clear processed bitmap",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            return False

    async def stop_tracking(self, job_id: UUID) -> bool:
        """
        Remove progress tracking for a completed job.

        Args:
            job_id: The job's unique identifier

        Returns:
            True if removed, False if not found/error
        """
        try:
            key = self._progress_key(job_id)
            result = await self._redis.delete(key)
            if result > 0:
                logger.debug(
                    "Stopped progress tracking",
                    extra={"job_id": str(job_id)},
                )
                return True
            return False
        except Exception as e:
            logger.error(
                "Failed to stop progress tracking",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            return False


def get_batch_job_progress_tracker() -> BatchJobProgressTracker:
    """Get a BatchJobProgressTracker instance using the global Redis client."""
    return BatchJobProgressTracker(redis_client)
