"""
Redis-based real-time progress tracking for batch jobs.

Provides fast, ephemeral progress updates that complement the persistent
BatchJob database records. Used for real-time UI updates during job execution.
"""

import json
import time
from dataclasses import dataclass, field
from uuid import UUID

from src.cache.redis_client import RedisClient, redis_client
from src.monitoring import get_logger

logger = get_logger(__name__)

BATCH_JOB_PROGRESS_KEY_PREFIX = "batch_job:progress:"
BATCH_JOB_PROGRESS_TTL_SECONDS = 3600  # 1 hour


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

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "job_id": str(self.job_id),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "current_item": self.current_item,
            "started_at": self.started_at,
            "last_update_at": self.last_update_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BatchJobProgressData":
        """Create from dictionary (Redis data)."""
        return cls(
            job_id=UUID(data["job_id"]),
            processed_count=data.get("processed_count", 0),
            error_count=data.get("error_count", 0),
            current_item=data.get("current_item"),
            started_at=data.get("started_at", time.time()),
            last_update_at=data.get("last_update_at", time.time()),
        )


class BatchJobProgressTracker:
    """
    Redis-based tracker for real-time batch job progress.

    Provides fast, ephemeral progress updates that can be polled frequently
    without impacting database performance.
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
            result = await self._redis.set(
                key,
                json.dumps(progress.to_dict()),
                ttl=BATCH_JOB_PROGRESS_TTL_SECONDS,
            )
            logger.debug(
                "Started progress tracking",
                extra={"job_id": str(job_id)},
            )
            return result is not False
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

        Args:
            job_id: The job's unique identifier
            processed_count: Absolute processed count (overrides increment)
            error_count: Absolute error count (overrides increment)
            current_item: Description of current item being processed
            increment_processed: Increment processed_count by 1
            increment_errors: Increment error_count by 1

        Returns:
            Updated progress data, or None if not found/error
        """
        progress = await self.get_progress(job_id)
        if progress is None:
            progress = BatchJobProgressData(job_id=job_id)

        if processed_count is not None:
            progress.processed_count = processed_count
        elif increment_processed:
            progress.processed_count += 1

        if error_count is not None:
            progress.error_count = error_count
        elif increment_errors:
            progress.error_count += 1

        if current_item is not None:
            progress.current_item = current_item

        progress.last_update_at = time.time()

        try:
            key = self._progress_key(job_id)
            await self._redis.set(
                key,
                json.dumps(progress.to_dict()),
                ttl=BATCH_JOB_PROGRESS_TTL_SECONDS,
            )
            return progress
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
            data = await self._redis.get(key)
            if data is None:
                return None
            return BatchJobProgressData.from_dict(json.loads(data))
        except Exception as e:
            logger.error(
                "Failed to get progress",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            return None

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
