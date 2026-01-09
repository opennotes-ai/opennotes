"""
API router for chunk re-embedding operations.

This module provides endpoints for bulk re-chunking and re-embedding of:
- FactCheckItem content
- PreviouslySeenMessage content

These endpoints are useful for:
- Re-processing content after embedding model changes
- Migrating to chunk-based embeddings from full-document embeddings
- Refreshing embeddings with updated chunking parameters

Rate Limiting and Concurrency Control:
- Endpoints are rate-limited to 1 request per minute per user
- Only one rechunk operation can run per resource (table/community) at a time
- Returns 409 Conflict if an operation is already in progress

Status Tracking:
- Each rechunk operation returns a BatchJob for status polling
- Use GET /batch-jobs/{job_id} to check progress
- Job status is stored in PostgreSQL with Redis for real-time progress
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    _get_profile_id_from_user,
    verify_community_admin_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.batch_jobs.models import BatchJobStatus
from src.batch_jobs.rechunk_service import (
    JOB_TYPE_FACT_CHECK,
    JOB_TYPE_PREVIOUSLY_SEEN,
    RechunkBatchJobService,
)
from src.batch_jobs.schemas import BatchJobResponse
from src.batch_jobs.service import BatchJobService, InvalidStateTransitionError
from src.cache.redis_client import redis_client
from src.database import get_db
from src.fact_checking.rechunk_lock import RechunkLockManager
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.users.models import User
from src.users.profile_crud import get_profile_by_id

logger = get_logger(__name__)


class _GlobalRechunkLockManager(RechunkLockManager):
    """Lock manager that uses the global redis_client as fallback."""

    @property
    def redis(self):
        if self._redis is not None:
            return self._redis
        return redis_client.client


rechunk_lock_manager = _GlobalRechunkLockManager()

router = APIRouter(prefix="/chunks", tags=["chunks"])


def get_rechunk_batch_job_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RechunkBatchJobService:
    """Get RechunkBatchJobService with injected dependencies."""
    batch_job_service = BatchJobService(db)
    return RechunkBatchJobService(db, rechunk_lock_manager, batch_job_service)


def get_batch_job_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchJobService:
    """Get BatchJobService with injected dependencies."""
    return BatchJobService(db)


@router.get(
    "/jobs/{job_id}",
    response_model=BatchJobResponse,
    summary="Get rechunk job status",
    description="Retrieve the current status and progress of a rechunk batch job. "
    "If the job is associated with a community server, requires admin or moderator access. "
    "If the job was started without a community server (global credentials), only requires authentication.",
    responses={
        403: {"description": "User lacks admin/moderator permission for the job's community"},
        404: {"description": "Job not found or not a rechunk job"},
    },
)
async def get_rechunk_job_status(
    request: Request,
    job_id: UUID,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
) -> BatchJobResponse:
    """
    Get the status of a rechunk batch job.

    Args:
        request: FastAPI request object
        job_id: The unique identifier of the job
        user: Authenticated user
        db: Database session
        service: Batch job service

    Returns:
        Job status including progress metrics

    Raises:
        HTTPException: 403 if user lacks admin/moderator permission for the job's community
        HTTPException: 404 if job not found
    """
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.job_type not in (JOB_TYPE_FACT_CHECK, JOB_TYPE_PREVIOUSLY_SEEN):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} is not a rechunk job",
        )

    metadata = job.metadata_ or {}
    community_server_id = metadata.get("community_server_id")

    if community_server_id is not None:
        await verify_community_admin_by_uuid(
            community_server_id=UUID(community_server_id),
            current_user=user,
            db=db,
            request=request,
        )

    return BatchJobResponse.model_validate(job)


@router.post(
    "/fact-check/rechunk",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Re-chunk and re-embed fact check items",
    description="Initiates a background task to re-chunk and re-embed all fact check items. "
    "Useful for updating embeddings after model changes or migration to chunk-based embeddings. "
    "When community_server_id is provided, requires admin or moderator access. "
    "When not provided, uses global LLM credentials and only requires authentication. "
    "Rate limited to 1 request per minute. Returns 409 if operation already in progress.",
    responses={
        403: {"description": "User lacks admin/moderator permission for the community"},
        409: {"description": "A rechunk operation is already in progress"},
    },
)
@limiter.limit("1/minute")
async def rechunk_fact_check_items(
    request: Request,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[RechunkBatchJobService, Depends(get_rechunk_batch_job_service)],
    community_server_id: UUID | None = Query(
        None,
        description="Community server ID for LLM credentials (optional, uses global fallback if not provided)",
    ),
    batch_size: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch (1-1000)",
    ),
) -> BatchJobResponse:
    """
    Re-chunk and re-embed all fact check items.

    This endpoint initiates a background task that:
    1. Queries all FactCheckItem records
    2. Clears existing FactCheckChunk entries for each item
    3. Re-chunks the content using ChunkingService
    4. Generates new embeddings via LLMService
    5. Creates new FactCheckChunk entries

    When community_server_id is provided, requires admin or moderator access
    to that community. When not provided, uses global LLM credentials.
    Only one fact check rechunk operation can run at a time.

    Args:
        request: FastAPI request object
        user: Authenticated user (via API key or JWT)
        db: Database session
        service: Rechunk batch job service
        community_server_id: Community server UUID for LLM credentials (optional)
        batch_size: Number of items to process per batch (default 100, max 1000)

    Returns:
        BatchJobResponse with job_id for status polling

    Raises:
        HTTPException: 403 if user lacks admin/moderator permission for the community
        HTTPException: 409 if a fact check rechunk operation is already in progress
    """
    if community_server_id is not None:
        await verify_community_admin_by_uuid(
            community_server_id=community_server_id,
            current_user=user,
            db=db,
            request=request,
        )

    try:
        job = await service.start_fact_check_rechunk_job(
            community_server_id=community_server_id,
            batch_size=batch_size,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    logger.info(
        "Started fact check rechunking job",
        extra={
            "job_id": str(job.id),
            "user_id": str(user.id),
            "community_server_id": str(community_server_id) if community_server_id else None,
            "batch_size": batch_size,
            "total_items": job.total_tasks,
        },
    )

    return BatchJobResponse.model_validate(job)


@router.post(
    "/previously-seen/rechunk",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Re-chunk and re-embed previously seen messages",
    description="Initiates a background task to re-chunk and re-embed previously seen messages "
    "for the specified community. Useful for updating embeddings after model changes or "
    "migration to chunk-based embeddings. Requires admin or moderator access to the community server. "
    "Rate limited to 1 request per minute. Returns 409 if operation already in progress for this community.",
    responses={
        403: {"description": "User lacks admin/moderator permission for the community"},
        409: {"description": "A rechunk operation is already in progress for this community"},
    },
)
@limiter.limit("1/minute")
async def rechunk_previously_seen_messages(
    request: Request,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[RechunkBatchJobService, Depends(get_rechunk_batch_job_service)],
    community_server_id: UUID = Query(
        ..., description="Community server ID for filtering and LLM credentials"
    ),
    batch_size: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch (1-1000)",
    ),
) -> BatchJobResponse:
    """
    Re-chunk and re-embed previously seen messages for a community.

    This endpoint initiates a background task that:
    1. Queries PreviouslySeenMessage records for the specified community
    2. Clears existing PreviouslySeenChunk entries for each message
    3. Re-chunks the content (from metadata) using ChunkingService
    4. Generates new embeddings via LLMService
    5. Creates new PreviouslySeenChunk entries

    Requires admin or moderator access to the community server.
    Only one rechunk operation can run per community at a time.

    Args:
        request: FastAPI request object
        user: Authenticated user (via API key or JWT)
        db: Database session
        service: Rechunk batch job service
        community_server_id: Community server UUID for filtering and LLM credentials
        batch_size: Number of items to process per batch (default 100, max 1000)

    Returns:
        BatchJobResponse with job_id for status polling

    Raises:
        HTTPException: 403 if user lacks admin/moderator permission for the community
        HTTPException: 409 if a rechunk operation is already in progress for this community
    """
    await verify_community_admin_by_uuid(
        community_server_id=community_server_id,
        current_user=user,
        db=db,
        request=request,
    )

    try:
        job = await service.start_previously_seen_rechunk_job(
            community_server_id=community_server_id,
            batch_size=batch_size,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    logger.info(
        "Started previously seen message rechunking job",
        extra={
            "job_id": str(job.id),
            "user_id": str(user.id),
            "community_server_id": str(community_server_id),
            "batch_size": batch_size,
            "total_items": job.total_tasks,
        },
    )

    return BatchJobResponse.model_validate(job)


@router.get(
    "/jobs",
    response_model=list[BatchJobResponse],
    summary="List all rechunk jobs",
    description="List all rechunk batch jobs. Optionally filter by status. "
    "Requires authentication.",
)
async def list_rechunk_jobs(
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    service: Annotated[BatchJobService, Depends(get_batch_job_service)],
    job_status: BatchJobStatus | None = Query(
        None,
        alias="status",
        description="Filter by job status (pending, in_progress, completed, failed, cancelled)",
    ),
) -> list[BatchJobResponse]:
    """
    List all rechunk batch jobs.

    Args:
        user: Authenticated user
        service: Batch job service
        job_status: Optional status filter

    Returns:
        List of rechunk batch jobs
    """
    fact_check_jobs = await service.list_jobs(
        job_type=JOB_TYPE_FACT_CHECK,
        status=job_status,
    )
    previously_seen_jobs = await service.list_jobs(
        job_type=JOB_TYPE_PREVIOUSLY_SEEN,
        status=job_status,
    )

    all_jobs = fact_check_jobs + previously_seen_jobs
    all_jobs.sort(key=lambda j: j.created_at, reverse=True)

    return [BatchJobResponse.model_validate(job) for job in all_jobs]


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a rechunk job",
    description="Cancel a rechunk job and release its lock. "
    "Jobs in terminal states (completed, failed, cancelled) cannot be cancelled. "
    "Requires admin/moderator permission for the job's community, "
    "or OpenNotes admin for global jobs.",
    responses={
        403: {
            "description": "User lacks permission for the job's community or is not an OpenNotes admin"
        },
        404: {"description": "Job not found or not a rechunk job"},
        409: {"description": "Job is in terminal state and cannot be cancelled"},
    },
)
async def cancel_rechunk_job(
    request: Request,
    job_id: UUID,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[RechunkBatchJobService, Depends(get_rechunk_batch_job_service)],
    batch_job_service: Annotated[BatchJobService, Depends(get_batch_job_service)],
) -> None:
    """
    Cancel a rechunk job and release its lock.

    Args:
        request: FastAPI request object
        job_id: The unique identifier of the job to cancel
        user: Authenticated user
        db: Database session
        service: Rechunk batch job service
        batch_job_service: Batch job service for looking up job

    Raises:
        HTTPException: 403 if user lacks permission
        HTTPException: 404 if job not found
        HTTPException: 409 if job is in terminal state
    """
    job = await batch_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.job_type not in (JOB_TYPE_FACT_CHECK, JOB_TYPE_PREVIOUSLY_SEEN):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} is not a rechunk job",
        )

    metadata = job.metadata_ or {}
    community_server_id = metadata.get("community_server_id")

    if community_server_id is not None:
        await verify_community_admin_by_uuid(
            community_server_id=UUID(community_server_id),
            current_user=user,
            db=db,
            request=request,
        )
    elif not getattr(user, "is_service_account", False):
        profile_id = await _get_profile_id_from_user(db, user)
        profile = await get_profile_by_id(db, profile_id) if profile_id else None
        if not profile or not profile.is_opennotes_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only OpenNotes admins or service accounts can cancel global jobs",
            )

    try:
        cancelled_job = await service.cancel_rechunk_job(job_id)
        if cancelled_job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel job: {e}",
        )

    logger.info(
        "Cancelled rechunk job",
        extra={
            "job_id": str(job_id),
            "user_id": str(user.id),
            "job_type": job.job_type,
            "community_server_id": community_server_id,
        },
    )
