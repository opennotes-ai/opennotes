"""API endpoint for fact-check bureau import.

Exposes the import pipeline functionality via REST API for programmatic access.
Import operations run asynchronously via BatchJob infrastructure.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.batch_jobs.import_service import ImportBatchJobService
from src.batch_jobs.schemas import BatchJobResponse
from src.database import get_db
from src.fact_checking.import_pipeline.scrape_tasks import enqueue_scrape_batch
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/fact-checking/import",
    tags=["fact-checking-import"],
)


class ImportFactCheckBureauRequest(BaseModel):
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


class ScrapeCandidatesRequest(BaseModel):
    """Request parameters for scraping pending candidates."""

    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of candidates to scrape in this batch",
    )
    dry_run: bool = Field(
        default=False,
        description="Count candidates only, do not perform scraping",
    )


class PromoteCandidatesRequest(BaseModel):
    """Request parameters for promoting scraped candidates."""

    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of candidates to promote in this batch",
    )
    dry_run: bool = Field(
        default=False,
        description="Count candidates only, do not perform promotion",
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
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    batch_size: int = 100,
) -> EnqueueScrapeResponse:
    """Enqueue scrape tasks for pending candidates.

    Finds candidates with status=pending and no content,
    then enqueues scrape tasks for each.

    Args:
        current_user: Authenticated user (via API key or JWT).
        batch_size: Maximum number of candidates to enqueue (default 100).

    Returns:
        Count of enqueued tasks.
    """
    logger.info(
        "Enqueue scrapes request",
        extra={
            "user_id": str(current_user.id),
            "batch_size": batch_size,
        },
    )

    result = await enqueue_scrape_batch(batch_size=batch_size)

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
)
async def scrape_candidates_endpoint(
    request: ScrapeCandidatesRequest,
    service: Annotated[ImportBatchJobService, Depends(get_import_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Start a candidate scraping batch job.

    Requires authentication via API key (X-API-Key header) or Bearer token.

    This endpoint returns immediately with a BatchJob in PENDING status.
    The actual scraping runs asynchronously as a background task.

    Poll the job status at:
    - GET /api/v1/batch-jobs/{job_id} - Full job status
    - GET /api/v1/batch-jobs/{job_id}/progress - Real-time progress

    Args:
        request: Scrape configuration parameters.
        service: Import batch job service.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        BatchJobResponse with job ID for status polling.
    """
    logger.info(
        "Starting scrape candidates job",
        extra={
            "user_id": str(current_user.id),
            "batch_size": request.batch_size,
            "dry_run": request.dry_run,
        },
    )

    job = await service.start_scrape_job(
        batch_size=request.batch_size,
        dry_run=request.dry_run,
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
)
async def promote_candidates_endpoint(
    request: PromoteCandidatesRequest,
    service: Annotated[ImportBatchJobService, Depends(get_import_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> BatchJobResponse:
    """Start a candidate promotion batch job.

    Requires authentication via API key (X-API-Key header) or Bearer token.

    This endpoint returns immediately with a BatchJob in PENDING status.
    The actual promotion runs asynchronously as a background task.

    Poll the job status at:
    - GET /api/v1/batch-jobs/{job_id} - Full job status
    - GET /api/v1/batch-jobs/{job_id}/progress - Real-time progress

    Args:
        request: Promotion configuration parameters.
        service: Import batch job service.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        BatchJobResponse with job ID for status polling.
    """
    logger.info(
        "Starting promote candidates job",
        extra={
            "user_id": str(current_user.id),
            "batch_size": request.batch_size,
            "dry_run": request.dry_run,
        },
    )

    job = await service.start_promotion_job(
        batch_size=request.batch_size,
        dry_run=request.dry_run,
    )

    logger.info(
        "Promote candidates job created",
        extra={
            "job_id": str(job.id),
            "user_id": str(current_user.id),
        },
    )

    return BatchJobResponse.model_validate(job)
