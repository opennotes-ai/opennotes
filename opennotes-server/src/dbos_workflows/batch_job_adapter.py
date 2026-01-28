"""Adapter to sync DBOS workflow state to BatchJob records.

This adapter enables API compatibility during the TaskIQ -> DBOS migration.
BatchJob records are informational—adapter failures do not block workflow execution.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from src.monitoring import get_logger

logger = get_logger(__name__)


class BatchJobDBOSAdapter:
    """Adapter for syncing DBOS workflow state to BatchJob records.

    All methods use fire-and-forget semantics: errors are logged but
    do not propagate to the caller (workflow execution continues).
    """

    async def update_status(
        self,
        batch_job_id: UUID,
        status: str,
        error_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Update BatchJob status (fire-and-forget).

        Args:
            batch_job_id: BatchJob UUID
            status: New status (use BatchJobStatus constants)
            error_summary: Optional error details for failed status

        Returns:
            True if update succeeded, False on error
        """
        try:
            from src.batch_jobs.schemas import BatchJobStatus
            from src.database import get_session_maker

            session_maker = get_session_maker()
            async with session_maker() as db:
                from src.batch_jobs.service import BatchJobService

                service = BatchJobService(db)
                job = await service.get_job(batch_job_id)
                if job is None:
                    logger.warning(
                        "BatchJob not found for status update",
                        extra={
                            "batch_job_id": str(batch_job_id),
                            "target_status": status,
                        },
                    )
                    return False

                if status == BatchJobStatus.IN_PROGRESS.value:
                    await service.start_job(batch_job_id)
                elif status == BatchJobStatus.COMPLETED.value:
                    await service.complete_job(
                        batch_job_id,
                        completed_tasks=job.completed_tasks,
                        failed_tasks=job.failed_tasks,
                    )
                elif status == BatchJobStatus.FAILED.value:
                    await service.fail_job(batch_job_id, error_summary)

                await db.commit()

                logger.info(
                    "BatchJob status updated",
                    extra={
                        "batch_job_id": str(batch_job_id),
                        "new_status": status,
                    },
                )
                return True

        except Exception as e:
            logger.error(
                "Failed to update BatchJob status",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "target_status": status,
                    "error": str(e),
                },
            )
            return False

    def update_status_sync(
        self,
        batch_job_id: UUID,
        status: str,
        error_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Synchronous wrapper for update_status."""
        try:
            return asyncio.run(self.update_status(batch_job_id, status, error_summary))
        except Exception as e:
            logger.error(
                "Failed to update BatchJob status (sync)",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "error": str(e),
                },
            )
            return False

    async def update_progress(
        self,
        batch_job_id: UUID,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
    ) -> bool:
        """Update BatchJob progress counters (fire-and-forget).

        Args:
            batch_job_id: BatchJob UUID
            completed_tasks: Absolute completed count (or None to skip)
            failed_tasks: Absolute failed count (or None to skip)

        Returns:
            True if update succeeded, False on error
        """
        try:
            from src.database import get_session_maker

            session_maker = get_session_maker()
            async with session_maker() as db:
                from src.batch_jobs.models import BatchJob

                job = await db.get(BatchJob, batch_job_id)
                if job is None:
                    logger.warning(
                        "BatchJob not found for progress update",
                        extra={"batch_job_id": str(batch_job_id)},
                    )
                    return False

                if completed_tasks is not None:
                    job.completed_tasks = completed_tasks
                if failed_tasks is not None:
                    job.failed_tasks = failed_tasks

                await db.commit()

                total_processed = (job.completed_tasks or 0) + (job.failed_tasks or 0)
                if total_processed % 100 == 0 or total_processed == job.total_tasks:
                    logger.debug(
                        "BatchJob progress updated",
                        extra={
                            "batch_job_id": str(batch_job_id),
                            "completed": job.completed_tasks,
                            "failed": job.failed_tasks,
                            "total": job.total_tasks,
                        },
                    )

                return True

        except Exception as e:
            logger.error(
                "Failed to update BatchJob progress",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "error": str(e),
                },
            )
            return False

    def update_progress_sync(
        self,
        batch_job_id: UUID,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
    ) -> bool:
        """Synchronous wrapper for update_progress."""
        try:
            return asyncio.run(
                self.update_progress(batch_job_id, completed_tasks, failed_tasks)
            )
        except Exception as e:
            logger.error(
                "Failed to update BatchJob progress (sync)",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "error": str(e),
                },
            )
            return False

    async def finalize_job_async(
        self,
        batch_job_id: UUID,
        success: bool,
        completed_tasks: int,
        failed_tasks: int,
        error_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Finalize a BatchJob with final counts and status.

        This is a convenience method that combines progress update and status
        update into a single call.
        """
        try:
            from src.database import get_session_maker

            session_maker = get_session_maker()
            async with session_maker() as db:
                from src.batch_jobs.models import BatchJob
                from src.batch_jobs.service import BatchJobService

                job = await db.get(BatchJob, batch_job_id)
                if job is None:
                    return False

                job.completed_tasks = completed_tasks
                job.failed_tasks = failed_tasks

                service = BatchJobService(db)
                if success:
                    await service.complete_job(
                        batch_job_id, completed_tasks, failed_tasks
                    )
                else:
                    await service.fail_job(batch_job_id, error_summary)

                await db.commit()

                logger.info(
                    "BatchJob finalized",
                    extra={
                        "batch_job_id": str(batch_job_id),
                        "success": success,
                        "completed": completed_tasks,
                        "failed": failed_tasks,
                    },
                )
                return True

        except Exception as e:
            logger.error(
                "Failed to finalize BatchJob",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "error": str(e),
                },
            )
            return False

    def finalize_job(
        self,
        batch_job_id: UUID,
        success: bool,
        completed_tasks: int,
        failed_tasks: int,
        error_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Synchronous wrapper for finalize_job_async."""
        try:
            return asyncio.run(
                self.finalize_job_async(
                    batch_job_id, success, completed_tasks, failed_tasks, error_summary
                )
            )
        except Exception as e:
            logger.error(
                "Failed to finalize BatchJob (sync)",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "error": str(e),
                },
            )
            return False
