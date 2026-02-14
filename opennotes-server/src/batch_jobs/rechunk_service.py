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
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.constants import (
    BULK_APPROVAL_JOB_TYPE,
    IMPORT_JOB_TYPE,
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
from src.batch_jobs.schemas import BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.config import settings
from src.monitoring import get_logger
from src.monitoring.metrics import batch_job_stale_cleanup_total

logger = get_logger(__name__)

USE_DBOS_RECHUNK = os.environ.get("USE_DBOS_RECHUNK", "false").lower() == "true"

DEFAULT_STALE_JOB_THRESHOLD_HOURS = 2


async def enqueue_single_fact_check_chunk(
    fact_check_id: UUID,
    community_server_id: UUID | None = None,
    use_dbos: bool | None = None,
) -> bool:
    """Enqueue a single fact-check item for chunking via DBOS.

    This is the preferred entry point for single-item chunking operations.
    Always uses DBOS workflows (TaskIQ support has been removed).

    Args:
        fact_check_id: UUID of the FactCheckItem to process
        community_server_id: Optional community server for LLM credentials
        use_dbos: Deprecated parameter, kept for API compatibility. Logs warning if False.

    Returns:
        True if successfully enqueued, False on failure
    """
    if use_dbos is False:
        logger.warning(
            "use_dbos=False is deprecated; TaskIQ support removed. Using DBOS.",
            extra={"fact_check_id": str(fact_check_id)},
        )

    from src.dbos_workflows.rechunk_workflow import (  # noqa: PLC0415
        enqueue_single_fact_check_chunk as dbos_enqueue,
    )

    workflow_id = await dbos_enqueue(
        fact_check_id=fact_check_id,
        community_server_id=community_server_id,
    )

    if workflow_id:
        logger.info(
            "Enqueued single fact-check chunk via DBOS",
            extra={
                "fact_check_id": str(fact_check_id),
                "workflow_id": workflow_id,
            },
        )
        return True

    logger.warning(
        "Failed to enqueue single fact-check chunk via DBOS",
        extra={"fact_check_id": str(fact_check_id)},
    )
    return False


DEFAULT_STUCK_JOB_THRESHOLD_MINUTES = 30

ALL_BATCH_JOB_TYPES = [
    BULK_APPROVAL_JOB_TYPE,
    IMPORT_JOB_TYPE,
    PROMOTION_JOB_TYPE,
    RECHUNK_FACT_CHECK_JOB_TYPE,
    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
    SCRAPE_JOB_TYPE,
]


@dataclass
class StuckJobInfo:
    """Information about a batch job that appears to be stuck."""

    job_id: UUID
    job_type: str
    status: str
    stuck_duration_seconds: float
    updated_at: datetime


async def get_stuck_jobs_info(
    session: AsyncSession,
    threshold_minutes: int = DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
) -> list[StuckJobInfo]:
    """
    Query jobs stuck in PENDING/IN_PROGRESS beyond threshold.

    Args:
        session: SQLAlchemy async session
        threshold_minutes: Minutes after which a non-terminal job is considered stuck.
            Defaults to 30 minutes.

    Returns:
        List of StuckJobInfo for jobs that haven't updated within the threshold.
    """
    cutoff_time = datetime.now(UTC) - timedelta(minutes=threshold_minutes)

    query = select(BatchJob).where(
        BatchJob.job_type.in_(ALL_BATCH_JOB_TYPES),
        or_(
            BatchJob.status == BatchJobStatus.PENDING.value,
            BatchJob.status == BatchJobStatus.IN_PROGRESS.value,
        ),
        BatchJob.updated_at < cutoff_time,
    )
    result = await session.execute(query)
    stuck_jobs = list(result.scalars().all())

    now = datetime.now(UTC)
    result_list: list[StuckJobInfo] = []
    for job in stuck_jobs:
        reference_time = job.updated_at or job.created_at
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=UTC)
        result_list.append(
            StuckJobInfo(
                job_id=job.id,
                job_type=job.job_type,
                status=job.status,
                stuck_duration_seconds=(now - reference_time).total_seconds(),
                updated_at=reference_time,
            )
        )
    return result_list


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
    hash_bytes = hashlib.md5(job_type.encode(), usedforsecurity=False).digest()[:8]
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
        use_dbos: bool | None = None,
    ) -> BatchJob:
        """
        Start a fact check rechunk job using DBOS workflow.

        Checks for active jobs first, then creates a BatchJob and dispatches
        the DBOS workflow.

        Note:
            As of TASK-1056, all fact_check rechunk operations use DBOS exclusively.
            The use_dbos parameter is retained for API compatibility but is ignored.

        Args:
            community_server_id: Community server ID for LLM credentials (None for global)
            batch_size: Number of items to process per batch
            use_dbos: Deprecated, ignored. DBOS is always used.

        Returns:
            The created and started BatchJob

        Raises:
            ActiveJobExistsError: If a fact check rechunk job is already active
        """
        if use_dbos is False:
            logger.warning("use_dbos=False is deprecated for fact_check rechunk; using DBOS anyway")

        return await self._start_dbos_fact_check_rechunk_job(
            community_server_id=community_server_id,
            batch_size=batch_size,
        )

    async def _start_dbos_fact_check_rechunk_job(
        self,
        community_server_id: UUID | None,
        batch_size: int = 100,
    ) -> BatchJob:
        """Start fact check rechunk job using DBOS workflow."""
        await self._check_no_active_job(RECHUNK_FACT_CHECK_JOB_TYPE)

        from src.dbos_workflows.rechunk_workflow import (  # noqa: PLC0415
            dispatch_dbos_rechunk_workflow,
        )

        logger.info(
            "Using DBOS workflow for rechunk job",
            extra={
                "community_server_id": str(community_server_id) if community_server_id else None,
                "batch_size": batch_size,
            },
        )

        job_id = await dispatch_dbos_rechunk_workflow(
            db=self._session,
            community_server_id=community_server_id,
            batch_size=batch_size,
        )

        job = await self._batch_job_service.get_job(job_id)
        if job is None:
            raise RuntimeError(f"BatchJob {job_id} not found after dispatch")

        return job

    async def start_previously_seen_rechunk_job(
        self,
        community_server_id: UUID,
        batch_size: int = 100,
    ) -> BatchJob:
        """
        Start a previously seen message rechunk job using DBOS workflow.

        Checks for active jobs first, then creates a BatchJob and dispatches
        the DBOS workflow.

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

        from src.dbos_workflows.rechunk_workflow import (  # noqa: PLC0415
            dispatch_dbos_previously_seen_rechunk_workflow,
        )

        logger.info(
            "Using DBOS workflow for previously-seen rechunk job",
            extra={
                "community_server_id": str(community_server_id),
                "batch_size": batch_size,
            },
        )

        job_id = await dispatch_dbos_previously_seen_rechunk_workflow(
            db=self._session,
            community_server_id=community_server_id,
            batch_size=batch_size,
        )

        job = await self._batch_job_service.get_job(job_id)
        if job is None:
            raise RuntimeError(f"BatchJob {job_id} not found after dispatch")

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
            BatchJob.job_type.in_(ALL_BATCH_JOB_TYPES),
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
                batch_job_stale_cleanup_total.labels(
                    job_type=job.job_type,
                    instance_id=settings.INSTANCE_ID,
                ).inc()

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
