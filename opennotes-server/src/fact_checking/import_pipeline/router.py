"""API endpoint for fact-check bureau import.

Exposes the import pipeline functionality via REST API for programmatic access.
Import operations run asynchronously via BatchJob infrastructure.

Concurrent job prevention uses dual-layer defense:
1. DistributedRateLimitMiddleware: Blocks duplicate requests at API boundary
2. Service-level ActiveJobExistsError: Database check before job creation

Both layers return HTTP 429 when a job of the same type is already active.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.batch_jobs import ActiveJobExistsError
from src.batch_jobs.import_service import ImportBatchJobService
from src.batch_jobs.schemas import BatchJobResponse
from src.common.base_schemas import StrictInputSchema
from src.database import get_db
from src.fact_checking.import_pipeline.scrape_tasks import enqueue_scrape_batch
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/fact-checking/import",
    tags=["fact-checking-import"],
)


class ImportFactCheckBureauRequest(StrictInputSchema):
    """Request parameters for fact-check bureau import."""

    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Batch size for import operations",
    )
    dry_run: bool = Field(
        default=False,
        description="Validate only, do not insert into database",
    )
    enqueue_scrapes: bool = Field(
        default=False,
        description="Enqueue scrape tasks for pending candidates after import completes",
    )


class BatchProcessingRequest(StrictInputSchema):
    """Request parameters for batch processing operations without rate limiting (e.g., promote)."""

    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of candidates to process in this batch",
    )
    dry_run: bool = Field(
        default=False,
        description="Count candidates only, do not perform operation",
    )


class ScrapeProcessingRequest(BatchProcessingRequest):
    """Request parameters for scraping operations with rate limiting support."""

    base_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=30.0,
        description="Minimum delay in seconds between requests to the same domain",
    )


class EnqueueScrapeResponse(BaseModel):
    """Response for enqueue scrapes operation."""

    model_config = ConfigDict(from_attributes=True)

    enqueued: int = Field(description="Number of scrape tasks enqueued")


def get_import_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportBatchJobService:
    """Get ImportBatchJobService with injected dependencies."""
    return ImportBatchJobService(db)


@router.post(
    "/fact-check-bureau",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start fact-check-bureau import job",
    description="Start an asynchronous import of the fact-check-bureau dataset from "
    "HuggingFace. Returns immediately with a BatchJob that can be polled for status. "
    "Use GET /api/v1/batch-jobs/{job_id} to check progress.",
    responses={
        429: {"description": "An import job is already in progress (rate limited)"},
    },
)
async def import_fact_check_bureau_endpoint(
    request: ImportFactCheckBureauRequest,
    service: Annotated[ImportBatchJobService, Depends(get_import_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Start a fact-check-bureau import job.

    Requires authentication via API key (X-API-Key header) or Bearer token.

    This endpoint returns immediately with a BatchJob in PENDING status.
    The actual import runs asynchronously as a background task.

    Note: Concurrent job rate limiting is handled by DistributedRateLimitMiddleware.
    If an import job is already running, the middleware returns 429 Too Many Requests.

    Poll the job status at:
    - GET /api/v1/batch-jobs/{job_id} - Full job status
    - GET /api/v1/batch-jobs/{job_id}/progress - Real-time progress

    Args:
        request: Import configuration parameters.
        service: Import batch job service.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        BatchJobResponse with job ID for status polling.
    """
    logger.info(
        "Starting import job",
        extra={
            "user_id": str(current_user.id),
            "batch_size": request.batch_size,
            "dry_run": request.dry_run,
            "enqueue_scrapes": request.enqueue_scrapes,
        },
    )

    job = await service.start_import_job(
        batch_size=request.batch_size,
        dry_run=request.dry_run,
        enqueue_scrapes=request.enqueue_scrapes,
        user_id=str(current_user.id),
    )

    logger.info(
        "Import job created",
        extra={
            "job_id": str(job.id),
            "user_id": str(current_user.id),
        },
    )

    return BatchJobResponse.model_validate(job)


@router.post(
    "/enqueue-scrapes",
    response_model=EnqueueScrapeResponse,
    status_code=status.HTTP_200_OK,
    summary="Enqueue scrape tasks for pending candidates",
    description="Enqueue scrape tasks for candidates with status=pending. "
    "This is a synchronous operation that returns the count of enqueued tasks.",
)
async def enqueue_scrapes_endpoint(
    request: ScrapeProcessingRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> EnqueueScrapeResponse:
    """Enqueue scrape tasks for pending candidates.

    Finds candidates with status=pending and no content,
    then enqueues scrape tasks for each.

    Args:
        request: Scrape configuration parameters including batch_size and base_delay.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        Count of enqueued tasks.
    """
    logger.info(
        "Enqueue scrapes request",
        extra={
            "user_id": str(current_user.id),
            "batch_size": request.batch_size,
            "base_delay": request.base_delay,
        },
    )

    result = await enqueue_scrape_batch(
        batch_size=request.batch_size,
        base_delay=request.base_delay,
    )

    logger.info(
        "Scrape tasks enqueued",
        extra={
            "enqueued": result["enqueued"],
        },
    )

    return EnqueueScrapeResponse(enqueued=result["enqueued"])


@router.post(
    "/scrape-candidates",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start candidate scraping batch job",
    description="Start an asynchronous batch job to scrape content for pending candidates. "
    "Returns immediately with a BatchJob that can be polled for status. "
    "Use GET /api/v1/batch-jobs/{job_id} to check progress.",
    responses={
        429: {"description": "A scrape job is already in progress (rate limited)"},
    },
)
async def scrape_candidates_endpoint(
    request: ScrapeProcessingRequest,
    service: Annotated[ImportBatchJobService, Depends(get_import_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Start a candidate scraping batch job.

    Requires authentication via API key (X-API-Key header) or Bearer token.

    This endpoint returns immediately with a BatchJob in PENDING status.
    The actual scraping runs asynchronously as a background task.

    Concurrent job prevention uses dual-layer defense:
    1. DistributedRateLimitMiddleware blocks duplicate requests at API boundary
    2. Service-level ActiveJobExistsError provides database-level check

    Both return HTTP 429 when a scrape job is already active.

    Poll the job status at:
    - GET /api/v1/batch-jobs/{job_id} - Full job status
    - GET /api/v1/batch-jobs/{job_id}/progress - Real-time progress

    Args:
        request: Scrape configuration parameters.
        service: Import batch job service.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        BatchJobResponse with job ID for status polling.

    Raises:
        HTTPException: 429 if a scrape job is already active.
    """
    logger.info(
        "Starting scrape candidates job",
        extra={
            "user_id": str(current_user.id),
            "batch_size": request.batch_size,
            "dry_run": request.dry_run,
        },
    )

    try:
        job = await service.start_scrape_job(
            batch_size=request.batch_size,
            dry_run=request.dry_run,
            user_id=str(current_user.id),
            base_delay=request.base_delay,
        )
    except ActiveJobExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )

    logger.info(
        "Scrape candidates job created",
        extra={
            "job_id": str(job.id),
            "user_id": str(current_user.id),
        },
    )

    return BatchJobResponse.model_validate(job)


@router.post(
    "/promote-candidates",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start candidate promotion batch job",
    description="Start an asynchronous batch job to promote scraped candidates to fact-check items. "
    "Returns immediately with a BatchJob that can be polled for status. "
    "Use GET /api/v1/batch-jobs/{job_id} to check progress.",
    responses={
        429: {"description": "A promotion job is already in progress (rate limited)"},
    },
)
async def promote_candidates_endpoint(
    request: BatchProcessingRequest,
    service: Annotated[ImportBatchJobService, Depends(get_import_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Start a candidate promotion batch job.

    Requires authentication via API key (X-API-Key header) or Bearer token.

    This endpoint returns immediately with a BatchJob in PENDING status.
    The actual promotion runs asynchronously as a background task.

    Concurrent job prevention uses dual-layer defense:
    1. DistributedRateLimitMiddleware blocks duplicate requests at API boundary
    2. Service-level ActiveJobExistsError provides database-level check

    Both return HTTP 429 when a promotion job is already active.

    Poll the job status at:
    - GET /api/v1/batch-jobs/{job_id} - Full job status
    - GET /api/v1/batch-jobs/{job_id}/progress - Real-time progress

    Args:
        request: Promotion configuration parameters.
        service: Import batch job service.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        BatchJobResponse with job ID for status polling.

    Raises:
        HTTPException: 429 if a promotion job is already active.
    """
    logger.info(
        "Starting promote candidates job",
        extra={
            "user_id": str(current_user.id),
            "batch_size": request.batch_size,
            "dry_run": request.dry_run,
        },
    )

    try:
        job = await service.start_promotion_job(
            batch_size=request.batch_size,
            dry_run=request.dry_run,
            user_id=str(current_user.id),
        )
    except ActiveJobExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )

    logger.info(
        "Promote candidates job created",
        extra={
            "job_id": str(job.id),
            "user_id": str(current_user.id),
        },
    )

    return BatchJobResponse.model_validate(job)
