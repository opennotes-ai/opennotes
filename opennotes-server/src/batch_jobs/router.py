"""API endpoints for batch job management.

Provides REST endpoints for creating, monitoring, and managing batch jobs.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.batch_jobs.models import BatchJobStatus
from src.batch_jobs.progress_tracker import get_batch_job_progress_tracker
from src.batch_jobs.schemas import (
    BatchJobCreate,
    BatchJobProgress,
    BatchJobResponse,
)
from src.batch_jobs.service import BatchJobService, InvalidStateTransitionError
from src.database import get_db
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/batch-jobs",
    tags=["batch-jobs"],
)


def get_batch_job_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchJobService:
    """Get BatchJobService with injected dependencies."""
    return BatchJobService(db)


@router.post(
    "",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new batch job",
    description="Create a new batch job entry. The job starts in PENDING status. "
    "Use this to register a job before dispatching tasks.",
)
async def create_batch_job(
    job_data: BatchJobCreate,
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Create a new batch job.

    Args:
        job_data: Job creation parameters.
        service: Batch job service.
        current_user: Authenticated user.

    Returns:
        The created batch job.
    """
    logger.info(
        "Creating batch job",
        extra={
            "user_id": str(current_user.id),
            "job_type": job_data.job_type,
            "total_tasks": job_data.total_tasks,
        },
    )

    job = await service.create_job(job_data)
    return BatchJobResponse.model_validate(job)


@router.get(
    "/{job_id}",
    response_model=BatchJobResponse,
    summary="Get batch job status",
    description="Get the current status and progress of a batch job.",
)
async def get_batch_job(
    job_id: UUID,
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Get a batch job by ID.

    Args:
        job_id: The job's unique identifier.
        service: Batch job service.
        current_user: Authenticated user.

    Returns:
        The batch job details.

    Raises:
        HTTPException: If job not found.
    """
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {job_id} not found",
        )
    return BatchJobResponse.model_validate(job)


@router.get(
    "/{job_id}/progress",
    response_model=BatchJobProgress,
    summary="Get real-time progress",
    description="Get real-time progress information from Redis cache. "
    "Includes processing rate and ETA when available.",
)
async def get_batch_job_progress(
    job_id: UUID,
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobProgress:
    """Get real-time progress for a batch job.

    Args:
        job_id: The job's unique identifier.
        service: Batch job service.
        current_user: Authenticated user.

    Returns:
        Real-time progress data.

    Raises:
        HTTPException: If job not found or no progress data available.
    """
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {job_id} not found",
        )

    tracker = get_batch_job_progress_tracker()
    progress = await tracker.get_progress(job_id)

    if progress is None:
        return BatchJobProgress(
            job_id=job_id,
            processed_count=job.completed_tasks,
            error_count=job.failed_tasks,
            current_item=None,
            rate=0.0,
            eta_seconds=None,
        )

    return BatchJobProgress(
        job_id=job_id,
        processed_count=progress.processed_count,
        error_count=progress.error_count,
        current_item=progress.current_item,
        rate=progress.rate,
        eta_seconds=progress.eta_seconds,
    )


@router.get(
    "",
    response_model=list[BatchJobResponse],
    summary="List batch jobs",
    description="List batch jobs with optional filters for job type and status.",
)
async def list_batch_jobs(
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    job_type: Annotated[
        str | None,
        Query(description="Filter by job type"),
    ] = None,
    job_status: Annotated[
        BatchJobStatus | None,
        Query(alias="status", description="Filter by job status"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of jobs to return"),
    ] = 50,
) -> list[BatchJobResponse]:
    """List batch jobs with optional filters.

    Args:
        service: Batch job service.
        current_user: Authenticated user.
        job_type: Filter by job type (e.g., 'fact_check_import').
        job_status: Filter by status (e.g., 'in_progress').
        limit: Maximum number of jobs to return.

    Returns:
        List of matching batch jobs.
    """
    jobs = await service.list_jobs(
        job_type=job_type,
        status=job_status,
        limit=limit,
    )
    return [BatchJobResponse.model_validate(job) for job in jobs]


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a batch job",
    description="Cancel a running or pending batch job. "
    "Jobs in terminal states (completed, failed, cancelled) cannot be cancelled.",
)
async def cancel_batch_job(
    job_id: UUID,
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> None:
    """Cancel a batch job.

    Args:
        job_id: The job's unique identifier.
        service: Batch job service.
        current_user: Authenticated user.

    Raises:
        HTTPException: If job not found or cannot be cancelled.
    """
    logger.info(
        "Cancelling batch job",
        extra={
            "user_id": str(current_user.id),
            "job_id": str(job_id),
        },
    )

    try:
        job = await service.cancel_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch job {job_id} not found",
            )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel job: {e}",
        )
