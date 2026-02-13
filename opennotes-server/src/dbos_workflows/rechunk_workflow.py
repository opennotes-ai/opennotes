"""DBOS workflows for rechunking fact-check items and previously-seen messages.

These workflows replace the TaskIQ-based rechunk tasks with durable
DBOS execution. Each item is processed as a step with automatic
checkpointing, enabling resume from the last completed item.

The dispatch functions in this module create a BatchJob, fetch
item IDs, enqueue the DBOS workflow, and link them together.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dbos import DBOS, EnqueueOptions, Queue
from sqlalchemy import select

from src.batch_jobs.constants import (
    RECHUNK_FACT_CHECK_JOB_TYPE,
    RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
)
from src.batch_jobs.schemas import BatchJobCreate
from src.batch_jobs.service import BatchJobService
from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.dbos_workflows.config import get_dbos_client
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

rechunk_queue = Queue(
    name="rechunk",
    worker_concurrency=2,
    concurrency=10,
)

EMBEDDING_RETRIES_ALLOWED: bool = True
EMBEDDING_MAX_ATTEMPTS: int = 5
EMBEDDING_INTERVAL_SECONDS: float = 1.0
EMBEDDING_BACKOFF_RATE: float = 2.0


async def dispatch_dbos_rechunk_workflow(
    db: AsyncSession,
    community_server_id: UUID | None = None,
    batch_size: int = 100,
    metadata: dict[str, Any] | None = None,
) -> UUID:
    """Dispatch a DBOS rechunk workflow for fact-check items.

    This function:
    1. Fetches item IDs to process
    2. Creates a BatchJob record (PENDING)
    3. Starts the BatchJob (IN_PROGRESS)
    4. Enqueues the DBOS workflow
    5. Updates BatchJob with workflow_id

    Args:
        db: Database session
        community_server_id: Optional community filter
        batch_size: Items per progress update
        metadata: Additional job metadata

    Returns:
        BatchJob UUID

    Raises:
        ValueError: If no fact-check items to process
        Exception: If workflow dispatch fails (BatchJob marked as FAILED)
    """
    stmt = select(FactCheckItem.id).order_by(FactCheckItem.created_at)

    result = await db.execute(stmt)
    item_ids = [str(row[0]) for row in result.fetchall()]

    if not item_ids:
        raise ValueError("No fact-check items to process")

    batch_job_service = BatchJobService(db)
    job_metadata = {
        "community_server_id": str(community_server_id) if community_server_id else None,
        "batch_size": batch_size,
        "chunk_type": "fact_check",
        "execution_backend": "dbos",
        **(metadata or {}),
    }

    job = await batch_job_service.create_job(
        BatchJobCreate(
            job_type=RECHUNK_FACT_CHECK_JOB_TYPE,
            total_tasks=len(item_ids),
            metadata=job_metadata,
        )
    )

    await batch_job_service.start_job(job.id)
    await db.commit()
    await db.refresh(job)

    try:
        client = get_dbos_client()
        options: EnqueueOptions = {
            "queue_name": "rechunk",
            "workflow_name": RECHUNK_FACT_CHECK_WORKFLOW_NAME,
        }
        handle = await asyncio.to_thread(
            client.enqueue,
            options,
            str(job.id),
            str(community_server_id) if community_server_id else None,
            item_ids,
            batch_size,
        )
        workflow_id = handle.workflow_id
    except Exception as e:
        await batch_job_service.fail_job(
            job.id,
            error_summary={"stage": "dispatch", "error": str(e)},
        )
        await db.commit()
        logger.error(
            "Failed to dispatch DBOS rechunk workflow",
            extra={"batch_job_id": str(job.id), "error": str(e)},
            exc_info=True,
        )
        raise

    await batch_job_service.set_workflow_id(job.id, workflow_id)
    await db.commit()

    logger.info(
        "DBOS rechunk workflow dispatched",
        extra={
            "batch_job_id": str(job.id),
            "workflow_id": workflow_id,
            "total_items": len(item_ids),
        },
    )

    return job.id


@DBOS.workflow()
def rechunk_fact_check_workflow(
    batch_job_id: str,
    community_server_id: str | None,
    item_ids: list[str],
    batch_size: int = 100,
) -> dict[str, Any]:
    """DBOS workflow for rechunking fact-check items.

    Args:
        batch_job_id: UUID of the BatchJob record (as string)
        community_server_id: Optional community server for LLM credentials
        item_ids: List of FactCheckItem UUIDs to process
        batch_size: Items per batch (for progress reporting)

    Returns:
        dict with completed_count, failed_count, and any errors
    """
    workflow_id = DBOS.workflow_id
    total_items = len(item_ids)

    logger.info(
        "Starting rechunk workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
            "total_items": total_items,
        },
    )

    circuit_breaker = CircuitBreaker(
        threshold=5,
        reset_timeout=60,
    )

    completed_count = 0
    failed_count = 0
    errors: list[dict[str, Any]] = []

    for i, item_id in enumerate(item_ids):
        try:
            circuit_breaker.check()

            result = process_fact_check_item(
                item_id=item_id,
                community_server_id=community_server_id,
            )

            if result["success"]:
                completed_count += 1
                circuit_breaker.record_success()
            else:
                failed_count += 1
                errors.append({"item_id": item_id, "error": result.get("error")})

        except CircuitOpenError:
            logger.error(
                "Circuit breaker open - pausing workflow",
                extra={
                    "workflow_id": workflow_id,
                    "consecutive_failures": circuit_breaker.failures,
                },
            )
            update_batch_job_progress_sync(
                UUID(batch_job_id),
                completed_tasks=completed_count,
                failed_tasks=failed_count,
            )
            raise

        except Exception as e:
            failed_count += 1
            errors.append({"item_id": item_id, "error": str(e)})
            circuit_breaker.record_failure()

        if (i + 1) % batch_size == 0 or (i + 1) == total_items:
            update_batch_job_progress_sync(
                UUID(batch_job_id),
                completed_tasks=completed_count,
                failed_tasks=failed_count,
            )

    success = failed_count == 0
    error_summary = {"errors": errors} if errors else None
    finalize_batch_job_sync(
        UUID(batch_job_id),
        success=success,
        completed_tasks=completed_count,
        failed_tasks=failed_count,
        error_summary=error_summary,
    )

    logger.info(
        "Rechunk workflow completed",
        extra={
            "workflow_id": workflow_id,
            "completed": completed_count,
            "failed": failed_count,
        },
    )

    return {
        "completed_count": completed_count,
        "failed_count": failed_count,
        "errors": errors,
    }


@DBOS.step(
    retries_allowed=EMBEDDING_RETRIES_ALLOWED,
    max_attempts=EMBEDDING_MAX_ATTEMPTS,
    interval_seconds=EMBEDDING_INTERVAL_SECONDS,
    backoff_rate=EMBEDDING_BACKOFF_RATE,
)
def process_fact_check_item(
    item_id: str,
    community_server_id: str | None,
) -> dict[str, Any]:
    """Process a single fact-check item (DBOS step with retry).

    This step is automatically checkpointed by DBOS. If the workflow
    is interrupted, it will resume from the last completed step.

    Retry schedule: 1s, 2s, 4s, 8s, 16s (5 attempts total)

    Args:
        item_id: FactCheckItem UUID as string
        community_server_id: Optional community server for LLM credentials

    Returns:
        dict with success boolean and optional error message
    """
    try:
        result = chunk_and_embed_fact_check_sync(
            fact_check_id=UUID(item_id),
            community_server_id=UUID(community_server_id) if community_server_id else None,
        )

        return {
            "success": True,
            "item_id": item_id,
            "chunks_created": result.get("chunks_created", 0),
        }

    except Exception as e:
        logger.warning(
            "Failed to process fact-check item",
            extra={"item_id": item_id, "error": str(e)},
        )
        raise


def chunk_and_embed_fact_check_sync(
    fact_check_id: UUID,
    community_server_id: UUID | None,
) -> dict[str, Any]:
    """Synchronous wrapper for chunk_and_embed_fact_check.

    DBOS steps are synchronous, so we need to wrap the async service method.
    This fetches the FactCheckItem's content and processes it.

    Uses singleton service dependencies via get_chunk_embedding_service() for
    consistent caching (TASK-1058.27). Acquires _access_lock via
    use_chunking_service_sync() only during NeuralChunker usage (TASK-1058.39),
    not during the full DB+LLM pipeline.
    """
    from src.database import get_session_maker
    from src.fact_checking.chunking_service import use_chunking_service_sync
    from src.tasks.rechunk_tasks import get_chunk_embedding_service

    service = get_chunk_embedding_service()

    async def _fetch_content() -> str:
        async with get_session_maker()() as db:
            result = await db.execute(
                select(FactCheckItem).where(FactCheckItem.id == fact_check_id)
            )
            item = result.scalar_one_or_none()
            if item is None:
                raise ValueError(f"FactCheckItem {fact_check_id} not found")
            return item.content or ""

    text = run_sync(_fetch_content())

    with use_chunking_service_sync() as chunking_service:
        chunk_texts = chunking_service.chunk_text(text)

    async def _embed_and_persist() -> dict[str, Any]:
        async with get_session_maker()() as db:
            chunks = await service.chunk_and_embed_fact_check(
                db=db,
                fact_check_id=fact_check_id,
                text=text,
                community_server_id=community_server_id,
                chunk_texts=chunk_texts,
            )
            await db.commit()
            return {"chunks_created": len(chunks)}

    return run_sync(_embed_and_persist())


def update_batch_job_progress_sync(
    batch_job_id: UUID,
    completed_tasks: int,
    failed_tasks: int,
) -> bool:
    """Synchronous helper to update BatchJob progress from DBOS workflow."""
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            await service.update_progress(
                batch_job_id,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
            )
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to update batch job progress",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


def finalize_batch_job_sync(
    batch_job_id: UUID,
    success: bool,
    completed_tasks: int,
    failed_tasks: int,
    error_summary: dict[str, Any] | None = None,
) -> bool:
    """Synchronous helper to finalize BatchJob from DBOS workflow."""
    from src.database import get_session_maker

    async def _async_impl() -> bool:
        async with get_session_maker()() as db:
            service = BatchJobService(db)
            if success:
                await service.complete_job(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
            else:
                await service.update_progress(
                    batch_job_id,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                )
                await service.fail_job(batch_job_id, error_summary)
            await db.commit()
            return True

    try:
        return run_sync(_async_impl())
    except Exception as e:
        logger.error(
            "Failed to finalize batch job",
            extra={"batch_job_id": str(batch_job_id), "error": str(e)},
            exc_info=True,
        )
        return False


@DBOS.workflow()
def chunk_single_fact_check_workflow(
    fact_check_id: str,
    community_server_id: str | None,
) -> dict[str, Any]:
    """DBOS workflow for chunking a single fact-check item.

    This is a lightweight workflow for processing individual items
    (e.g., after candidate promotion). Uses the same step as batch
    processing for consistency.

    Args:
        fact_check_id: UUID of the FactCheckItem to process
        community_server_id: Optional community server for LLM credentials

    Returns:
        dict with success boolean and optional error message
    """
    workflow_id = DBOS.workflow_id

    logger.info(
        "Starting single fact-check chunk workflow",
        extra={
            "workflow_id": workflow_id,
            "fact_check_id": fact_check_id,
            "community_server_id": community_server_id,
        },
    )

    try:
        result = process_fact_check_item(
            item_id=fact_check_id,
            community_server_id=community_server_id,
        )

        logger.info(
            "Single fact-check chunk workflow completed",
            extra={
                "workflow_id": workflow_id,
                "fact_check_id": fact_check_id,
                "success": result["success"],
            },
        )

        return result

    except Exception as e:
        logger.error(
            "Single fact-check chunk workflow failed",
            extra={
                "workflow_id": workflow_id,
                "fact_check_id": fact_check_id,
                "error": str(e),
            },
        )
        return {
            "success": False,
            "item_id": fact_check_id,
            "error": str(e),
        }


async def enqueue_single_fact_check_chunk(
    fact_check_id: UUID,
    community_server_id: UUID | None = None,
) -> str | None:
    """Enqueue a single fact-check item for chunking via DBOS.

    This function uses DBOSClient.enqueue() to submit the workflow to the
    rechunk queue for durable processing by a DBOS worker. The client
    does not poll the queue - it only enqueues work.

    Args:
        fact_check_id: UUID of the FactCheckItem to process
        community_server_id: Optional community server for LLM credentials

    Returns:
        The DBOS workflow_id if successfully enqueued, None on failure
    """
    try:
        client = get_dbos_client()
        options: EnqueueOptions = {
            "queue_name": "rechunk",
            "workflow_name": CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
        }
        handle = await asyncio.to_thread(
            client.enqueue,
            options,
            str(fact_check_id),
            str(community_server_id) if community_server_id else None,
        )

        logger.info(
            "Enqueued single fact-check chunk via DBOS",
            extra={
                "fact_check_id": str(fact_check_id),
                "workflow_id": handle.workflow_id,
            },
        )

        return handle.workflow_id

    except Exception as e:
        logger.error(
            "Failed to enqueue single fact-check chunk via DBOS",
            extra={
                "fact_check_id": str(fact_check_id),
                "error": str(e),
            },
            exc_info=True,
        )
        return None


RECHUNK_FACT_CHECK_WORKFLOW_NAME: str = rechunk_fact_check_workflow.__qualname__
CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME: str = chunk_single_fact_check_workflow.__qualname__


def chunk_and_embed_previously_seen_sync(
    previously_seen_id: UUID,
    community_server_id: UUID,
) -> dict[str, Any]:
    """Synchronous wrapper for chunk_and_embed_previously_seen.

    DBOS steps are synchronous, so we need to wrap the async service method.
    This fetches the PreviouslySeenMessage's content from extra_metadata and
    processes it.

    Uses singleton service dependencies via get_chunk_embedding_service() for
    consistent caching. Acquires _access_lock via use_chunking_service_sync()
    only during NeuralChunker usage, not during the full DB+LLM pipeline.

    Returns:
        dict with chunks_created count. If no content, returns chunks_created=0.
    """
    from src.database import get_session_maker
    from src.fact_checking.chunking_service import use_chunking_service_sync
    from src.tasks.rechunk_tasks import get_chunk_embedding_service

    service = get_chunk_embedding_service()

    async def _fetch_content() -> str:
        async with get_session_maker()() as db:
            result = await db.execute(
                select(PreviouslySeenMessage).where(PreviouslySeenMessage.id == previously_seen_id)
            )
            item = result.scalar_one_or_none()
            if item is None:
                raise ValueError(f"PreviouslySeenMessage {previously_seen_id} not found")
            return (item.extra_metadata or {}).get("content", "")

    text = run_sync(_fetch_content())

    if not text:
        return {"chunks_created": 0}

    with use_chunking_service_sync() as chunking_service:
        chunk_texts = chunking_service.chunk_text(text)

    async def _embed_and_persist() -> dict[str, Any]:
        async with get_session_maker()() as db:
            chunks = await service.chunk_and_embed_previously_seen(
                db=db,
                previously_seen_id=previously_seen_id,
                text=text,
                community_server_id=community_server_id,
                chunk_texts=chunk_texts,
            )
            await db.commit()
            return {"chunks_created": len(chunks)}

    return run_sync(_embed_and_persist())


@DBOS.step(
    retries_allowed=EMBEDDING_RETRIES_ALLOWED,
    max_attempts=EMBEDDING_MAX_ATTEMPTS,
    interval_seconds=EMBEDDING_INTERVAL_SECONDS,
    backoff_rate=EMBEDDING_BACKOFF_RATE,
)
def process_previously_seen_item(
    item_id: str,
    community_server_id: str,
) -> dict[str, Any]:
    """Process a single previously-seen message (DBOS step with retry).

    This step is automatically checkpointed by DBOS. If the workflow
    is interrupted, it will resume from the last completed step.

    Retry schedule: 1s, 2s, 4s, 8s, 16s (5 attempts total)

    Args:
        item_id: PreviouslySeenMessage UUID as string
        community_server_id: Community server UUID as string

    Returns:
        dict with success boolean and optional error message
    """
    try:
        result = chunk_and_embed_previously_seen_sync(
            previously_seen_id=UUID(item_id),
            community_server_id=UUID(community_server_id),
        )

        return {
            "success": True,
            "item_id": item_id,
            "chunks_created": result.get("chunks_created", 0),
        }

    except Exception as e:
        logger.warning(
            "Failed to process previously-seen message",
            extra={"item_id": item_id, "error": str(e)},
        )
        raise


@DBOS.workflow()
def rechunk_previously_seen_workflow(
    batch_job_id: str,
    community_server_id: str,
    item_ids: list[str],
    batch_size: int = 100,
) -> dict[str, Any]:
    """DBOS workflow for rechunking previously-seen messages.

    Args:
        batch_job_id: UUID of the BatchJob record (as string)
        community_server_id: Community server UUID (as string)
        item_ids: List of PreviouslySeenMessage UUIDs to process
        batch_size: Items per batch (for progress reporting)

    Returns:
        dict with completed_count, failed_count, and any errors
    """
    workflow_id = DBOS.workflow_id
    total_items = len(item_ids)

    logger.info(
        "Starting previously-seen rechunk workflow",
        extra={
            "workflow_id": workflow_id,
            "batch_job_id": batch_job_id,
            "community_server_id": community_server_id,
            "total_items": total_items,
        },
    )

    circuit_breaker = CircuitBreaker(
        threshold=5,
        reset_timeout=60,
    )

    completed_count = 0
    failed_count = 0
    errors: list[dict[str, Any]] = []

    for i, item_id in enumerate(item_ids):
        try:
            circuit_breaker.check()

            result = process_previously_seen_item(
                item_id=item_id,
                community_server_id=community_server_id,
            )

            if result["success"]:
                completed_count += 1
                circuit_breaker.record_success()
            else:
                failed_count += 1
                errors.append({"item_id": item_id, "error": result.get("error")})

        except CircuitOpenError:
            logger.error(
                "Circuit breaker open - pausing previously-seen rechunk workflow",
                extra={
                    "workflow_id": workflow_id,
                    "consecutive_failures": circuit_breaker.failures,
                },
            )
            update_batch_job_progress_sync(
                UUID(batch_job_id),
                completed_tasks=completed_count,
                failed_tasks=failed_count,
            )
            raise

        except Exception as e:
            failed_count += 1
            errors.append({"item_id": item_id, "error": str(e)})
            circuit_breaker.record_failure()

        if (i + 1) % batch_size == 0 or (i + 1) == total_items:
            update_batch_job_progress_sync(
                UUID(batch_job_id),
                completed_tasks=completed_count,
                failed_tasks=failed_count,
            )

    success = failed_count == 0
    error_summary = {"errors": errors} if errors else None
    finalize_batch_job_sync(
        UUID(batch_job_id),
        success=success,
        completed_tasks=completed_count,
        failed_tasks=failed_count,
        error_summary=error_summary,
    )

    logger.info(
        "Previously-seen rechunk workflow completed",
        extra={
            "workflow_id": workflow_id,
            "completed": completed_count,
            "failed": failed_count,
        },
    )

    return {
        "completed_count": completed_count,
        "failed_count": failed_count,
        "errors": errors,
    }


async def dispatch_dbos_previously_seen_rechunk_workflow(
    db: AsyncSession,
    community_server_id: UUID,
    batch_size: int = 100,
    metadata: dict[str, Any] | None = None,
) -> UUID:
    """Dispatch a DBOS rechunk workflow for previously-seen messages.

    This function:
    1. Fetches item IDs to process
    2. Creates a BatchJob record (PENDING)
    3. Starts the BatchJob (IN_PROGRESS)
    4. Enqueues the DBOS workflow
    5. Updates BatchJob with workflow_id

    Args:
        db: Database session
        community_server_id: Community server filter
        batch_size: Items per progress update
        metadata: Additional job metadata

    Returns:
        BatchJob UUID

    Raises:
        ValueError: If no previously-seen messages to process
        Exception: If workflow dispatch fails (BatchJob marked as FAILED)
    """
    stmt = (
        select(PreviouslySeenMessage.id)
        .where(PreviouslySeenMessage.community_server_id == community_server_id)
        .order_by(PreviouslySeenMessage.created_at)
    )

    result = await db.execute(stmt)
    item_ids = [str(row[0]) for row in result.fetchall()]

    if not item_ids:
        raise ValueError("No previously-seen messages to process")

    batch_job_service = BatchJobService(db)
    job_metadata = {
        "community_server_id": str(community_server_id),
        "batch_size": batch_size,
        "chunk_type": "previously_seen",
        "execution_backend": "dbos",
        **(metadata or {}),
    }

    job = await batch_job_service.create_job(
        BatchJobCreate(
            job_type=RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE,
            total_tasks=len(item_ids),
            metadata=job_metadata,
        )
    )

    await batch_job_service.start_job(job.id)
    await db.commit()
    await db.refresh(job)

    try:
        client = get_dbos_client()
        options: EnqueueOptions = {
            "queue_name": "rechunk",
            "workflow_name": RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME,
        }
        handle = await asyncio.to_thread(
            client.enqueue,
            options,
            str(job.id),
            str(community_server_id),
            item_ids,
            batch_size,
        )
        workflow_id = handle.workflow_id
    except Exception as e:
        await batch_job_service.fail_job(
            job.id,
            error_summary={"stage": "dispatch", "error": str(e)},
        )
        await db.commit()
        logger.error(
            "Failed to dispatch DBOS previously-seen rechunk workflow",
            extra={"batch_job_id": str(job.id), "error": str(e)},
            exc_info=True,
        )
        raise

    await batch_job_service.set_workflow_id(job.id, workflow_id)
    await db.commit()

    logger.info(
        "DBOS previously-seen rechunk workflow dispatched",
        extra={
            "batch_job_id": str(job.id),
            "workflow_id": workflow_id,
            "total_items": len(item_ids),
            "community_server_id": str(community_server_id),
        },
    )

    return job.id


RECHUNK_PREVIOUSLY_SEEN_WORKFLOW_NAME: str = rechunk_previously_seen_workflow.__qualname__
