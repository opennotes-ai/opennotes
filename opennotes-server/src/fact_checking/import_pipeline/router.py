"""API endpoint for fact-check bureau import.

Exposes the import pipeline functionality via REST API for programmatic access.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.database import get_db
from src.fact_checking.import_pipeline.importer import import_fact_check_bureau
from src.fact_checking.import_pipeline.scrape_task import enqueue_scrape_batch
from src.users.models import User

logger = logging.getLogger(__name__)

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
        description="Enqueue scrape tasks for pending candidates instead of importing",
    )


class ImportFactCheckBureauResponse(BaseModel):
    """Response containing import statistics."""

    total_rows: int = Field(description="Total rows in the dataset")
    valid_rows: int = Field(description="Rows that passed validation")
    invalid_rows: int = Field(description="Rows that failed validation")
    inserted: int = Field(description="Rows inserted into database")
    updated: int = Field(description="Rows updated in database")
    errors: list[str] = Field(
        default_factory=list,
        description="First 10 validation/import errors",
    )
    dry_run: bool = Field(description="Whether this was a dry run")


class EnqueueScrapeResponse(BaseModel):
    """Response for enqueue scrapes operation."""

    enqueued: int = Field(description="Number of scrape tasks enqueued")


@router.post(
    "/fact-check-bureau",
    response_model=ImportFactCheckBureauResponse | EnqueueScrapeResponse,
    status_code=status.HTTP_200_OK,
    summary="Import fact-check-bureau dataset",
    description="Import the fact-check-bureau dataset from HuggingFace. "
    "Supports dry-run mode for validation and enqueue-scrapes mode for "
    "triggering content scraping of pending candidates.",
)
async def import_fact_check_bureau_endpoint(
    request: ImportFactCheckBureauRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> ImportFactCheckBureauResponse | EnqueueScrapeResponse:
    """Import fact-check-bureau dataset or enqueue scrape tasks.

    Requires authentication via API key (X-API-Key header) or Bearer token.

    Args:
        request: Import configuration parameters.
        db: Database session.
        current_user: Authenticated user (via API key or JWT).

    Returns:
        Import statistics or scrape enqueue count.
    """
    logger.info(
        f"Import request from user {current_user.id}: "
        f"batch_size={request.batch_size}, dry_run={request.dry_run}, "
        f"enqueue_scrapes={request.enqueue_scrapes}"
    )

    if request.enqueue_scrapes:
        result = await enqueue_scrape_batch(batch_size=request.batch_size)
        logger.info(f"Enqueued {result['enqueued']} scrape tasks")
        return EnqueueScrapeResponse(enqueued=result["enqueued"])

    stats = await import_fact_check_bureau(
        session=db,
        batch_size=request.batch_size,
        dry_run=request.dry_run,
    )

    logger.info(
        f"Import complete: {stats.total_rows} total, {stats.valid_rows} valid, "
        f"{stats.inserted} inserted, {stats.updated} updated"
    )

    return ImportFactCheckBureauResponse(
        total_rows=stats.total_rows,
        valid_rows=stats.valid_rows,
        invalid_rows=stats.invalid_rows,
        inserted=stats.inserted,
        updated=stats.updated,
        errors=stats.errors[:10] if stats.errors else [],
        dry_run=request.dry_run,
    )
