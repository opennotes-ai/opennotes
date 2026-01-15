"""
Service for managing fact-check import batch jobs.

Provides high-level operations for starting and managing import jobs
that run asynchronously via TaskIQ background tasks.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.config import get_settings
from src.monitoring import get_logger

logger = get_logger(__name__)

IMPORT_JOB_TYPE = "import:fact_check_bureau"
SCRAPE_JOB_TYPE = "scrape:candidates"
PROMOTION_JOB_TYPE = "promote:candidates"


class ImportBatchJobService:
    """
    Service for managing fact-check import batch jobs.

    Coordinates batch job creation with TaskIQ task dispatch for
    non-blocking import operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize the service.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self._session = session
        self._batch_job_service = BatchJobService(session)

    async def start_import_job(
        self,
        batch_size: int = 1000,
        dry_run: bool = False,
        enqueue_scrapes: bool = False,
    ) -> BatchJob:
        """
        Start a new fact-check import job.

        Creates a BatchJob in PENDING status and dispatches a TaskIQ
        background task to perform the actual import. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of rows per batch during import (default 1000)
            dry_run: If True, validate only without inserting
            enqueue_scrapes: If True, enqueue scrape tasks after import

        Returns:
            The created BatchJob (in PENDING status)
        """
        from src.tasks.import_tasks import process_fact_check_import  # noqa: PLC0415

        settings = get_settings()

        job_data = BatchJobCreate(
            job_type=IMPORT_JOB_TYPE,
            total_tasks=0,
            metadata={
                "source": "fact_check_bureau",
                "batch_size": batch_size,
                "dry_run": dry_run,
                "enqueue_scrapes": enqueue_scrapes,
            },
        )

        job = await self._batch_job_service.create_job(job_data)
        await self._session.commit()

        logger.info(
            "Created import batch job, dispatching background task",
            extra={
                "job_id": str(job.id),
                "batch_size": batch_size,
                "dry_run": dry_run,
                "enqueue_scrapes": enqueue_scrapes,
            },
        )

        await process_fact_check_import.kiq(
            job_id=str(job.id),
            batch_size=batch_size,
            dry_run=dry_run,
            enqueue_scrapes=enqueue_scrapes,
            db_url=settings.DATABASE_URL,
            redis_url=settings.REDIS_URL,
        )

        return job

    async def get_import_job(self, job_id: UUID) -> BatchJob | None:
        """
        Get an import job by ID.

        Args:
            job_id: The job's unique identifier

        Returns:
            The BatchJob if found, None otherwise
        """
        return await self._batch_job_service.get_job(job_id)

    async def start_scrape_job(
        self,
        batch_size: int = 1000,
        dry_run: bool = False,
    ) -> BatchJob:
        """
        Start a new candidate scrape job.

        Creates a BatchJob in PENDING status and dispatches a TaskIQ
        background task to scrape pending candidates. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of candidates to process per batch (default 1000)
            dry_run: If True, count candidates but don't scrape

        Returns:
            The created BatchJob (in PENDING status)
        """
        from src.tasks.import_tasks import process_scrape_batch  # noqa: PLC0415

        settings = get_settings()

        job_data = BatchJobCreate(
            job_type=SCRAPE_JOB_TYPE,
            total_tasks=0,
            metadata={
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        job = await self._batch_job_service.create_job(job_data)
        await self._session.commit()

        logger.info(
            "Created scrape batch job, dispatching background task",
            extra={
                "job_id": str(job.id),
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        await process_scrape_batch.kiq(
            job_id=str(job.id),
            batch_size=batch_size,
            dry_run=dry_run,
            db_url=settings.DATABASE_URL,
            redis_url=settings.REDIS_URL,
        )

        return job

    async def start_promotion_job(
        self,
        batch_size: int = 1000,
        dry_run: bool = False,
    ) -> BatchJob:
        """
        Start a new candidate promotion job.

        Creates a BatchJob in PENDING status and dispatches a TaskIQ
        background task to promote scraped candidates. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of candidates to process per batch (default 1000)
            dry_run: If True, count candidates but don't promote

        Returns:
            The created BatchJob (in PENDING status)
        """
        from src.tasks.import_tasks import process_promotion_batch  # noqa: PLC0415

        settings = get_settings()

        job_data = BatchJobCreate(
            job_type=PROMOTION_JOB_TYPE,
            total_tasks=0,
            metadata={
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        job = await self._batch_job_service.create_job(job_data)
        await self._session.commit()

        logger.info(
            "Created promotion batch job, dispatching background task",
            extra={
                "job_id": str(job.id),
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        await process_promotion_batch.kiq(
            job_id=str(job.id),
            batch_size=batch_size,
            dry_run=dry_run,
            db_url=settings.DATABASE_URL,
            redis_url=settings.REDIS_URL,
        )

        return job


def get_import_batch_job_service(session: AsyncSession) -> ImportBatchJobService:
    """Factory function to create an ImportBatchJobService instance."""
    return ImportBatchJobService(session)
