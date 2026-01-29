"""Adapter to sync DBOS workflow state to BatchJob records.

This adapter enables API compatibility during the TaskIQ → DBOS migration.
BatchJob records are informational—adapter failures do not block workflow execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast, overload
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobCreate, BatchJobStatus
from src.batch_jobs.service import BatchJobService
from src.monitoring import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")


def _fire_and_forget_impl(
    func: Callable[P, Coroutine[Any, Any, R]],
    default_return: R,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Implementation of fire_and_forget decorator."""

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(
                f"Fire-and-forget operation failed: {func.__name__}",
                exc_info=True,
                extra={"error": str(e)},
            )
            return default_return

    return async_wrapper


@overload
def fire_and_forget(
    default_return: None,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, UUID | None]]],
    Callable[P, Coroutine[Any, Any, UUID | None]],
]: ...


@overload
def fire_and_forget(
    default_return: bool,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, bool]]], Callable[P, Coroutine[Any, Any, bool]]
]: ...


def fire_and_forget(
    default_return: Any,
) -> Callable[[Callable[P, Coroutine[Any, Any, Any]]], Callable[P, Coroutine[Any, Any, Any]]]:
    """Decorator that catches all exceptions and returns a default value.

    Use this for operations that should never block the caller.
    Errors are logged but not propagated.
    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, Any]],
    ) -> Callable[P, Coroutine[Any, Any, Any]]:
        return _fire_and_forget_impl(func, default_return)

    return decorator


class BatchJobDBOSAdapter:
    """Adapter for syncing DBOS workflow state to BatchJob records.

    All methods use fire-and-forget semantics: errors are logged but
    do not propagate to the caller (workflow execution continues).
    """

    def __init__(
        self,
        db_session_factory: Callable[[], AsyncSession] | Callable[[], AbstractAsyncContextManager[AsyncSession]],
    ) -> None:
        """Initialize the adapter.

        Args:
            db_session_factory: Callable that returns an AsyncSession or an async context manager
                that yields an AsyncSession. The adapter will manage session lifecycle.
        """
        self._db_session_factory = db_session_factory

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session, handling both session factories and context managers."""
        result = self._db_session_factory()
        if hasattr(result, "__aenter__"):
            async with cast(AbstractAsyncContextManager[AsyncSession], result) as session:
                yield session
        else:
            yield cast(AsyncSession, result)

    @fire_and_forget(default_return=None)
    async def create_for_workflow(
        self,
        workflow_id: str,
        job_type: str,
        total_tasks: int,
        metadata: dict[str, Any] | None = None,
    ) -> UUID | None:
        """Create a BatchJob record for a DBOS workflow.

        Args:
            workflow_id: DBOS workflow ID (string)
            job_type: Job type identifier (e.g., "rechunk:fact_check")
            total_tasks: Total number of items to process
            metadata: Optional job metadata (community_server_id, etc.)

        Returns:
            BatchJob UUID if created successfully, None on error
        """
        async with self._get_session() as db:
            service = BatchJobService(db)
            job_create = BatchJobCreate(
                job_type=job_type,
                total_tasks=total_tasks,
                metadata=metadata or {},
                workflow_id=workflow_id,
            )
            job = await service.create_job(job_create)
            await db.commit()
            logger.info(
                "BatchJob created for workflow",
                extra={
                    "batch_job_id": str(job.id),
                    "workflow_id": workflow_id,
                    "job_type": job_type,
                    "total_tasks": total_tasks,
                },
            )
            return job.id

    def create_for_workflow_sync(
        self,
        workflow_id: str,
        job_type: str,
        total_tasks: int,
        metadata: dict[str, Any] | None = None,
    ) -> UUID | None:
        """Synchronous wrapper for create_for_workflow."""
        coro = self.create_for_workflow(workflow_id, job_type, total_tasks, metadata)
        return asyncio.run(cast(Coroutine[Any, Any, UUID | None], coro))

    @fire_and_forget(default_return=False)
    async def update_status(
        self,
        batch_job_id: UUID,
        status: BatchJobStatus | str,
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
        async with self._get_session() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job is None:
                logger.warning(
                    "BatchJob not found for status update",
                    extra={
                        "batch_job_id": str(batch_job_id),
                        "target_status": str(status),
                    },
                )
                return False

            status_value = status.value if isinstance(status, BatchJobStatus) else status

            if status_value == BatchJobStatus.IN_PROGRESS.value:
                await service.start_job(batch_job_id)
            elif status_value == BatchJobStatus.COMPLETED.value:
                await service.complete_job(
                    batch_job_id,
                    completed_tasks=job.completed_tasks,
                    failed_tasks=job.failed_tasks,
                )
            elif status_value == BatchJobStatus.FAILED.value:
                await service.fail_job(batch_job_id, error_summary)
            elif status_value == BatchJobStatus.CANCELLED.value:
                await service.cancel_job(batch_job_id)
            else:
                job.status = status_value
                await db.commit()

            logger.info(
                "BatchJob status updated",
                extra={
                    "batch_job_id": str(batch_job_id),
                    "new_status": status_value,
                },
            )
            return True

    def update_status_sync(
        self,
        batch_job_id: UUID,
        status: BatchJobStatus | str,
        error_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Synchronous wrapper for update_status."""
        coro = self.update_status(batch_job_id, status, error_summary)
        return asyncio.run(cast(Coroutine[Any, Any, bool], coro))

    @fire_and_forget(default_return=False)
    async def update_progress(
        self,
        batch_job_id: UUID,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
        increment_completed: bool = False,
        increment_failed: bool = False,
    ) -> bool:
        """Update BatchJob progress counters (fire-and-forget).

        Args:
            batch_job_id: BatchJob UUID
            completed_tasks: Absolute completed count (or None to skip)
            failed_tasks: Absolute failed count (or None to skip)
            increment_completed: If True, increment completed_tasks by 1
            increment_failed: If True, increment failed_tasks by 1

        Returns:
            True if update succeeded, False on error

        Note: increment_* options are useful for step-by-step progress updates.
        """
        async with self._get_session() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job is None:
                logger.warning(
                    "BatchJob not found for progress update",
                    extra={"batch_job_id": str(batch_job_id)},
                )
                return False

            new_completed = job.completed_tasks
            new_failed = job.failed_tasks

            if completed_tasks is not None:
                new_completed = completed_tasks
            if failed_tasks is not None:
                new_failed = failed_tasks

            if increment_completed:
                new_completed = (new_completed or 0) + 1
            if increment_failed:
                new_failed = (new_failed or 0) + 1

            await service.update_progress(
                batch_job_id,
                completed_tasks=new_completed,
                failed_tasks=new_failed,
            )
            await db.commit()

            total_processed = (new_completed or 0) + (new_failed or 0)
            if total_processed % 100 == 0 or total_processed == job.total_tasks:
                logger.debug(
                    "BatchJob progress updated",
                    extra={
                        "batch_job_id": str(batch_job_id),
                        "completed": new_completed,
                        "failed": new_failed,
                        "total": job.total_tasks,
                    },
                )

            return True

    def update_progress_sync(
        self,
        batch_job_id: UUID,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
        increment_completed: bool = False,
        increment_failed: bool = False,
    ) -> bool:
        """Synchronous wrapper for update_progress."""
        coro = self.update_progress(
            batch_job_id,
            completed_tasks,
            failed_tasks,
            increment_completed,
            increment_failed,
        )
        return asyncio.run(cast(Coroutine[Any, Any, bool], coro))

    @fire_and_forget(default_return=False)
    async def finalize_job(
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

        Args:
            batch_job_id: BatchJob UUID
            success: Whether the workflow completed successfully
            completed_tasks: Final count of completed tasks
            failed_tasks: Final count of failed tasks
            error_summary: Optional error details for failed status

        Returns:
            True if finalization succeeded, False on error
        """
        async with self._get_session() as db:
            service = BatchJobService(db)
            job = await service.get_job(batch_job_id)
            if job is None:
                logger.warning(
                    "BatchJob not found for finalization",
                    extra={"batch_job_id": str(batch_job_id)},
                )
                return False

            if success:
                await service.complete_job(batch_job_id, completed_tasks, failed_tasks)
            else:
                await service.update_progress(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
                await service.fail_job(batch_job_id, error_summary)

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

    def finalize_job_sync(
        self,
        batch_job_id: UUID,
        success: bool,
        completed_tasks: int,
        failed_tasks: int,
        error_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Synchronous wrapper for finalize_job."""
        coro = self.finalize_job(
            batch_job_id, success, completed_tasks, failed_tasks, error_summary
        )
        return asyncio.run(cast(Coroutine[Any, Any, bool], coro))

    async def get_job_by_workflow_id(self, workflow_id: str) -> BatchJob | None:
        """Get a BatchJob by its workflow_id.

        Args:
            workflow_id: DBOS workflow ID

        Returns:
            BatchJob if found, None otherwise
        """
        from sqlalchemy import select  # noqa: PLC0415

        try:
            async with self._get_session() as db:
                result = await db.execute(
                    select(BatchJob).where(BatchJob.workflow_id == workflow_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                "Failed to get BatchJob by workflow_id",
                exc_info=True,
                extra={
                    "workflow_id": workflow_id,
                    "error": str(e),
                },
            )
            return None
