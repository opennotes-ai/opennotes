"""
TaskIQ tasks for chunk re-embedding operations.

DEPRECATION NOTICE:
    All rechunk tasks (fact_check, previously_seen, chunk:fact_check_item) have been
    migrated to DBOS workflows for improved reliability. The TaskIQ task functions
    are retained as deprecated no-op stubs to drain legacy JetStream messages.
    See src/dbos_workflows/rechunk_workflow.py for the DBOS implementations.

    Remove all deprecated stubs after 2026-04-01.

These tasks handle background processing of:
- FactCheckItem operations are handled by DBOS workflows (TASK-1056)
- PreviouslySeenMessage operations are handled by DBOS workflows (TASK-1095)

Service singletons (get_chunk_embedding_service, etc.) are still used by
DBOS workflow steps and must remain in this module.

Deadlock Handling:
- Individual items are processed with retry logic for deadlock recovery
- Each retry uses a fresh database session to avoid corrupted transaction state
- Exponential backoff prevents thundering herd on retry
"""

import asyncio
import random
import threading
from typing import Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.batch_jobs.models import BatchJobStatus
from src.batch_jobs.progress_tracker import BatchJobProgressTracker
from src.batch_jobs.service import BatchJobService
from src.cache.redis_client import RedisClient
from src.common.db_retry import is_deadlock_error
from src.config import get_settings
from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunking_service import (
    reset_chunking_service,
    use_chunking_service_sync,
)
from src.fact_checking.models import FactCheckItem
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)
_tracer = trace.get_tracer(__name__)

MAX_DEADLOCK_RETRIES = 3
DEADLOCK_BASE_DELAY = 0.1
DEADLOCK_MAX_DELAY = 2.0

_encryption_service: EncryptionService | None = None
_llm_client_manager: LLMClientManager | None = None
_llm_service: LLMService | None = None
_chunk_embedding_service: ChunkEmbeddingService | None = None
_service_lock = threading.RLock()


def _get_encryption_service() -> EncryptionService:
    """Get or create singleton EncryptionService with double-checked locking."""
    global _encryption_service  # noqa: PLW0603
    if _encryption_service is None:
        with _service_lock:
            if _encryption_service is None:
                settings = get_settings()
                _encryption_service = EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    return _encryption_service


def _get_llm_client_manager() -> LLMClientManager:
    """Get or create singleton LLMClientManager with double-checked locking."""
    global _llm_client_manager  # noqa: PLW0603
    if _llm_client_manager is None:
        with _service_lock:
            if _llm_client_manager is None:
                _llm_client_manager = LLMClientManager(encryption_service=_get_encryption_service())
    return _llm_client_manager


def _get_llm_service() -> LLMService:
    """Get or create singleton LLMService with double-checked locking."""
    global _llm_service  # noqa: PLW0603
    if _llm_service is None:
        with _service_lock:
            if _llm_service is None:
                _llm_service = LLMService(client_manager=_get_llm_client_manager())
    return _llm_service


def get_chunk_embedding_service() -> ChunkEmbeddingService:
    """Get or create singleton ChunkEmbeddingService with double-checked locking.

    All service dependencies are also singletons, ensuring consistent caching
    behavior for LLM clients and avoiding repeated model loading.

    Lock ordering: acquires _service_lock and _access_lock (via
    use_chunking_service_sync) independently to avoid ABBA deadlock with
    callers that acquire _access_lock without _service_lock (TASK-1061.06).
    """
    global _chunk_embedding_service  # noqa: PLW0603
    if _chunk_embedding_service is None:
        with _service_lock:
            if _chunk_embedding_service is not None:
                return _chunk_embedding_service
            llm_service = _get_llm_service()

        with use_chunking_service_sync() as chunking_service:
            service = ChunkEmbeddingService(
                chunking_service=chunking_service,
                llm_service=llm_service,
            )

        with _service_lock:
            if _chunk_embedding_service is None:
                _chunk_embedding_service = service
    return _chunk_embedding_service


def reset_task_services() -> None:
    """Reset all service singletons. For testing only."""
    global _encryption_service, _llm_client_manager  # noqa: PLW0603
    global _llm_service, _chunk_embedding_service  # noqa: PLW0603
    with _service_lock:
        _encryption_service = None
        _llm_client_manager = None
        _llm_service = None
        _chunk_embedding_service = None
    reset_chunking_service()


async def _process_fact_check_item_with_retry(
    engine: AsyncEngine,
    service: ChunkEmbeddingService,
    item_id: UUID,
    item_content: str,
    community_server_id: UUID | None,
) -> None:
    """
    Process a single fact check item with deadlock retry.

    Uses a fresh database session for each retry attempt to avoid corrupted
    transaction state after a deadlock rollback.

    Args:
        engine: Database engine for creating sessions
        service: ChunkEmbeddingService instance
        item_id: UUID of the fact check item
        item_content: Text content to chunk and embed
        community_server_id: Optional community server ID for LLM credentials
    """
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    last_exception: Exception | None = None

    for attempt in range(1, MAX_DEADLOCK_RETRIES + 1):
        try:
            async with async_session() as db:
                await service.chunk_and_embed_fact_check(
                    db=db,
                    fact_check_id=item_id,
                    text=item_content,
                    community_server_id=community_server_id,
                )
                await db.commit()
                return
        except Exception as e:
            if not is_deadlock_error(e):
                raise

            last_exception = e

            if attempt >= MAX_DEADLOCK_RETRIES:
                logger.warning(
                    "Deadlock retry exhausted for fact check item",
                    extra={
                        "fact_check_id": str(item_id),
                        "attempt": attempt,
                        "max_attempts": MAX_DEADLOCK_RETRIES,
                    },
                )
                raise

            delay = min(DEADLOCK_BASE_DELAY * (2 ** (attempt - 1)), DEADLOCK_MAX_DELAY)
            jittered_delay = delay * (1 + random.uniform(-0.1, 0.1))

            logger.info(
                "Deadlock detected for fact check item, retrying",
                extra={
                    "fact_check_id": str(item_id),
                    "attempt": attempt,
                    "max_attempts": MAX_DEADLOCK_RETRIES,
                    "delay_seconds": round(jittered_delay, 3),
                },
            )

            await asyncio.sleep(jittered_delay)

    if last_exception:
        raise last_exception


async def _process_previously_seen_item_with_retry(
    engine: AsyncEngine,
    service: ChunkEmbeddingService,
    item_id: UUID,
    item_content: str,
    community_server_id: UUID,
) -> None:
    """
    Process a single previously seen message with deadlock retry.

    Uses a fresh database session for each retry attempt to avoid corrupted
    transaction state after a deadlock rollback.

    Args:
        engine: Database engine for creating sessions
        service: ChunkEmbeddingService instance
        item_id: UUID of the previously seen message
        item_content: Text content to chunk and embed
        community_server_id: Community server ID for LLM credentials
    """
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    last_exception: Exception | None = None

    for attempt in range(1, MAX_DEADLOCK_RETRIES + 1):
        try:
            async with async_session() as db:
                await service.chunk_and_embed_previously_seen(
                    db=db,
                    previously_seen_id=item_id,
                    text=item_content,
                    community_server_id=community_server_id,
                )
                await db.commit()
                return
        except Exception as e:
            if not is_deadlock_error(e):
                raise

            last_exception = e

            if attempt >= MAX_DEADLOCK_RETRIES:
                logger.warning(
                    "Deadlock retry exhausted for previously seen message",
                    extra={
                        "previously_seen_id": str(item_id),
                        "attempt": attempt,
                        "max_attempts": MAX_DEADLOCK_RETRIES,
                    },
                )
                raise

            delay = min(DEADLOCK_BASE_DELAY * (2 ** (attempt - 1)), DEADLOCK_MAX_DELAY)
            jittered_delay = delay * (1 + random.uniform(-0.1, 0.1))

            logger.info(
                "Deadlock detected for previously seen message, retrying",
                extra={
                    "previously_seen_id": str(item_id),
                    "attempt": attempt,
                    "max_attempts": MAX_DEADLOCK_RETRIES,
                    "delay_seconds": round(jittered_delay, 3),
                },
            )

            await asyncio.sleep(jittered_delay)

    if last_exception:
        raise last_exception


async def chunk_fact_check_item_task(
    fact_check_id: str,
    community_server_id: str | None,
    db_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to chunk and embed a single fact check item.

    This task is enqueued when a candidate is promoted to a fact check item.
    It performs the same chunking/embedding as the batch rechunk task but for
    a single item, without BatchJob infrastructure.

    Args:
        fact_check_id: UUID string of the fact check item to process
        community_server_id: UUID string of the community server for LLM credentials,
            or None to use global fallback
        db_url: Database connection URL

    Returns:
        dict with status and fact_check_id
    """
    with _tracer.start_as_current_span("chunk.fact_check_item") as span:
        span.set_attribute("task.id", fact_check_id)
        span.set_attribute("task.community_server_id", community_server_id or "global")

        settings = get_settings()
        fact_check_uuid = UUID(fact_check_id)
        community_uuid = UUID(community_server_id) if community_server_id else None

        engine = create_async_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_POOL_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        service = get_chunk_embedding_service()

        try:
            async with async_session() as db:
                result = await db.execute(
                    select(FactCheckItem).where(FactCheckItem.id == fact_check_uuid)
                )
                item = result.scalar_one_or_none()

                if not item:
                    logger.warning(
                        "Fact check item not found for chunking",
                        extra={"fact_check_id": fact_check_id},
                    )
                    span.set_status(StatusCode.ERROR, "Item not found")
                    return {"status": "not_found", "fact_check_id": fact_check_id}

                if not item.content:
                    logger.warning(
                        "Fact check item has no content for chunking",
                        extra={"fact_check_id": fact_check_id},
                    )
                    span.set_status(StatusCode.ERROR, "No content")
                    return {"status": "no_content", "fact_check_id": fact_check_id}

                item_content = item.content

            await _process_fact_check_item_with_retry(
                engine=engine,
                service=service,
                item_id=fact_check_uuid,
                item_content=item_content,
                community_server_id=community_uuid,
            )

            logger.info(
                "Completed chunking for promoted fact check item",
                extra={
                    "fact_check_id": fact_check_id,
                    "community_server_id": community_server_id,
                },
            )

            return {"status": "completed", "fact_check_id": fact_check_id}

        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)

            logger.error(
                "Failed to chunk fact check item",
                extra={
                    "fact_check_id": fact_check_id,
                    "community_server_id": community_server_id,
                    "error": error_msg,
                },
            )
            raise
        finally:
            await engine.dispose()


async def process_fact_check_rechunk_task(
    job_id: str,
    community_server_id: str | None,
    batch_size: int,
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    """
    TaskIQ task to process fact check item re-chunking.

    This task:
    1. Queries all FactCheckItem records
    2. For each item, clears existing FactCheckChunk entries
    3. Re-chunks and embeds the content using ChunkEmbeddingService
    4. Updates job progress via BatchJobService
    5. Releases the lock when complete

    Args:
        job_id: UUID string of the batch job for status tracking
        community_server_id: UUID string of the community server for LLM credentials,
            or None to use global fallback
        batch_size: Number of items to process in each batch
        db_url: Database connection URL
        redis_url: Redis connection URL for progress tracking

    Returns:
        dict with status and processed_count
    """
    with _tracer.start_as_current_span("rechunk.fact_check") as span:
        span.set_attribute("job.id", job_id)
        span.set_attribute("job.type", "fact_check")
        span.set_attribute("job.community_server_id", community_server_id or "global")
        span.set_attribute("job.batch_size", batch_size)

        settings = get_settings()
        job_uuid = UUID(job_id)
        community_uuid = UUID(community_server_id) if community_server_id else None

        engine = create_async_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_POOL_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        redis_client_bg = RedisClient()
        await redis_client_bg.connect(redis_url)
        progress_tracker = BatchJobProgressTracker(redis_client_bg)

        service = get_chunk_embedding_service()

        progress = await progress_tracker.get_progress(job_uuid)
        if progress and progress.processed_count > 0:
            processed_count = progress.processed_count
            logger.info(
                "Resuming fact check rechunk from previous progress",
                extra={
                    "job_id": job_id,
                    "resumed_from_count": processed_count,
                },
            )
            span.set_attribute("job.resumed", True)
            span.set_attribute("job.resumed_from_count", processed_count)
        else:
            processed_count = 0
            span.set_attribute("job.resumed", False)

        failed_count = 0
        offset = 0

        item_errors: list[dict[str, Any]] = []
        try:
            async with async_session() as db:
                while True:
                    result = await db.execute(
                        select(FactCheckItem)
                        .order_by(FactCheckItem.created_at)
                        .offset(offset)
                        .limit(batch_size)
                    )
                    items = result.scalars().all()

                    if not items:
                        break

                    for item in items:
                        item_id_str = str(item.id)
                        if await progress_tracker.is_item_processed_by_id(job_uuid, item_id_str):
                            logger.debug(
                                "Skipping already processed item",
                                extra={
                                    "job_id": job_id,
                                    "item_id": item_id_str,
                                },
                            )
                            continue

                        try:
                            await _process_fact_check_item_with_retry(
                                engine=engine,
                                service=service,
                                item_id=item.id,
                                item_content=item.content,
                                community_server_id=community_uuid,
                            )
                            await progress_tracker.mark_item_processed_by_id(job_uuid, item_id_str)
                            processed_count += 1
                        except Exception as item_error:
                            await progress_tracker.mark_item_failed_by_id(job_uuid, item_id_str)
                            failed_count += 1
                            item_errors.append(
                                {
                                    "item_id": item_id_str,
                                    "error": str(item_error),
                                }
                            )
                            logger.error(
                                "Failed to process fact check item",
                                extra={
                                    "job_id": job_id,
                                    "item_id": item_id_str,
                                    "error": str(item_error),
                                },
                            )

                        try:
                            await progress_tracker.update_progress(
                                job_uuid,
                                processed_count=processed_count,
                                error_count=failed_count,
                            )
                        except Exception as progress_error:
                            logger.warning(
                                "Failed to update progress, continuing",
                                extra={
                                    "job_id": job_id,
                                    "error": str(progress_error),
                                },
                            )

                    offset += batch_size

                    logger.info(
                        "Processed fact check rechunk batch",
                        extra={
                            "job_id": job_id,
                            "community_server_id": community_server_id,
                            "processed_count": processed_count,
                            "failed_count": failed_count,
                            "batch_offset": offset,
                        },
                    )

            async with async_session() as session:
                batch_job_service = BatchJobService(session, progress_tracker)
                await batch_job_service.complete_job(
                    job_uuid,
                    completed_tasks=processed_count,
                    failed_tasks=failed_count,
                )
                await session.commit()

            await progress_tracker.clear_item_tracking(job_uuid)

            span.set_attribute("job.processed_count", processed_count)
            span.set_attribute("job.failed_count", failed_count)

            logger.info(
                "Completed fact check rechunking",
                extra={
                    "job_id": job_id,
                    "community_server_id": community_server_id,
                    "total_processed": processed_count,
                    "total_failed": failed_count,
                },
            )

            return {
                "status": BatchJobStatus.COMPLETED.value,
                "processed_count": processed_count,
                "failed_count": failed_count,
            }
        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            span.set_attribute("job.item_errors", len(item_errors))

            logger.warning(
                "Fact check rechunk batch failed, will retry if attempts remain",
                extra={
                    "job_id": job_id,
                    "community_server_id": community_server_id,
                    "processed_count": processed_count,
                    "failed_count": failed_count,
                    "item_errors": item_errors[:10],
                    "error": error_msg,
                },
            )
            raise
        finally:
            await redis_client_bg.disconnect()
            await engine.dispose()


@register_task(
    task_name="rechunk:previously_seen",
    component="rechunk",
    task_type="deprecated",
)
async def process_previously_seen_rechunk_task(*args, **kwargs) -> None:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1095. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated rechunk:previously_seen message - discarding",
        extra={
            "task_name": "rechunk:previously_seen",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1095",
        },
    )


@register_task(
    task_name="rechunk:fact_check",
    component="rechunk",
    task_type="deprecated",
)
async def deprecated_fact_check_rechunk_task(*args, **kwargs) -> None:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1056. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated rechunk:fact_check message - discarding",
        extra={
            "task_name": "rechunk:fact_check",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1056",
        },
    )


@register_task(
    task_name="chunk:fact_check_item",
    component="rechunk",
    task_type="deprecated",
)
async def deprecated_chunk_fact_check_item_task(*args, **kwargs) -> None:
    """Deprecated no-op handler to drain legacy messages from pre-DBOS migration.

    This task was migrated to DBOS in TASK-1056. This handler exists only to
    acknowledge and discard stale messages in the JetStream queue.

    The task will automatically ACK the message after this function returns,
    preventing infinite redelivery of legacy messages.

    Remove after 2026-04-01 when all legacy messages have been drained.
    """
    logger.info(
        "Received deprecated chunk:fact_check_item message - discarding",
        extra={
            "task_name": "chunk:fact_check_item",
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            "migration_note": "Task migrated to DBOS in TASK-1056",
        },
    )
