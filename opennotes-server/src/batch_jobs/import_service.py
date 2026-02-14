"""
Service for managing fact-check import batch jobs.

Provides high-level operations for starting and managing import jobs
that run asynchronously via DBOS durable workflows.

Note: Concurrent job prevention is handled by DistributedRateLimitMiddleware,
not by this service. The middleware enforces one active job per type.

Orphaned Job Cleanup Strategy
-----------------------------
If DBOS dispatch (client.enqueue()) fails AND the subsequent fail_job() call
also fails (double-failure scenario), the job remains in PENDING status
indefinitely.

This is handled by a cleanup mechanism rather than immediate deletion because:
1. Multiple start_*_job methods share this pattern
2. Deletion could race with legitimate job pickup
3. PENDING jobs should be rare; cleanup is sufficient

Cleanup approach:
- A scheduled task should periodically scan for PENDING jobs where:
  - updated_at < (now - STALE_PENDING_JOB_THRESHOLD_MINUTES)
  - No corresponding DBOS workflow is running
- Such jobs should be marked FAILED with error_summary indicating "orphaned"
- Double-failure cases are logged with ORPHANED_JOB_MARKER for monitoring alerts

See: batch_jobs/cleanup.py for the cleanup implementation (TODO if not exists).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.constants import (
    BULK_APPROVAL_JOB_TYPE,
    DEFAULT_SCRAPE_CONCURRENCY,
    IMPORT_JOB_TYPE,
    PROMOTION_JOB_TYPE,
    SCRAPE_JOB_TYPE,
)
from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.monitoring import get_logger

logger = get_logger(__name__)

USER_ID_KEY = "user_id"
MIN_BASE_DELAY = 0.1
MAX_BASE_DELAY = 30.0
STALE_PENDING_JOB_THRESHOLD_MINUTES = 5
ORPHANED_JOB_MARKER = "POTENTIAL_ORPHANED_JOB"


class ImportBatchJobService:
    """
    Service for managing fact-check import batch jobs.

    Coordinates batch job creation with DBOS workflow dispatch for
    non-blocking import operations.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
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
        user_id: str | None = None,
    ) -> BatchJob:
        """
        Start a new fact-check import job.

        Creates a BatchJob in PENDING status and dispatches a DBOS durable
        workflow to perform the actual import. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of rows per batch during import (default 1000)
            dry_run: If True, validate only without inserting
            enqueue_scrapes: If True, enqueue scrape tasks after import
            user_id: ID of the user who started the job (for audit trail)

        Returns:
            The created BatchJob (in PENDING status)
        """
        from src.dbos_workflows.import_workflow import dispatch_import_workflow  # noqa: PLC0415

        metadata: dict[str, str | int | bool | float | list[str] | None] = {
            "source": "fact_check_bureau",
            "batch_size": batch_size,
            "dry_run": dry_run,
            "enqueue_scrapes": enqueue_scrapes,
            "execution_backend": "dbos",
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
            "Created import batch job, dispatching DBOS workflow",
            extra={
                "job_id": str(job.id),
                "batch_size": batch_size,
                "dry_run": dry_run,
                "enqueue_scrapes": enqueue_scrapes,
            },
        )

        try:
            workflow_id = await dispatch_import_workflow(
                batch_job_id=job.id,
                batch_size=batch_size,
                dry_run=dry_run,
                enqueue_scrapes=enqueue_scrapes,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            await self._handle_dispatch_failure(job, e, "connection_error")
            raise
        except Exception as e:
            await self._handle_dispatch_failure(job, e, "workflow_dispatch")
            raise

        await self._batch_job_service.set_workflow_id(job.id, workflow_id)
        await self._session.commit()

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
        base_delay: float = 1.0,
    ) -> BatchJob:
        """
        Start a new candidate scrape job.

        Creates a BatchJob in PENDING status and dispatches a DBOS durable
        workflow to scrape pending candidates. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of candidates to process per batch (default 1000)
            dry_run: If True, count candidates but don't scrape
            user_id: ID of the user who started the job (for audit trail)
            base_delay: Minimum delay in seconds between requests to same domain
                (must be between 0.1 and 30.0)

        Returns:
            The created BatchJob (in PENDING status)

        Raises:
            ValueError: If base_delay is outside [0.1, 30.0] range
        """
        if not (MIN_BASE_DELAY <= base_delay <= MAX_BASE_DELAY):
            raise ValueError(
                f"base_delay must be between {MIN_BASE_DELAY} and {MAX_BASE_DELAY}, "
                f"got {base_delay}"
            )

        from src.dbos_workflows.import_workflow import dispatch_scrape_workflow  # noqa: PLC0415

        metadata: dict[str, str | int | bool | float | list[str] | None] = {
            "batch_size": batch_size,
            "dry_run": dry_run,
            "base_delay": base_delay,
            "execution_backend": "dbos",
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
            "Created scrape batch job, dispatching DBOS workflow",
            extra={
                "job_id": str(job.id),
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        try:
            workflow_id = await dispatch_scrape_workflow(
                batch_job_id=job.id,
                batch_size=batch_size,
                dry_run=dry_run,
                concurrency=DEFAULT_SCRAPE_CONCURRENCY,
                base_delay=base_delay,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            await self._handle_dispatch_failure(job, e, "connection_error")
            raise
        except Exception as e:
            await self._handle_dispatch_failure(job, e, "workflow_dispatch")
            raise

        await self._batch_job_service.set_workflow_id(job.id, workflow_id)
        await self._session.commit()

        return job

    async def start_promotion_job(
        self,
        batch_size: int = 1000,
        dry_run: bool = False,
        user_id: str | None = None,
    ) -> BatchJob:
        """
        Start a new candidate promotion job.

        Creates a BatchJob in PENDING status and dispatches a DBOS durable
        workflow to promote scraped candidates. Returns immediately
        without blocking the HTTP connection.

        Args:
            batch_size: Number of candidates to process per batch (default 1000)
            dry_run: If True, count candidates but don't promote
            user_id: ID of the user who started the job (for audit trail)

        Returns:
            The created BatchJob (in PENDING status)
        """
        from src.dbos_workflows.import_workflow import dispatch_promote_workflow  # noqa: PLC0415

        metadata: dict[str, str | int | bool | float | list[str] | None] = {
            "batch_size": batch_size,
            "dry_run": dry_run,
            "execution_backend": "dbos",
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
            "Created promotion batch job, dispatching DBOS workflow",
            extra={
                "job_id": str(job.id),
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        try:
            workflow_id = await dispatch_promote_workflow(
                batch_job_id=job.id,
                batch_size=batch_size,
                dry_run=dry_run,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            await self._handle_dispatch_failure(job, e, "connection_error")
            raise
        except Exception as e:
            await self._handle_dispatch_failure(job, e, "workflow_dispatch")
            raise

        await self._batch_job_service.set_workflow_id(job.id, workflow_id)
        await self._session.commit()

        return job

    async def start_bulk_approval_job(
        self,
        threshold: float = 1.0,
        auto_promote: bool = False,
        limit: int = 200,
        status: str | None = None,
        dataset_name: str | None = None,
        dataset_tags: list[str] | None = None,
        has_content: bool | None = None,
        published_date_from: datetime | None = None,
        published_date_to: datetime | None = None,
        user_id: str | None = None,
    ) -> BatchJob:
        """
        Start a new bulk approval job.

        Creates a BatchJob in PENDING status and enqueues a DBOS durable
        workflow to approve candidates from predictions. Returns immediately
        without blocking the HTTP connection.

        Args:
            threshold: Minimum prediction probability to approve (0.0-1.0)
            auto_promote: Whether to promote approved candidates
            limit: Maximum number of candidates to process
            status: Filter by candidate status
            dataset_name: Filter by dataset name
            dataset_tags: Filter by dataset tags
            has_content: Filter by content presence
            published_date_from: Filter by published date
            published_date_to: Filter by published date
            user_id: ID of the user who started the job (for audit trail)

        Returns:
            The created BatchJob (in PENDING status)
        """
        from src.dbos_workflows.approval_workflow import (  # noqa: PLC0415
            dispatch_bulk_approval_workflow,
        )

        metadata: dict[str, str | int | bool | float | list[str] | None] = {
            "threshold": threshold,
            "auto_promote": auto_promote,
            "limit": limit,
            "status": status,
            "dataset_name": dataset_name,
            "dataset_tags": dataset_tags,
            "has_content": has_content,
            "published_date_from": published_date_from.isoformat() if published_date_from else None,
            "published_date_to": published_date_to.isoformat() if published_date_to else None,
            "execution_backend": "dbos",
        }
        if user_id is not None:
            metadata[USER_ID_KEY] = user_id

        job_data = BatchJobCreate(
            job_type=BULK_APPROVAL_JOB_TYPE,
            total_tasks=0,
            metadata=metadata,
        )

        job = await self._batch_job_service.create_job(job_data)
        await self._session.commit()

        logger.info(
            "Created bulk approval batch job, dispatching DBOS workflow",
            extra={
                "job_id": str(job.id),
                "threshold": threshold,
                "auto_promote": auto_promote,
                "limit": limit,
            },
        )

        try:
            workflow_id = await dispatch_bulk_approval_workflow(
                batch_job_id=job.id,
                threshold=threshold,
                auto_promote=auto_promote,
                limit=limit,
                status=status,
                dataset_name=dataset_name,
                dataset_tags=dataset_tags,
                has_content=has_content,
                published_date_from=published_date_from.isoformat()
                if published_date_from
                else None,
                published_date_to=published_date_to.isoformat() if published_date_to else None,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            await self._handle_dispatch_failure(job, e, "connection_error")
            raise
        except Exception as e:
            await self._handle_dispatch_failure(job, e, "workflow_dispatch")
            raise

        await self._batch_job_service.set_workflow_id(job.id, workflow_id)
        await self._session.commit()

        return job

    async def _handle_dispatch_failure(
        self,
        job: BatchJob,
        error: Exception,
        stage: str,
    ) -> None:
        """
        Handle workflow dispatch failure by marking the job as failed.

        If marking the job as failed also fails (double-failure), logs with
        ORPHANED_JOB_MARKER for monitoring alerts. Such jobs will be cleaned
        up by the stale PENDING job cleanup mechanism.

        Args:
            job: The BatchJob that failed to dispatch
            error: The exception that occurred during dispatch
            stage: Error stage identifier (e.g., "connection_error", "workflow_dispatch")
        """
        try:
            await self._batch_job_service.fail_job(
                job.id,
                error_summary={"error": str(error), "stage": stage},
            )
            await self._session.commit()
            await self._session.refresh(job)
        except Exception:
            logger.exception(
                f"{ORPHANED_JOB_MARKER}: Failed to mark job as failed after "
                "workflow dispatch error. Job may remain in PENDING status and "
                f"require cleanup after {STALE_PENDING_JOB_THRESHOLD_MINUTES} minutes.",
                extra={
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "original_error": str(error),
                    "original_stage": stage,
                },
            )


def get_import_batch_job_service(
    session: AsyncSession,
) -> ImportBatchJobService:
    """Factory function to create an ImportBatchJobService instance."""
    return ImportBatchJobService(session)
