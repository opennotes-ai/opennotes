"""
API router for chunk re-embedding operations.

This module provides endpoints for bulk re-chunking and re-embedding of:
- FactCheckItem content
- PreviouslySeenMessage content

These endpoints are useful for:
- Re-processing content after embedding model changes
- Migrating to chunk-based embeddings from full-document embeddings
- Refreshing embeddings with updated chunking parameters
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.config import settings
from src.database import get_db
from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunk_models import FactCheckChunk, PreviouslySeenChunk
from src.fact_checking.chunking_service import ChunkingService
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/chunks", tags=["chunks"])


def get_chunk_embedding_service() -> ChunkEmbeddingService:
    """Create ChunkEmbeddingService with required dependencies."""
    llm_client_manager = LLMClientManager(
        encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    )
    llm_service = LLMService(client_manager=llm_client_manager)
    chunking_service = ChunkingService()
    return ChunkEmbeddingService(
        chunking_service=chunking_service,
        llm_service=llm_service,
    )


async def process_fact_check_rechunk_batch(
    community_server_id: UUID,
    batch_size: int,
    db_url: str,
) -> None:
    """
    Background task to process fact check item re-chunking.

    This function:
    1. Queries FactCheckItem records (all items, as they don't have community_server_id)
    2. For each item, clears existing FactCheckChunk entries
    3. Re-chunks and embeds the content using ChunkEmbeddingService

    Args:
        community_server_id: UUID of the community server for LLM credentials
        batch_size: Number of items to process in each batch
        db_url: Database connection URL
    """
    from sqlalchemy.ext.asyncio import (  # noqa: PLC0415
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    service = get_chunk_embedding_service()

    async with async_session() as db:
        offset = 0
        processed_count = 0

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
                await db.execute(
                    delete(FactCheckChunk).where(FactCheckChunk.fact_check_id == item.id)
                )

                await service.chunk_and_embed_fact_check(
                    db=db,
                    fact_check_id=item.id,
                    text=item.content,
                    community_server_id=community_server_id,
                )
                processed_count += 1

            await db.commit()
            offset += batch_size

            logger.info(
                "Processed fact check rechunk batch",
                extra={
                    "community_server_id": str(community_server_id),
                    "processed_count": processed_count,
                    "batch_offset": offset,
                },
            )

    await engine.dispose()

    logger.info(
        "Completed fact check rechunking",
        extra={
            "community_server_id": str(community_server_id),
            "total_processed": processed_count,
        },
    )


async def process_previously_seen_rechunk_batch(
    community_server_id: UUID,
    batch_size: int,
    db_url: str,
) -> None:
    """
    Background task to process previously seen message re-chunking.

    This function:
    1. Queries PreviouslySeenMessage records for the specified community
    2. For each message, clears existing PreviouslySeenChunk entries
    3. Re-chunks and embeds the content using ChunkEmbeddingService

    Note: PreviouslySeenMessage stores message IDs, not content. The actual
    content would need to be retrieved from the message archive. For now,
    we use the metadata if available or skip if no content is present.

    Args:
        community_server_id: UUID of the community server
        batch_size: Number of items to process in each batch
        db_url: Database connection URL
    """
    from sqlalchemy.ext.asyncio import (  # noqa: PLC0415
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    service = get_chunk_embedding_service()

    async with async_session() as db:
        offset = 0
        processed_count = 0

        while True:
            result = await db.execute(
                select(PreviouslySeenMessage)
                .where(PreviouslySeenMessage.community_server_id == community_server_id)
                .order_by(PreviouslySeenMessage.created_at)
                .offset(offset)
                .limit(batch_size)
            )
            messages = result.scalars().all()

            if not messages:
                break

            for msg in messages:
                await db.execute(
                    delete(PreviouslySeenChunk).where(
                        PreviouslySeenChunk.previously_seen_id == msg.id
                    )
                )

                content = msg.extra_metadata.get("content", "")
                if content:
                    await service.chunk_and_embed_previously_seen(
                        db=db,
                        previously_seen_id=msg.id,
                        text=content,
                        community_server_id=community_server_id,
                    )
                processed_count += 1

            await db.commit()
            offset += batch_size

            logger.info(
                "Processed previously seen rechunk batch",
                extra={
                    "community_server_id": str(community_server_id),
                    "processed_count": processed_count,
                    "batch_offset": offset,
                },
            )

    await engine.dispose()

    logger.info(
        "Completed previously seen message rechunking",
        extra={
            "community_server_id": str(community_server_id),
            "total_processed": processed_count,
        },
    )


@router.post(
    "/fact-check/rechunk",
    summary="Re-chunk and re-embed fact check items",
    description="Initiates a background task to re-chunk and re-embed all fact check items. "
    "Useful for updating embeddings after model changes or migration to chunk-based embeddings. "
    "Requires authentication via API key or JWT token.",
)
async def rechunk_fact_check_items(
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    community_server_id: UUID = Query(..., description="Community server ID for LLM credentials"),
    batch_size: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch (1-1000)",
    ),
) -> dict:
    """
    Re-chunk and re-embed all fact check items.

    This endpoint initiates a background task that:
    1. Queries all FactCheckItem records
    2. Clears existing FactCheckChunk entries for each item
    3. Re-chunks the content using ChunkingService
    4. Generates new embeddings via LLMService
    5. Creates new FactCheckChunk entries

    Args:
        background_tasks: FastAPI background tasks
        user: Authenticated user (via API key or JWT)
        db: Database session
        community_server_id: Community server UUID for LLM credentials
        batch_size: Number of items to process per batch (default 100, max 1000)

    Returns:
        Dict with status and total item count
    """
    result = await db.execute(select(func.count(FactCheckItem.id)))
    total_items = result.scalar_one()

    background_tasks.add_task(
        process_fact_check_rechunk_batch,
        community_server_id=community_server_id,
        batch_size=batch_size,
        db_url=settings.DATABASE_URL,
    )

    logger.info(
        "Started fact check rechunking task",
        extra={
            "user_id": str(user.id),
            "community_server_id": str(community_server_id),
            "batch_size": batch_size,
            "total_items": total_items,
        },
    )

    return {
        "status": "started",
        "total_items": total_items,
        "batch_size": batch_size,
        "message": f"Re-chunking {total_items} fact check items in batches of {batch_size}",
    }


@router.post(
    "/previously-seen/rechunk",
    summary="Re-chunk and re-embed previously seen messages",
    description="Initiates a background task to re-chunk and re-embed previously seen messages "
    "for the specified community. Useful for updating embeddings after model changes or "
    "migration to chunk-based embeddings. Requires authentication via API key or JWT token.",
)
async def rechunk_previously_seen_messages(
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    community_server_id: UUID = Query(
        ..., description="Community server ID for filtering and LLM credentials"
    ),
    batch_size: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch (1-1000)",
    ),
) -> dict:
    """
    Re-chunk and re-embed previously seen messages for a community.

    This endpoint initiates a background task that:
    1. Queries PreviouslySeenMessage records for the specified community
    2. Clears existing PreviouslySeenChunk entries for each message
    3. Re-chunks the content (from metadata) using ChunkingService
    4. Generates new embeddings via LLMService
    5. Creates new PreviouslySeenChunk entries

    Args:
        background_tasks: FastAPI background tasks
        user: Authenticated user (via API key or JWT)
        db: Database session
        community_server_id: Community server UUID for filtering and LLM credentials
        batch_size: Number of items to process per batch (default 100, max 1000)

    Returns:
        Dict with status and total item count
    """
    result = await db.execute(
        select(func.count(PreviouslySeenMessage.id)).where(
            PreviouslySeenMessage.community_server_id == community_server_id
        )
    )
    total_items = result.scalar_one()

    background_tasks.add_task(
        process_previously_seen_rechunk_batch,
        community_server_id=community_server_id,
        batch_size=batch_size,
        db_url=settings.DATABASE_URL,
    )

    logger.info(
        "Started previously seen message rechunking task",
        extra={
            "user_id": str(user.id),
            "community_server_id": str(community_server_id),
            "batch_size": batch_size,
            "total_items": total_items,
        },
    )

    return {
        "status": "started",
        "total_items": total_items,
        "batch_size": batch_size,
        "message": f"Re-chunking {total_items} previously seen messages in batches of {batch_size}",
    }
