"""
Service for chunk-based content embedding with deduplication.

This module provides the ChunkEmbeddingService which handles:
- Splitting text into semantic chunks using ChunkingService
- Deduplicating chunks by exact text match
- Generating embeddings for new chunks via LLMService
- Managing join table entries for FactCheckItem and PreviouslySeenMessage
- Tracking common chunks that appear across multiple documents
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.fact_checking.chunk_models import ChunkEmbedding, FactCheckChunk, PreviouslySeenChunk
from src.fact_checking.chunking_service import ChunkingService
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)


class ChunkEmbeddingService:
    """
    Service for creating and managing chunk embeddings with deduplication.

    Chunks text using neural-based semantic segmentation, then checks if
    each chunk already exists in the database. If it exists, reuses the
    existing embedding. If not, generates a new embedding via LLMService.

    This approach:
    - Reduces embedding generation costs by reusing existing chunks
    - Enables more granular semantic search than full-document embeddings
    - Tracks common/boilerplate chunks across documents

    Attributes:
        chunking_service: Service for splitting text into semantic chunks
        llm_service: Service for generating embeddings
    """

    def __init__(
        self,
        chunking_service: ChunkingService,
        llm_service: LLMService,
    ) -> None:
        """
        Initialize the ChunkEmbeddingService.

        Args:
            chunking_service: Service for text chunking
            llm_service: Service for embedding generation
        """
        self.chunking_service = chunking_service
        self.llm_service = llm_service

    async def get_or_create_chunk(
        self,
        db: AsyncSession,
        chunk_text: str,
        community_server_id: UUID,
        chunk_index: int = 0,
    ) -> tuple[ChunkEmbedding, bool]:
        """
        Get an existing chunk by text or create a new one with embedding.

        Performs exact text match lookup before generating embeddings.
        If chunk exists, returns it without generating new embedding.
        If chunk is new, generates embedding via LLMService and creates record.

        Uses INSERT ON CONFLICT DO NOTHING to handle race conditions where
        concurrent requests try to create the same chunk simultaneously.

        Args:
            db: Database session
            chunk_text: The text content of the chunk
            community_server_id: Community server UUID for LLM credentials
            chunk_index: Position of this chunk in original document (0-indexed)

        Returns:
            Tuple of (ChunkEmbedding, is_created) where is_created is True
            if a new chunk was created, False if existing was found
        """
        result = await db.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_text == chunk_text)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.debug(
                "Found existing chunk",
                extra={
                    "chunk_id": str(existing.id),
                    "text_length": len(chunk_text),
                },
            )
            return existing, False

        embedding, provider, model = await self.llm_service.generate_embedding(
            db, chunk_text, community_server_id
        )

        now = datetime.now(UTC)

        stmt = (
            pg_insert(ChunkEmbedding)
            .values(
                chunk_text=chunk_text,
                chunk_index=chunk_index,
                embedding=embedding,
                embedding_provider=provider,
                embedding_model=model,
                is_common=False,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["chunk_text"])
        )

        insert_result = await db.execute(stmt)
        await db.flush()

        result = await db.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_text == chunk_text)
        )
        chunk = result.scalar_one()

        is_created = insert_result.rowcount > 0

        if is_created:
            logger.info(
                "Created new chunk embedding",
                extra={
                    "chunk_id": str(chunk.id),
                    "text_length": len(chunk_text),
                    "chunk_index": chunk_index,
                    "embedding_provider": provider,
                    "embedding_model": model,
                },
            )
        else:
            logger.debug(
                "Race condition resolved: using existing chunk",
                extra={
                    "chunk_id": str(chunk.id),
                    "text_length": len(chunk_text),
                },
            )

        return chunk, is_created

    async def update_is_common_flag(
        self,
        db: AsyncSession,
        chunk_id: UUID,
    ) -> bool:
        """
        Update the is_common flag based on chunk appearances in join tables.

        A chunk is considered "common" if it appears in more than one document
        across FactCheckChunk and PreviouslySeenChunk join tables combined.

        Args:
            db: Database session
            chunk_id: UUID of the chunk to update

        Returns:
            The new is_common value
        """
        fact_check_count_result = await db.execute(
            select(func.count(FactCheckChunk.id)).where(FactCheckChunk.chunk_id == chunk_id)
        )
        fact_check_count = fact_check_count_result.scalar_one()

        previously_seen_count_result = await db.execute(
            select(func.count(PreviouslySeenChunk.id)).where(
                PreviouslySeenChunk.chunk_id == chunk_id
            )
        )
        previously_seen_count = previously_seen_count_result.scalar_one()

        total_count = fact_check_count + previously_seen_count
        is_common = total_count > 1

        await db.execute(
            update(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id).values(is_common=is_common)
        )

        logger.debug(
            "Updated is_common flag",
            extra={
                "chunk_id": str(chunk_id),
                "fact_check_count": fact_check_count,
                "previously_seen_count": previously_seen_count,
                "is_common": is_common,
            },
        )

        return is_common

    async def chunk_and_embed_fact_check(
        self,
        db: AsyncSession,
        fact_check_id: UUID,
        text: str,
        community_server_id: UUID,
    ) -> list[ChunkEmbedding]:
        """
        Chunk text and create/reuse embeddings for a FactCheckItem.

        Splits text into semantic chunks, creates or retrieves ChunkEmbedding
        records for each, and creates FactCheckChunk join entries.

        Args:
            db: Database session
            fact_check_id: UUID of the FactCheckItem
            text: Text content to chunk and embed
            community_server_id: Community server UUID for LLM credentials

        Returns:
            List of ChunkEmbedding records (new or existing)
        """
        chunk_texts = self.chunking_service.chunk_text(text)

        chunks: list[ChunkEmbedding] = []

        for idx, chunk_text in enumerate(chunk_texts):
            chunk, _ = await self.get_or_create_chunk(
                db=db,
                chunk_text=chunk_text,
                community_server_id=community_server_id,
                chunk_index=idx,
            )
            chunks.append(chunk)

            join_entry = FactCheckChunk(
                chunk_id=chunk.id,
                fact_check_id=fact_check_id,
            )
            db.add(join_entry)

            await self.update_is_common_flag(db, chunk.id)

        logger.info(
            "Chunked and embedded fact check item",
            extra={
                "fact_check_id": str(fact_check_id),
                "text_length": len(text),
                "chunk_count": len(chunks),
            },
        )

        return chunks

    async def chunk_and_embed_previously_seen(
        self,
        db: AsyncSession,
        previously_seen_id: UUID,
        text: str,
        community_server_id: UUID,
    ) -> list[ChunkEmbedding]:
        """
        Chunk text and create/reuse embeddings for a PreviouslySeenMessage.

        Splits text into semantic chunks, creates or retrieves ChunkEmbedding
        records for each, and creates PreviouslySeenChunk join entries.

        Args:
            db: Database session
            previously_seen_id: UUID of the PreviouslySeenMessage
            text: Text content to chunk and embed
            community_server_id: Community server UUID for LLM credentials

        Returns:
            List of ChunkEmbedding records (new or existing)
        """
        chunk_texts = self.chunking_service.chunk_text(text)

        chunks: list[ChunkEmbedding] = []

        for idx, chunk_text in enumerate(chunk_texts):
            chunk, _ = await self.get_or_create_chunk(
                db=db,
                chunk_text=chunk_text,
                community_server_id=community_server_id,
                chunk_index=idx,
            )
            chunks.append(chunk)

            join_entry = PreviouslySeenChunk(
                chunk_id=chunk.id,
                previously_seen_id=previously_seen_id,
            )
            db.add(join_entry)

            await self.update_is_common_flag(db, chunk.id)

        logger.info(
            "Chunked and embedded previously seen message",
            extra={
                "previously_seen_id": str(previously_seen_id),
                "text_length": len(text),
                "chunk_count": len(chunks),
            },
        )

        return chunks
