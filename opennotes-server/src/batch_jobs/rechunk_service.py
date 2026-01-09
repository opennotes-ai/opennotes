"""
Rechunk-specific batch job service.

Provides high-level operations for creating and managing rechunk batch jobs.
This is a thin wrapper around BatchJobService that handles rechunk-specific
logic like counting items and setting up appropriate metadata.
"""

from enum import Enum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.config import settings
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.fact_checking.rechunk_lock import RechunkLockManager
from src.monitoring import get_logger
from src.tasks.rechunk_tasks import (
    process_fact_check_rechunk_task,
    process_previously_seen_rechunk_task,
)

logger = get_logger(__name__)


class RechunkType(str, Enum):
    """Type of rechunk operation."""

    FACT_CHECK = "fact_check"
    PREVIOUSLY_SEEN = "previously_seen"


JOB_TYPE_FACT_CHECK = "rechunk:fact_check"
JOB_TYPE_PREVIOUSLY_SEEN = "rechunk:previously_seen"


class RechunkBatchJobService:
    """
    Service for managing rechunk batch jobs.

    Provides methods to start and manage rechunk operations using the
    BatchJob infrastructure for persistent tracking and progress reporting.
    """

    def __init__(
        self,
        session: AsyncSession,
        lock_manager: RechunkLockManager,
        batch_job_service: BatchJobService | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            session: SQLAlchemy async session for database operations
            lock_manager: Lock manager for preventing concurrent rechunk operations
            batch_job_service: Optional BatchJobService instance (created if not provided)
        """
        self._session = session
        self._lock_manager = lock_manager
        self._batch_job_service = batch_job_service or BatchJobService(session)

    async def start_fact_check_rechunk_job(
        self,
        community_server_id: UUID | None,
        batch_size: int = 100,
    ) -> BatchJob:
        """
        Start a fact check rechunk job.

        Creates a BatchJob, acquires the lock, and dispatches the TaskIQ task.

        Args:
            community_server_id: Community server ID for LLM credentials (None for global)
            batch_size: Number of items to process per batch

        Returns:
            The created and started BatchJob

        Raises:
            RuntimeError: If the lock cannot be acquired
        """
        lock_acquired = await self._lock_manager.acquire_lock("fact_check")
        if not lock_acquired:
            raise RuntimeError(
                "A fact check rechunk operation is already in progress. "
                "Please wait for it to complete before starting a new one."
            )

        try:
            result = await self._session.execute(select(func.count(FactCheckItem.id)))
            total_items = result.scalar_one()

            job = await self._batch_job_service.create_job(
                BatchJobCreate(
                    job_type=JOB_TYPE_FACT_CHECK,
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

            job = await self._batch_job_service.start_job(job.id)
            if job is None:
                raise RuntimeError("Failed to start batch job")

            await self._session.commit()

        except Exception:
            await self._lock_manager.release_lock("fact_check")
            raise

        try:
            await process_fact_check_rechunk_task.kiq(
                job_id=str(job.id),
                community_server_id=str(community_server_id) if community_server_id else None,
                batch_size=batch_size,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
            )
        except Exception:
            await self._lock_manager.release_lock("fact_check")
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

        Creates a BatchJob, acquires the lock, and dispatches the TaskIQ task.

        Args:
            community_server_id: Community server ID for LLM credentials
            batch_size: Number of items to process per batch

        Returns:
            The created and started BatchJob

        Raises:
            RuntimeError: If the lock cannot be acquired
        """
        lock_acquired = await self._lock_manager.acquire_lock(
            "previously_seen", str(community_server_id)
        )
        if not lock_acquired:
            raise RuntimeError(
                f"A previously seen message rechunk operation is already in progress "
                f"for community {community_server_id}. Please wait for it to complete."
            )

        try:
            result = await self._session.execute(
                select(func.count(PreviouslySeenMessage.id)).where(
                    PreviouslySeenMessage.community_server_id == community_server_id
                )
            )
            total_items = result.scalar_one()

            job = await self._batch_job_service.create_job(
                BatchJobCreate(
                    job_type=JOB_TYPE_PREVIOUSLY_SEEN,
                    total_tasks=total_items,
                    metadata={
                        "community_server_id": str(community_server_id),
                        "batch_size": batch_size,
                        "chunk_type": RechunkType.PREVIOUSLY_SEEN.value,
                    },
                )
            )

            job = await self._batch_job_service.start_job(job.id)
            if job is None:
                raise RuntimeError("Failed to start batch job")

            await self._session.commit()

        except Exception:
            await self._lock_manager.release_lock("previously_seen", str(community_server_id))
            raise

        try:
            await process_previously_seen_rechunk_task.kiq(
                job_id=str(job.id),
                community_server_id=str(community_server_id),
                batch_size=batch_size,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
            )
        except Exception:
            await self._lock_manager.release_lock("previously_seen", str(community_server_id))
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
        Cancel a rechunk job and release its lock.

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

        if chunk_type == RechunkType.FACT_CHECK.value:
            await self._lock_manager.release_lock("fact_check")
        elif chunk_type == RechunkType.PREVIOUSLY_SEEN.value and community_server_id:
            await self._lock_manager.release_lock("previously_seen", community_server_id)

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
