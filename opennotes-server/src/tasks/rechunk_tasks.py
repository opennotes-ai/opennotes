"""
TaskIQ tasks for chunk re-embedding operations.

These tasks handle background processing of:
- FactCheckItem content re-chunking and re-embedding
- PreviouslySeenMessage content re-chunking and re-embedding

Tasks are designed to be self-contained, creating their own database and Redis
connections to work reliably in distributed worker environments.

OpenTelemetry Integration:
- Tasks are instrumented with spans for tracing
- Exceptions are recorded on spans with proper error status
- Trace context is propagated via TaskIQ's OpenTelemetryMiddleware

Deadlock Handling:
- Individual items are processed with retry logic for deadlock recovery
- Each retry uses a fresh database session to avoid corrupted transaction state
- Exponential backoff prevents thundering herd on retry
"""

import asyncio
import random
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.cache.redis_client import RedisClient
from src.common.db_retry import is_deadlock_error
from src.config import get_settings
from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunk_task_schemas import RechunkTaskStatus
from src.fact_checking.chunk_task_tracker import RechunkTaskTracker
from src.fact_checking.chunking_service import ChunkingService
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.fact_checking.rechunk_lock import TaskRechunkLockManager
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


def get_chunk_embedding_service() -> ChunkEmbeddingService:
    """Create ChunkEmbeddingService with required dependencies."""
    settings = get_settings()
    llm_client_manager = LLMClientManager(
        encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    )
    llm_service = LLMService(client_manager=llm_client_manager)
    chunking_service = ChunkingService()
    return ChunkEmbeddingService(
        chunking_service=chunking_service,
        llm_service=llm_service,
    )


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


@register_task(task_name="rechunk:fact_check", component="rechunk", task_type="batch")
async def process_fact_check_rechunk_task(
    task_id: str,
    community_server_id: str | None,
    batch_size: int,
    db_url: str,
    redis_url: str,
) -> dict:
    """
    TaskIQ task to process fact check item re-chunking.

    This task:
    1. Queries all FactCheckItem records
    2. For each item, clears existing FactCheckChunk entries
    3. Re-chunks and embeds the content using ChunkEmbeddingService
    4. Updates task progress in Redis
    5. Releases the lock when complete

    Args:
        task_id: UUID string of the task for status tracking
        community_server_id: UUID string of the community server for LLM credentials,
            or None to use global fallback
        batch_size: Number of items to process in each batch
        db_url: Database connection URL
        redis_url: Redis connection URL for task tracking

    Returns:
        dict with status and processed_count
    """
    with _tracer.start_as_current_span("rechunk.fact_check") as span:
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.type", "fact_check")
        span.set_attribute("task.community_server_id", community_server_id or "global")
        span.set_attribute("task.batch_size", batch_size)

        settings = get_settings()
        task_uuid = UUID(task_id)
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
        tracker = RechunkTaskTracker(redis_client_bg)
        lock_manager = TaskRechunkLockManager(redis_client_bg)

        service = get_chunk_embedding_service()

        existing_task = await tracker.get_task(task_uuid)
        if existing_task and existing_task.processed_count > 0:
            processed_count = existing_task.processed_count
            offset = processed_count
            logger.info(
                "Resuming fact check rechunk from previous progress",
                extra={
                    "task_id": task_id,
                    "resumed_from_count": processed_count,
                },
            )
            span.set_attribute("task.resumed", True)
            span.set_attribute("task.resumed_from_count", processed_count)
        else:
            processed_count = 0
            offset = 0
            span.set_attribute("task.resumed", False)

        try:
            await tracker.update_status(task_uuid, RechunkTaskStatus.IN_PROGRESS)

            async with async_session() as db:
                total_count_result = await db.execute(select(func.count(FactCheckItem.id)))
                total_items = total_count_result.scalar() or 0

                if offset > total_items:
                    logger.warning(
                        "Stored progress exceeds current item count, resetting offset",
                        extra={
                            "task_id": task_id,
                            "stored_offset": offset,
                            "total_items": total_items,
                        },
                    )
                    offset = 0
                    processed_count = 0
                    span.add_event(
                        "progress_reset",
                        {"reason": "stored_offset_exceeds_total", "total_items": total_items},
                    )

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
                        await _process_fact_check_item_with_retry(
                            engine=engine,
                            service=service,
                            item_id=item.id,
                            item_content=item.content,
                            community_server_id=community_uuid,
                        )
                        processed_count += 1

                    offset += batch_size

                    await tracker.update_progress(task_uuid, processed_count)

                    logger.info(
                        "Processed fact check rechunk batch",
                        extra={
                            "task_id": task_id,
                            "community_server_id": community_server_id,
                            "processed_count": processed_count,
                            "batch_offset": offset,
                        },
                    )

            await tracker.mark_completed(task_uuid, processed_count)
            span.set_attribute("task.processed_count", processed_count)

            logger.info(
                "Completed fact check rechunking",
                extra={
                    "task_id": task_id,
                    "community_server_id": community_server_id,
                    "total_processed": processed_count,
                },
            )

            return {"status": "completed", "processed_count": processed_count}
        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            await tracker.mark_failed(task_uuid, error_msg, processed_count)

            logger.error(
                "Failed to process fact check rechunk batch",
                extra={
                    "task_id": task_id,
                    "community_server_id": community_server_id,
                    "processed_count": processed_count,
                    "error": error_msg,
                },
                exc_info=True,
            )
            raise
        finally:
            await redis_client_bg.disconnect()
            await engine.dispose()
            await lock_manager.release_lock("fact_check")


@register_task(task_name="rechunk:previously_seen", component="rechunk", task_type="batch")
async def process_previously_seen_rechunk_task(
    task_id: str,
    community_server_id: str,
    batch_size: int,
    db_url: str,
    redis_url: str,
) -> dict:
    """
    TaskIQ task to process previously seen message re-chunking.

    This task:
    1. Queries PreviouslySeenMessage records for the specified community
    2. For each message, clears existing PreviouslySeenChunk entries
    3. Re-chunks and embeds the content using ChunkEmbeddingService
    4. Updates task progress in Redis
    5. Releases the lock when complete

    Args:
        task_id: UUID string of the task for status tracking
        community_server_id: UUID string of the community server
        batch_size: Number of items to process in each batch
        db_url: Database connection URL
        redis_url: Redis connection URL for task tracking

    Returns:
        dict with status and processed_count
    """
    with _tracer.start_as_current_span("rechunk.previously_seen") as span:
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.type", "previously_seen")
        span.set_attribute("task.community_server_id", community_server_id)
        span.set_attribute("task.batch_size", batch_size)

        settings = get_settings()
        task_uuid = UUID(task_id)
        community_uuid = UUID(community_server_id)

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
        tracker = RechunkTaskTracker(redis_client_bg)
        lock_manager = TaskRechunkLockManager(redis_client_bg)

        service = get_chunk_embedding_service()

        existing_task = await tracker.get_task(task_uuid)
        if existing_task and existing_task.processed_count > 0:
            processed_count = existing_task.processed_count
            offset = processed_count
            logger.info(
                "Resuming previously seen rechunk from previous progress",
                extra={
                    "task_id": task_id,
                    "community_server_id": community_server_id,
                    "resumed_from_count": processed_count,
                },
            )
            span.set_attribute("task.resumed", True)
            span.set_attribute("task.resumed_from_count", processed_count)
        else:
            processed_count = 0
            offset = 0
            span.set_attribute("task.resumed", False)

        try:
            await tracker.update_status(task_uuid, RechunkTaskStatus.IN_PROGRESS)

            async with async_session() as db:
                total_count_result = await db.execute(
                    select(func.count(PreviouslySeenMessage.id)).where(
                        PreviouslySeenMessage.community_server_id == community_uuid
                    )
                )
                total_items = total_count_result.scalar() or 0

                if offset > total_items:
                    logger.warning(
                        "Stored progress exceeds current item count, resetting offset",
                        extra={
                            "task_id": task_id,
                            "community_server_id": community_server_id,
                            "stored_offset": offset,
                            "total_items": total_items,
                        },
                    )
                    offset = 0
                    processed_count = 0
                    span.add_event(
                        "progress_reset",
                        {"reason": "stored_offset_exceeds_total", "total_items": total_items},
                    )

                while True:
                    result = await db.execute(
                        select(PreviouslySeenMessage)
                        .where(PreviouslySeenMessage.community_server_id == community_uuid)
                        .order_by(PreviouslySeenMessage.created_at)
                        .offset(offset)
                        .limit(batch_size)
                    )
                    messages = result.scalars().all()

                    if not messages:
                        break

                    for msg in messages:
                        content = (msg.extra_metadata or {}).get("content", "")
                        if content:
                            await _process_previously_seen_item_with_retry(
                                engine=engine,
                                service=service,
                                item_id=msg.id,
                                item_content=content,
                                community_server_id=community_uuid,
                            )
                        processed_count += 1

                    offset += batch_size

                    await tracker.update_progress(task_uuid, processed_count)

                    logger.info(
                        "Processed previously seen rechunk batch",
                        extra={
                            "task_id": task_id,
                            "community_server_id": community_server_id,
                            "processed_count": processed_count,
                            "batch_offset": offset,
                        },
                    )

            await tracker.mark_completed(task_uuid, processed_count)
            span.set_attribute("task.processed_count", processed_count)

            logger.info(
                "Completed previously seen message rechunking",
                extra={
                    "task_id": task_id,
                    "community_server_id": community_server_id,
                    "total_processed": processed_count,
                },
            )

            return {"status": "completed", "processed_count": processed_count}
        except Exception as e:
            error_msg = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, error_msg)
            await tracker.mark_failed(task_uuid, error_msg, processed_count)

            logger.error(
                "Failed to process previously seen rechunk batch",
                extra={
                    "task_id": task_id,
                    "community_server_id": community_server_id,
                    "processed_count": processed_count,
                    "error": error_msg,
                },
                exc_info=True,
            )
            raise
        finally:
            await redis_client_bg.disconnect()
            await engine.dispose()
            await lock_manager.release_lock("previously_seen", community_server_id)
