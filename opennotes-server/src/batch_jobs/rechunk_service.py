"""
Rechunk-specific batch job service.

Provides high-level operations for creating and managing rechunk batch jobs.
This is a thin wrapper around BatchJobService that handles rechunk-specific
logic like counting items and setting up appropriate metadata.

Concurrency Control:
    Jobs are protected at two levels:
    1. Service-level: Checks for active jobs before creating new ones (prevents orphans)
    2. Worker-level: DistributedRateLimitMiddleware enforces one active task per type

Orphan Recovery:
    Use cleanup_stale_jobs() to recover from orphaned jobs (e.g., jobs stuck in
    PENDING/IN_PROGRESS due to worker crashes). Consider running periodically.

Monitoring:
    Use get_stuck_jobs_info() to check for jobs stuck in non-terminal states
    with zero progress. This is used by health checks to detect potential issues.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.constants import (
    PROMOTION_JOB_TYPE,
    RECHUNK_FACT_CHECK_JOB_TYPE,
    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
    SCRAPE_JOB_TYPE,
)
from src.batch_jobs.models import BatchJob
from src.batch_jobs.progress_tracker import (
    BatchJobProgressTracker,
    get_batch_job_progress_tracker,
)
from src.batch_jobs.schemas import BatchJobCreate, BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.config import settings
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.monitoring import get_logger

logger = get_logger(__name__)

DEFAULT_STALE_JOB_THRESHOLD_HOURS = 2
STUCK_JOB_THRESHOLD_MINUTES = 30


@dataclass
class StuckJobInfo:
    """Information about a batch job that appears to be stuck."""

    job_id: UUID
    job_type: str
    status: str
    completed_tasks: int
    total_tasks: int
    stuck_duration_seconds: float
    started_at: datetime | None
    updated_at: datetime | None


def _job_type_lock_key(job_type: str) -> int:
    """
    Generate a deterministic int64 lock key from a job_type string.

    Uses MD5 hash (first 8 bytes interpreted as signed int64) to generate
    a consistent lock key for pg_advisory_xact_lock.

    Args:
        job_type: The job type string (e.g., "rechunk:fact_check")

    Returns:
        A signed 64-bit integer suitable for PostgreSQL advisory locks
    """
    hash_bytes = hashlib.md5(job_type.encode()).digest()[:8]
    return int.from_bytes(hash_bytes, byteorder="big", signed=True)


class ActiveJobExistsError(Exception):
    """Raised when attempting to create a job while another is active."""

    def __init__(self, job_type: str, active_job_id: UUID) -> None:
        self.job_type = job_type
        self.active_job_id = active_job_id
        super().__init__(f"Cannot create {job_type} job: active job {active_job_id} already exists")


class RechunkType(str, Enum):
    """Type of rechunk operation."""

    FACT_CHECK = "fact_check"
    PREVIOUSLY_SEEN = "previously_seen"


class RechunkBatchJobService:
    """
    Service for managing rechunk batch jobs.

    Provides methods to start and manage rechunk operations using the
    BatchJob infrastructure for persistent tracking and progress reporting.
    """

    def __init__(
        self,
        session: AsyncSession,
        batch_job_service: BatchJobService | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            session: SQLAlchemy async session for database operations
            batch_job_service: Optional BatchJobService instance (created if not provided)
        """
        self._session = session
        self._batch_job_service = batch_job_service or BatchJobService(session)

    async def _check_no_active_job(self, job_type: str) -> None:
        """
        Check that no active job exists for the given type.

        This prevents creating orphaned jobs by ensuring we don't create a new
        job when one is already pending or running.

        Concurrency Control:
            This method uses a two-layer locking strategy:

            1. **Advisory Lock (Primary)**: pg_advisory_xact_lock acquires an
               exclusive transaction-level lock keyed by job_type. This prevents
               TOCTOU race conditions even when no active job rows exist yet.
               The lock is automatically released when the transaction commits
               or rolls back.

            2. **SELECT FOR UPDATE (Secondary)**: Defense-in-depth check that
               locks any existing active job row. This provides additional
               safety against edge cases and makes the intent explicit.

        Global Serialization:
            The advisory lock is global per job_type, meaning all job creation
            requests for the same job_type are serialized across the entire
            system, regardless of community_server_id. This is intentional:
            - Prevents system overload from concurrent batch operations
            - Simplifies resource management and capacity planning
            - Matches the "one active job per type" business rule

        Args:
            job_type: The job type to check

        Raises:
            ActiveJobExistsError: If an active job exists for this type
        """
        lock_key = _job_type_lock_key(job_type)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=lock_key)
        )

        query = (
            select(BatchJob)
            .where(
                BatchJob.job_type == job_type,
                or_(
                    BatchJob.status == BatchJobStatus.PENDING.value,
                    BatchJob.status == BatchJobStatus.IN_PROGRESS.value,
                ),
            )
            .with_for_update()
        )
        result = await self._session.execute(query)
        active_job = result.scalar_one_or_none()

        if active_job is not None:
            logger.warning(
                "Cannot create job: active job already exists",
                extra={
                    "job_type": job_type,
                    "active_job_id": str(active_job.id),
                    "active_job_status": active_job.status,
                },
            )
            raise ActiveJobExistsError(job_type, active_job.id)

    async def start_fact_check_rechunk_job(
        self,
        community_server_id: UUID | None,
        batch_size: int = 100,
    ) -> BatchJob:
        """
        Start a fact check rechunk job.

        Checks for active jobs first, then creates a BatchJob and dispatches
        the TaskIQ task.

        Args:
            community_server_id: Community server ID for LLM credentials (None for global)
            batch_size: Number of items to process per batch

        Returns:
            The created and started BatchJob

        Raises:
            ActiveJobExistsError: If a fact check rechunk job is already active
        """
        await self._check_no_active_job(RECHUNK_FACT_CHECK_JOB_TYPE)

        result = await self._session.execute(select(func.count(FactCheckItem.id)))
        total_items = result.scalar_one()

        job = await self._batch_job_service.create_job(
            BatchJobCreate(
                job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
                total_tasks=total_items,
                metadata={
                    "community_server_id": str(community_server_id)
                    if community_server_id
                    else None,
                    "batch_size": batch_size,
                    "chunk_type": RechunkType.FACT_CHECK.value,
                },
            )
        )

        await self._batch_job_service.start_job(job.id)
        await self._session.commit()
        await self._session.refresh(job)

        try:
            from src.tasks.rechunk_tasks import process_fact_check_rechunk_task  # noqa: PLC0415

            await process_fact_check_rechunk_task.kiq(
                job_id=str(job.id),
                community_server_id=str(community_server_id) if community_server_id else None,
                batch_size=batch_size,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
            )
        except Exception as e:
            await self._batch_job_service.fail_job(
                job.id,
                error_summary={"error": str(e), "stage": "task_dispatch"},
            )
            await self._session.commit()
            await self._session.refresh(job)
            raise

        logger.info(
            "Started fact check rechunk batch job",
            extra={
                "job_id": str(job.id),
                "community_server_id": str(community_server_id) if community_server_id else None,
                "batch_size": batch_size,
                "total_items": total_items,
            },
        )

        return job

    async def start_previously_seen_rechunk_job(
        self,
        community_server_id: UUID,
        batch_size: int = 100,
    ) -> BatchJob:
        """
        Start a previously seen message rechunk job.

        Checks for active jobs first, then creates a BatchJob and dispatches
        the TaskIQ task.

        Global Serialization:
            Jobs of this type are serialized globally across all community servers.
            Even though community_server_id is provided, only one previously_seen
            rechunk job can run at a time system-wide. This is intentional:
            - Prevents system overload from concurrent batch operations
            - Simplifies resource management and capacity planning
            - Ensures predictable system behavior under load

        Args:
            community_server_id: Community server ID for LLM credentials
            batch_size: Number of items to process per batch

        Returns:
            The created and started BatchJob

        Raises:
            ActiveJobExistsError: If a previously seen rechunk job is already active
                (regardless of community_server_id)
        """
        await self._check_no_active_job(RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE)

        result = await self._session.execute(
            select(func.count(PreviouslySeenMessage.id)).where(
                PreviouslySeenMessage.community_server_id == community_server_id
            )
        )
        total_items = result.scalar_one()

        job = await self._batch_job_service.create_job(
            BatchJobCreate(
                job_type=RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
                total_tasks=total_items,
                metadata={
                    "community_server_id": str(community_server_id),
                    "batch_size": batch_size,
                    "chunk_type": RechunkType.PREVIOUSLY_SEEN.value,
                },
            )
        )

        await self._batch_job_service.start_job(job.id)
        await self._session.commit()
        await self._session.refresh(job)

        try:
            from src.tasks.rechunk_tasks import (  # noqa: PLC0415
                process_previously_seen_rechunk_task,
            )

            await process_previously_seen_rechunk_task.kiq(
                job_id=str(job.id),
                community_server_id=str(community_server_id),
                batch_size=batch_size,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
            )
        except Exception as e:
            await self._batch_job_service.fail_job(
                job.id,
                error_summary={"error": str(e), "stage": "task_dispatch"},
            )
            await self._session.commit()
            await self._session.refresh(job)
            raise

        logger.info(
            "Started previously seen rechunk batch job",
            extra={
                "job_id": str(job.id),
                "community_server_id": str(community_server_id),
                "batch_size": batch_size,
                "total_items": total_items,
            },
        )

        return job

    async def cancel_rechunk_job(self, job_id: UUID) -> BatchJob | None:
        """
        Cancel a rechunk job.

        Args:
            job_id: The job's unique identifier

        Returns:
            The cancelled BatchJob if found, None otherwise
        """
        job = await self._batch_job_service.get_job(job_id)
        if job is None:
            return None

        metadata = job.metadata_ or {}
        chunk_type = metadata.get("chunk_type")
        community_server_id = metadata.get("community_server_id")

        cancelled_job = await self._batch_job_service.cancel_job(job_id)
        await self._session.commit()

        logger.info(
            "Cancelled rechunk batch job",
            extra={
                "job_id": str(job_id),
                "chunk_type": chunk_type,
                "community_server_id": community_server_id,
            },
        )

        return cancelled_job

    async def cleanup_stale_jobs(
        self,
        stale_threshold_hours: float = DEFAULT_STALE_JOB_THRESHOLD_HOURS,
        progress_tracker: BatchJobProgressTracker | None = None,
    ) -> list[BatchJob]:
        """
        Mark stale jobs as failed.

        Jobs are considered stale if they have been in PENDING or IN_PROGRESS status
        for longer than the specified threshold (based on updated_at). This recovers
        from scenarios like worker crashes or network failures that left jobs in a
        non-terminal state.

        Note:
            Uses updated_at (not created_at) to determine staleness. This ensures
            that jobs actively reporting progress are not incorrectly marked as stale,
            even if they were created long ago. A job is only considered stale if it
            has stopped updating for the threshold period.

        Args:
            stale_threshold_hours: Hours after which a non-terminal job is considered
                stale (based on last update). Defaults to 2 hours.
            progress_tracker: Optional progress tracker for cleaning up Redis bitmaps.
                If not provided, uses the global tracker.

        Returns:
            List of jobs that were marked as failed
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=stale_threshold_hours)

        query = select(BatchJob).where(
            BatchJob.job_type.in_(
                [
                    RECHUNK_FACT_CHECK_JOB_TYPE,
                    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
                    SCRAPE_JOB_TYPE,
                    PROMOTION_JOB_TYPE,
                ]
            ),
            or_(
                BatchJob.status == BatchJobStatus.PENDING.value,
                BatchJob.status == BatchJobStatus.IN_PROGRESS.value,
            ),
            BatchJob.updated_at < cutoff_time,
        )
        result = await self._session.execute(query)
        stale_jobs = list(result.scalars().all())

        tracker = progress_tracker or get_batch_job_progress_tracker()
        failed_jobs: list[BatchJob] = []
        for job in stale_jobs:
            failed_job = await self._batch_job_service.fail_job(
                job.id,
                error_summary={
                    "error": "Job marked as stale",
                    "reason": f"Job was in {job.status} status for over {stale_threshold_hours} hours",
                    "cleanup_time": datetime.now(UTC).isoformat(),
                },
            )
            if failed_job is not None:
                failed_jobs.append(failed_job)
                await tracker.clear_processed_bitmap(job.id)

        if failed_jobs:
            await self._session.commit()
            logger.info(
                "Cleaned up stale rechunk jobs",
                extra={
                    "cleaned_count": len(failed_jobs),
                    "job_ids": [str(j.id) for j in failed_jobs],
                    "threshold_hours": stale_threshold_hours,
                },
            )

        return failed_jobs

    async def get_stuck_jobs_info(
        self,
        threshold_minutes: float = STUCK_JOB_THRESHOLD_MINUTES,
    ) -> list[StuckJobInfo]:
        """
        Get information about potentially stuck batch jobs.

        A job is considered "stuck" if it:
        1. Is in PENDING or IN_PROGRESS status
        2. Has not been updated for longer than the threshold

        Note: Jobs with partial progress (completed_tasks > 0) are also detected
        if they haven't been updated within the threshold. This catches jobs that
        processed some items then got stuck.

        This is useful for health checks and monitoring dashboards to detect
        jobs that may need manual intervention or indicate worker issues.

        Timezone Handling:
            Database timestamps are assumed to be stored in UTC. If the database
            returns naive datetimes, they are interpreted as UTC. This is the
            standard convention for PostgreSQL with TIMESTAMPTZ columns.

        Args:
            threshold_minutes: Minutes after which an inactive job is
                considered stuck. Defaults to 30 minutes.

        Returns:
            List of StuckJobInfo for jobs meeting the criteria
        """
        now = datetime.now(UTC)
        cutoff_time = now - timedelta(minutes=threshold_minutes)

        query = select(BatchJob).where(
            BatchJob.job_type.in_(
                [
                    RECHUNK_FACT_CHECK_JOB_TYPE,
                    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
                    SCRAPE_JOB_TYPE,
                    PROMOTION_JOB_TYPE,
                ]
            ),
            or_(
                BatchJob.status == BatchJobStatus.PENDING.value,
                BatchJob.status == BatchJobStatus.IN_PROGRESS.value,
            ),
            BatchJob.updated_at < cutoff_time,
        )

        result = await self._session.execute(query)
        stuck_jobs = result.scalars().all()

        stuck_info: list[StuckJobInfo] = []
        for job in stuck_jobs:
            reference_time = job.updated_at or job.created_at
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=UTC)
            stuck_duration = (now - reference_time).total_seconds()

            stuck_info.append(
                StuckJobInfo(
                    job_id=job.id,
                    job_type=job.job_type,
                    status=job.status,
                    completed_tasks=job.completed_tasks,
                    total_tasks=job.total_tasks,
                    stuck_duration_seconds=stuck_duration,
                    started_at=job.started_at,
                    updated_at=job.updated_at,
                )
            )

        if stuck_info:
            logger.warning(
                "Found stuck batch jobs",
                extra={
                    "stuck_count": len(stuck_info),
                    "job_ids": [str(info.job_id) for info in stuck_info],
                    "threshold_minutes": threshold_minutes,
                },
            )

        return stuck_info
