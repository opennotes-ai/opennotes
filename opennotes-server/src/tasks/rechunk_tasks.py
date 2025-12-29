"""
TaskIQ tasks for chunk re-embedding operations.

These tasks handle background processing of:
- FactCheckItem content re-chunking and re-embedding
- PreviouslySeenMessage content re-chunking and re-embedding

Tasks are designed to be self-contained, creating their own database and Redis
connections to work reliably in distributed worker environments.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.cache.redis_client import RedisClient
from src.config import get_settings
from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunk_task_schemas import RechunkTaskStatus
from src.fact_checking.chunk_task_tracker import RechunkTaskTracker
from src.fact_checking.chunking_service import ChunkingService
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.tasks.broker import register_task

logger = get_logger(__name__)


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


class RechunkLockManager:
    """
    Distributed lock manager for rechunk operations using Redis.

    This is a simplified version for use within TaskIQ tasks. The lock manager
    needs to be recreated in each task because tasks run in separate worker
    processes that don't share the main application's Redis connection.
    """

    LOCK_TTL_SECONDS = 3600
    LOCK_PREFIX = "rechunk:lock"

    def __init__(self, redis_client: RedisClient):
        self._redis_client = redis_client

    def _get_lock_key(self, operation: str, resource_id: str | None = None) -> str:
        """Generate lock key for an operation."""
        if resource_id:
            return f"{self.LOCK_PREFIX}:{operation}:{resource_id}"
        return f"{self.LOCK_PREFIX}:{operation}"

    async def release_lock(self, operation: str, resource_id: str | None = None) -> bool:
        """Release a lock for a rechunk operation."""
        if not self._redis_client.client:
            return True

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self._redis_client.client.delete(key)
            logger.info(
                "Released rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "key": key},
            )
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to release rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return False


@register_task()
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
    lock_manager = RechunkLockManager(redis_client_bg)

    service = get_chunk_embedding_service()
    processed_count = 0

    try:
        await tracker.update_status(task_uuid, RechunkTaskStatus.IN_PROGRESS)

        async with async_session() as db:
            offset = 0

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
                    await service.chunk_and_embed_fact_check(
                        db=db,
                        fact_check_id=item.id,
                        text=item.content,
                        community_server_id=community_uuid,
                    )
                    processed_count += 1

                await db.commit()
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


@register_task()
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
    lock_manager = RechunkLockManager(redis_client_bg)

    service = get_chunk_embedding_service()
    processed_count = 0

    try:
        await tracker.update_status(task_uuid, RechunkTaskStatus.IN_PROGRESS)

        async with async_session() as db:
            offset = 0

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
                        await service.chunk_and_embed_previously_seen(
                            db=db,
                            previously_seen_id=msg.id,
                            text=content,
                            community_server_id=community_uuid,
                        )
                    processed_count += 1

                await db.commit()
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
