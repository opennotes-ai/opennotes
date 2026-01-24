"""
Service layer for batch job management.

Provides high-level operations for creating, updating, and querying batch jobs
with coordinated database and Redis progress tracking.

NOTE: For detailed task-level inspection beyond batch job aggregates, consider
integrating with taskiq-dashboard (https://github.com/taskiq-python/taskiq-dashboard).
This provides a web UI for viewing individual task states, retries, and errors
which complements the aggregate tracking provided by BatchJob.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob, BatchJobStatus
from src.batch_jobs.progress_tracker import (
    BatchJobProgressTracker,
    get_batch_job_progress_tracker,
)
from src.batch_jobs.schemas import BatchJobCreate
from src.monitoring import get_logger

logger = get_logger(__name__)


VALID_STATUS_TRANSITIONS: dict[BatchJobStatus, set[BatchJobStatus]] = {
    BatchJobStatus.PENDING: {
        BatchJobStatus.IN_PROGRESS,
        BatchJobStatus.CANCELLED,
        BatchJobStatus.FAILED,
    },
    BatchJobStatus.IN_PROGRESS: {
        BatchJobStatus.COMPLETED,
        BatchJobStatus.FAILED,
        BatchJobStatus.CANCELLED,
    },
    BatchJobStatus.COMPLETED: set(),
    BatchJobStatus.FAILED: set(),
    BatchJobStatus.CANCELLED: set(),
}


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_status: BatchJobStatus, target_status: BatchJobStatus) -> None:
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Invalid state transition from {current_status.value} to {target_status.value}"
        )


class BatchJobService:
    """
    Service for managing batch jobs.

    Coordinates between database persistence and Redis progress tracking
    to provide a unified interface for batch job management.
    """

    def __init__(
        self,
        session: AsyncSession,
        progress_tracker: BatchJobProgressTracker | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            session: SQLAlchemy async session for database operations
            progress_tracker: Optional progress tracker (uses global if not provided)
        """
        self._session = session
        self._progress_tracker = progress_tracker or get_batch_job_progress_tracker()

    async def create_job(self, job_data: BatchJobCreate) -> BatchJob:
        """
        Create a new batch job.

        Args:
            job_data: Job creation data

        Returns:
            The created BatchJob model instance
        """
        job = BatchJob(
            job_type=job_data.job_type,
            total_tasks=job_data.total_tasks,
            metadata_=job_data.metadata_,
            status=BatchJobStatus.PENDING.value,
        )

        self._session.add(job)
        await self._session.flush()

        logger.info(
            "Created batch job",
            extra={
                "job_id": str(job.id),
                "job_type": job.job_type,
                "total_tasks": job.total_tasks,
            },
        )

        return job

    async def get_job(self, job_id: UUID) -> BatchJob | None:
        """
        Get a batch job by ID.

        Args:
            job_id: The job's unique identifier

        Returns:
            The BatchJob if found, None otherwise
        """
        result = await self._session.execute(select(BatchJob).where(BatchJob.id == job_id))
        return result.scalar_one_or_none()

    async def start_job(self, job_id: UUID) -> BatchJob | None:
        """
        Mark a job as in progress and start tracking.

        Args:
            job_id: The job's unique identifier

        Returns:
            The updated BatchJob if found, None otherwise

        Raises:
            InvalidStateTransitionError: If job is not in PENDING status
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        current_status = BatchJobStatus(job.status)
        self._validate_transition(current_status, BatchJobStatus.IN_PROGRESS)

        await self._progress_tracker.start_tracking(job_id)

        job.status = BatchJobStatus.IN_PROGRESS.value
        job.started_at = datetime.now(UTC)

        try:
            await self._session.commit()
        except Exception:
            await self._progress_tracker.stop_tracking(job_id)
            raise

        logger.info(
            "Started batch job",
            extra={
                "job_id": str(job_id),
                "total_tasks": job.total_tasks,
            },
        )

        return job

    async def update_progress(
        self,
        job_id: UUID,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
        current_item: str | None = None,
    ) -> BatchJob | None:
        """
        Update job progress in both database and Redis.

        Args:
            job_id: The job's unique identifier
            completed_tasks: Number of successfully completed tasks
            failed_tasks: Number of failed tasks
            current_item: Description of current item being processed

        Returns:
            The updated BatchJob if found, None otherwise
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        if completed_tasks is not None:
            job.completed_tasks = completed_tasks
        if failed_tasks is not None:
            job.failed_tasks = failed_tasks

        await self._session.flush()

        await self._progress_tracker.update_progress(
            job_id,
            processed_count=completed_tasks,
            error_count=failed_tasks,
            current_item=current_item,
        )

        return job

    async def complete_job(
        self,
        job_id: UUID,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
    ) -> BatchJob | None:
        """
        Mark a job as completed.

        Args:
            job_id: The job's unique identifier
            completed_tasks: Final count of completed tasks
            failed_tasks: Final count of failed tasks

        Returns:
            The updated BatchJob if found, None otherwise

        Raises:
            InvalidStateTransitionError: If job is not in IN_PROGRESS status
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        current_status = BatchJobStatus(job.status)
        self._validate_transition(current_status, BatchJobStatus.COMPLETED)

        job.status = BatchJobStatus.COMPLETED.value
        job.completed_at = datetime.now(UTC)

        if completed_tasks is not None:
            job.completed_tasks = completed_tasks
        if failed_tasks is not None:
            job.failed_tasks = failed_tasks

        await self._session.commit()
        await self._progress_tracker.stop_tracking(job_id)

        logger.info(
            "Completed batch job",
            extra={
                "job_id": str(job_id),
                "completed_tasks": job.completed_tasks,
                "failed_tasks": job.failed_tasks,
            },
        )

        return job

    async def fail_job(
        self,
        job_id: UUID,
        error_summary: dict[str, Any] | None = None,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
    ) -> BatchJob | None:
        """
        Mark a job as failed.

        Args:
            job_id: The job's unique identifier
            error_summary: Summary of errors that caused failure
            completed_tasks: Count of tasks completed before failure
            failed_tasks: Count of failed tasks

        Returns:
            The updated BatchJob if found, None otherwise

        Raises:
            InvalidStateTransitionError: If job is in terminal state
        """
        job = await self.get_job(job_id)
        if job is None:
            logger.error(
                "Job not found for fail_job",
                extra={"job_id": str(job_id)},
            )
            return None

        current_status = BatchJobStatus(job.status)
        self._validate_transition(current_status, BatchJobStatus.FAILED)

        job.status = BatchJobStatus.FAILED.value
        job.completed_at = datetime.now(UTC)
        job.error_summary = error_summary

        if completed_tasks is not None:
            job.completed_tasks = completed_tasks
        if failed_tasks is not None:
            job.failed_tasks = failed_tasks

        await self._session.commit()
        await self._progress_tracker.stop_tracking(job_id)

        logger.error(
            "Batch job failed",
            extra={
                "job_id": str(job_id),
                "completed_tasks": job.completed_tasks,
                "failed_tasks": job.failed_tasks,
                "error_summary": error_summary,
            },
        )

        return job

    async def cancel_job(self, job_id: UUID) -> BatchJob | None:
        """
        Cancel a running job.

        Args:
            job_id: The job's unique identifier

        Returns:
            The updated BatchJob if found, None otherwise

        Raises:
            InvalidStateTransitionError: If job is in terminal state
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        current_status = BatchJobStatus(job.status)
        self._validate_transition(current_status, BatchJobStatus.CANCELLED)

        job.status = BatchJobStatus.CANCELLED.value
        job.completed_at = datetime.now(UTC)

        await self._session.commit()
        await self._progress_tracker.stop_tracking(job_id)

        logger.info(
            "Cancelled batch job",
            extra={
                "job_id": str(job_id),
                "completed_tasks": job.completed_tasks,
            },
        )

        return job

    async def list_jobs(
        self,
        job_type: str | None = None,
        status: BatchJobStatus | None = None,
        limit: int = 100,
    ) -> list[BatchJob]:
        """
        List batch jobs with optional filters.

        Args:
            job_type: Filter by job type
            status: Filter by status
            limit: Maximum number of jobs to return

        Returns:
            List of matching BatchJob instances
        """
        query = select(BatchJob)

        if job_type:
            query = query.where(BatchJob.job_type == job_type)
        if status:
            query = query.where(BatchJob.status == status.value)

        query = query.order_by(BatchJob.created_at.desc()).limit(limit)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    def _validate_transition(
        self,
        current_status: BatchJobStatus,
        target_status: BatchJobStatus,
    ) -> None:
        """
        Validate that a status transition is allowed.

        Args:
            current_status: Current job status
            target_status: Target status to transition to

        Raises:
            InvalidStateTransitionError: If the transition is not allowed
        """
        if current_status == target_status:
            return

        valid_targets = VALID_STATUS_TRANSITIONS.get(current_status, set())
        if target_status not in valid_targets:
            raise InvalidStateTransitionError(current_status, target_status)
