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
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.constants import (
    PROMOTION_JOB_TYPE,
    RECHUNK_FACT_CHECK_JOB_TYPE,
    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
    SCRAPE_JOB_TYPE,
)
from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate, BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.config import settings
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.monitoring import get_logger
from src.tasks.rechunk_tasks import (
    process_fact_check_rechunk_task,
    process_previously_seen_rechunk_task,
)

logger = get_logger(__name__)

DEFAULT_STALE_JOB_THRESHOLD_HOURS = 2


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

        Uses SELECT FOR UPDATE to acquire a row-level lock on any active job found,
        preventing TOCTOU race conditions where concurrent requests could both pass
        the check before either creates a new job.

        Args:
            job_type: The job type to check

        Raises:
            ActiveJobExistsError: If an active job exists for this type
        """
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

        Args:
            community_server_id: Community server ID for LLM credentials
            batch_size: Number of items to process per batch

        Returns:
            The created and started BatchJob

        Raises:
            ActiveJobExistsError: If a previously seen rechunk job is already active
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
    ) -> list[BatchJob]:
        """
        Mark stale jobs as failed.

        Jobs are considered stale if they have been in PENDING or IN_PROGRESS status
        for longer than the specified threshold. This recovers from scenarios like
        worker crashes or network failures that left jobs in a non-terminal state.

        Args:
            stale_threshold_hours: Hours after which a non-terminal job is considered
                stale. Defaults to 2 hours.

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
            BatchJob.created_at < cutoff_time,
        )
        result = await self._session.execute(query)
        stale_jobs = list(result.scalars().all())

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
