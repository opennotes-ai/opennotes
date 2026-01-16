"""
Service for managing fact-check import batch jobs.

Provides high-level operations for starting and managing import jobs
that run asynchronously via TaskIQ background tasks.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.constants import (
    DEFAULT_SCRAPE_CONCURRENCY,
    IMPORT_JOB_TYPE,
    PROMOTION_JOB_TYPE,
    SCRAPE_JOB_TYPE,
)
from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.config import get_settings
from src.fact_checking.rechunk_lock import RechunkLockManager
from src.monitoring import get_logger

logger = get_logger(__name__)

USER_ID_KEY = "user_id"

LOCK_OPERATION_IMPORT = "import"
LOCK_OPERATION_SCRAPE = "scrape"
LOCK_OPERATION_PROMOTE = "promote"


class ConcurrentJobError(Exception):
    """Raised when attempting to start a job while another job of the same type is running."""

    def __init__(self, job_type: str) -> None:
        self.job_type = job_type
        super().__init__(
            f"A {job_type} job is already in progress. "
            "Please wait for it to complete before starting a new one."
        )


class ImportBatchJobService:
    """
    Service for managing fact-check import batch jobs.

    Coordinates batch job creation with TaskIQ task dispatch for
    non-blocking import operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        lock_manager: RechunkLockManager | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            session: SQLAlchemy async session for database operations
            lock_manager: Optional lock manager for preventing concurrent jobs
        """
        self._session = session
        self._batch_job_service = BatchJobService(session)
        self._lock_manager = lock_manager

    async def start_import_job(
        self,
        batch_size: int = 1000,
        dry_run: bool = False,
        enqueue_scrapes: bool = False,
        user_id: str | None = None,
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
            user_id: ID of the user who started the job (for audit trail)

        Returns:
            The created BatchJob (in PENDING status)

        Raises:
            ConcurrentJobError: If a lock manager is configured and a job is already running
        """
        from src.tasks.import_tasks import process_fact_check_import  # noqa: PLC0415

        settings = get_settings()

        if self._lock_manager is not None:
            lock_acquired = await self._lock_manager.acquire_lock(LOCK_OPERATION_IMPORT)
            if not lock_acquired:
                raise ConcurrentJobError(LOCK_OPERATION_IMPORT)

        try:
            metadata = {
                "source": "fact_check_bureau",
                "batch_size": batch_size,
                "dry_run": dry_run,
                "enqueue_scrapes": enqueue_scrapes,
            }
            if user_id is not None:
                metadata[USER_ID_KEY] = user_id

            job_data = BatchJobCreate(
                job_type=IMPORT_JOB_TYPE,
                total_tasks=0,
                metadata=metadata,
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
        except Exception:
            if self._lock_manager is not None:
                await self._lock_manager.release_lock(LOCK_OPERATION_IMPORT)
            raise

        try:
            await process_fact_check_import.kiq(
                job_id=str(job.id),
                batch_size=batch_size,
                dry_run=dry_run,
                enqueue_scrapes=enqueue_scrapes,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
                lock_operation=LOCK_OPERATION_IMPORT if self._lock_manager else None,
            )
        except Exception as e:
            await self._batch_job_service.fail_job(
                job.id,
                error_summary={"error": str(e), "stage": "task_dispatch"},
            )
            await self._session.commit()
            await self._session.refresh(job)
            if self._lock_manager is not None:
                await self._lock_manager.release_lock(LOCK_OPERATION_IMPORT)
            raise

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
        user_id: str | None = None,
    ) -> BatchJob:
        """
        Start a new candidate scrape job.

        Creates a BatchJob in PENDING status and dispatches a TaskIQ
        background task to scrape pending candidates. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of candidates to process per batch (default 1000)
            dry_run: If True, count candidates but don't scrape
            user_id: ID of the user who started the job (for audit trail)

        Returns:
            The created BatchJob (in PENDING status)

        Raises:
            ConcurrentJobError: If a lock manager is configured and a job is already running
        """
        from src.tasks.import_tasks import process_scrape_batch  # noqa: PLC0415

        settings = get_settings()

        if self._lock_manager is not None:
            lock_acquired = await self._lock_manager.acquire_lock(LOCK_OPERATION_SCRAPE)
            if not lock_acquired:
                raise ConcurrentJobError(LOCK_OPERATION_SCRAPE)

        try:
            metadata = {
                "batch_size": batch_size,
                "dry_run": dry_run,
            }
            if user_id is not None:
                metadata[USER_ID_KEY] = user_id

            job_data = BatchJobCreate(
                job_type=SCRAPE_JOB_TYPE,
                total_tasks=0,
                metadata=metadata,
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
        except Exception:
            if self._lock_manager is not None:
                await self._lock_manager.release_lock(LOCK_OPERATION_SCRAPE)
            raise

        try:
            await process_scrape_batch.kiq(
                job_id=str(job.id),
                batch_size=batch_size,
                dry_run=dry_run,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
                lock_operation=LOCK_OPERATION_SCRAPE if self._lock_manager else None,
                concurrency=DEFAULT_SCRAPE_CONCURRENCY,
            )
        except Exception as e:
            await self._batch_job_service.fail_job(
                job.id,
                error_summary={"error": str(e), "stage": "task_dispatch"},
            )
            await self._session.commit()
            await self._session.refresh(job)
            if self._lock_manager is not None:
                await self._lock_manager.release_lock(LOCK_OPERATION_SCRAPE)
            raise

        return job

    async def start_promotion_job(
        self,
        batch_size: int = 1000,
        dry_run: bool = False,
        user_id: str | None = None,
    ) -> BatchJob:
        """
        Start a new candidate promotion job.

        Creates a BatchJob in PENDING status and dispatches a TaskIQ
        background task to promote scraped candidates. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of candidates to process per batch (default 1000)
            dry_run: If True, count candidates but don't promote
            user_id: ID of the user who started the job (for audit trail)

        Returns:
            The created BatchJob (in PENDING status)

        Raises:
            ConcurrentJobError: If a lock manager is configured and a job is already running
        """
        from src.tasks.import_tasks import process_promotion_batch  # noqa: PLC0415

        settings = get_settings()

        if self._lock_manager is not None:
            lock_acquired = await self._lock_manager.acquire_lock(LOCK_OPERATION_PROMOTE)
            if not lock_acquired:
                raise ConcurrentJobError(LOCK_OPERATION_PROMOTE)

        try:
            metadata = {
                "batch_size": batch_size,
                "dry_run": dry_run,
            }
            if user_id is not None:
                metadata[USER_ID_KEY] = user_id

            job_data = BatchJobCreate(
                job_type=PROMOTION_JOB_TYPE,
                total_tasks=0,
                metadata=metadata,
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
        except Exception:
            if self._lock_manager is not None:
                await self._lock_manager.release_lock(LOCK_OPERATION_PROMOTE)
            raise

        try:
            await process_promotion_batch.kiq(
                job_id=str(job.id),
                batch_size=batch_size,
                dry_run=dry_run,
                db_url=settings.DATABASE_URL,
                redis_url=settings.REDIS_URL,
                lock_operation=LOCK_OPERATION_PROMOTE if self._lock_manager else None,
            )
        except Exception as e:
            await self._batch_job_service.fail_job(
                job.id,
                error_summary={"error": str(e), "stage": "task_dispatch"},
            )
            await self._session.commit()
            await self._session.refresh(job)
            if self._lock_manager is not None:
                await self._lock_manager.release_lock(LOCK_OPERATION_PROMOTE)
            raise

        return job


def get_import_batch_job_service(
    session: AsyncSession,
    lock_manager: RechunkLockManager | None = None,
) -> ImportBatchJobService:
    """Factory function to create an ImportBatchJobService instance."""
    return ImportBatchJobService(session, lock_manager)
