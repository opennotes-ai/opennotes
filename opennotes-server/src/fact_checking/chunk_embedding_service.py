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
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.fact_checking.chunk_models import (
    ChunkEmbedding,
    FactCheckChunk,
    PreviouslySeenChunk,
    compute_chunk_text_hash,
)
from src.fact_checking.chunking_service import ChunkingService
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)

# Minimum number of document appearances for a chunk to be marked as "common".
# A chunk with total_count > IS_COMMON_THRESHOLD is flagged is_common=True.
#
# Tradeoff:
# - Lower threshold (e.g., 1): Aggressively marks chunks as common. This reduces
#   weight for chunks appearing in just 2 documents, which may prematurely
#   down-weight legitimately important shared content.
# - Higher threshold (e.g., 4): Only marks chunks appearing in 5+ documents as
#   common. More conservative, but may fail to down-weight boilerplate text
#   that appears in fewer documents.
#
# Default of 2 means chunks appearing in 3+ documents are marked common.
# Adjust based on corpus characteristics and search quality observations.
IS_COMMON_THRESHOLD = 2


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

    async def get_or_create_chunks_batch(
        self,
        db: AsyncSession,
        chunk_texts: list[str],
        community_server_id: UUID | None = None,
    ) -> list[tuple[ChunkEmbedding, bool]]:
        """
        Get existing chunks or create new ones with embeddings in batch.

        Optimizes for performance by:
        1. Batch querying all existing chunks in a single DB query
        2. Batch generating embeddings for missing chunks in a single API call
        3. Batch inserting new chunks with ON CONFLICT DO NOTHING

        This reduces API calls from O(N) to O(1) and DB round trips significantly.

        Args:
            db: Database session
            chunk_texts: List of text contents to get or create chunks for
            community_server_id: Community server UUID for LLM credentials,
                or None for global fallback

        Returns:
            List of (ChunkEmbedding, is_created) tuples in the same order as input texts.
            is_created is True if a new chunk was created, False if existing was found.
        """
        if not chunk_texts:
            return []

        unique_texts = list(dict.fromkeys(chunk_texts))
        text_to_hash = {text: compute_chunk_text_hash(text) for text in unique_texts}
        unique_hashes = list(text_to_hash.values())

        result = await db.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_text_hash.in_(unique_hashes))
        )
        existing_by_hash = {chunk.chunk_text_hash: chunk for chunk in result.scalars().all()}

        missing_texts = [t for t in unique_texts if text_to_hash[t] not in existing_by_hash]

        new_by_hash: dict[str, ChunkEmbedding] = {}
        if missing_texts:
            embeddings = await self.llm_service.generate_embeddings_batch(
                db, missing_texts, community_server_id
            )

            now = datetime.now(UTC)

            for text, (embedding, provider, model) in zip(missing_texts, embeddings, strict=True):
                chunk_hash = text_to_hash[text]
                stmt = (
                    pg_insert(ChunkEmbedding)
                    .values(
                        chunk_text=text,
                        chunk_text_hash=chunk_hash,
                        embedding=embedding,
                        embedding_provider=provider,
                        embedding_model=model,
                        is_common=False,
                        created_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=["chunk_text_hash"])
                )
                await db.execute(stmt)

            await db.flush()

            missing_hashes = [text_to_hash[t] for t in missing_texts]
            result = await db.execute(
                select(ChunkEmbedding).where(ChunkEmbedding.chunk_text_hash.in_(missing_hashes))
            )
            for chunk in result.scalars().all():
                new_by_hash[chunk.chunk_text_hash] = chunk

        text_to_chunk: dict[str, tuple[ChunkEmbedding, bool]] = {}
        for text in unique_texts:
            chunk_hash = text_to_hash[text]
            if chunk_hash in existing_by_hash:
                text_to_chunk[text] = (existing_by_hash[chunk_hash], False)
            else:
                text_to_chunk[text] = (new_by_hash[chunk_hash], True)

        results = [text_to_chunk[text] for text in chunk_texts]

        new_count = sum(1 for _, is_created in text_to_chunk.values() if is_created)
        logger.info(
            "Batch get_or_create chunks completed",
            extra={
                "total_texts": len(chunk_texts),
                "unique_texts": len(unique_texts),
                "existing_count": len(existing_by_hash),
                "new_count": new_count,
            },
        )

        return results

    async def get_or_create_chunk(
        self,
        db: AsyncSession,
        chunk_text: str,
        community_server_id: UUID | None = None,
    ) -> tuple[ChunkEmbedding, bool]:
        """
        Get an existing chunk by text or create a new one with embedding.

        Performs exact text match lookup before generating embeddings.
        If chunk exists, returns it without generating new embedding.
        If chunk is new, generates embedding via LLMService and creates record.

        Uses INSERT ON CONFLICT DO NOTHING to handle race conditions where
        concurrent requests try to create the same chunk simultaneously.

        Note: chunk_index is not stored here because chunks are deduplicated
        by text. The same text can appear at different positions in different
        documents, so chunk_index is stored in the join tables instead.

        Args:
            db: Database session
            chunk_text: The text content of the chunk
            community_server_id: Community server UUID for LLM credentials,
                or None for global fallback

        Returns:
            Tuple of (ChunkEmbedding, is_created) where is_created is True
            if a new chunk was created, False if existing was found
        """
        chunk_hash = compute_chunk_text_hash(chunk_text)

        result = await db.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_text_hash == chunk_hash)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.debug(
                "Found existing chunk",
                extra={
                    "chunk_id": str(existing.id),
                    "text_length": len(chunk_text),
                    "chunk_hash": chunk_hash,
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
                chunk_text_hash=chunk_hash,
                embedding=embedding,
                embedding_provider=provider,
                embedding_model=model,
                is_common=False,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["chunk_text_hash"])
        )

        insert_result = await db.execute(stmt)
        await db.flush()

        result = await db.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_text_hash == chunk_hash)
        )
        chunk = result.scalar_one()

        cursor_result = cast(CursorResult[Any], insert_result)
        is_created = cursor_result.rowcount > 0

        if is_created:
            logger.info(
                "Created new chunk embedding",
                extra={
                    "chunk_id": str(chunk.id),
                    "text_length": len(chunk_text),
                    "chunk_hash": chunk_hash,
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
                    "chunk_hash": chunk_hash,
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
        is_common = total_count > IS_COMMON_THRESHOLD

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

    async def batch_update_is_common_flags(
        self,
        db: AsyncSession,
        chunk_ids: list[UUID],
    ) -> dict[UUID, bool]:
        """
        Batch update is_common flags for multiple chunks.

        This is more efficient than calling update_is_common_flag individually
        for each chunk, reducing queries from O(3N) to O(3) constant.

        Deadlock Prevention:
        Uses SELECT FOR UPDATE with ORDER BY id to acquire row locks in a
        consistent order across all concurrent workers. This prevents deadlocks
        where worker A locks row 1 then tries to lock row 2, while worker B
        locks row 2 then tries to lock row 1.

        Args:
            db: Database session
            chunk_ids: List of chunk UUIDs to update

        Returns:
            Dictionary mapping chunk_id to its new is_common value
        """
        if not chunk_ids:
            return {}

        unique_ids = sorted(set(chunk_ids))

        await db.execute(
            select(ChunkEmbedding.id)
            .where(ChunkEmbedding.id.in_(unique_ids))
            .order_by(ChunkEmbedding.id)
            .with_for_update()
        )

        fact_check_counts = (
            select(
                FactCheckChunk.chunk_id.label("chunk_id"),
                func.count().label("cnt"),
            )
            .where(FactCheckChunk.chunk_id.in_(unique_ids))
            .group_by(FactCheckChunk.chunk_id)
        )

        previously_seen_counts = (
            select(
                PreviouslySeenChunk.chunk_id.label("chunk_id"),
                func.count().label("cnt"),
            )
            .where(PreviouslySeenChunk.chunk_id.in_(unique_ids))
            .group_by(PreviouslySeenChunk.chunk_id)
        )

        combined = union_all(fact_check_counts, previously_seen_counts).subquery()

        totals_query = select(
            combined.c.chunk_id,
            func.sum(combined.c.cnt).label("total"),
        ).group_by(combined.c.chunk_id)

        result = await db.execute(totals_query)
        counts = {row.chunk_id: row.total for row in result.all()}

        common_ids = [cid for cid in unique_ids if counts.get(cid, 0) > IS_COMMON_THRESHOLD]
        not_common_ids = [cid for cid in unique_ids if counts.get(cid, 0) <= IS_COMMON_THRESHOLD]

        if common_ids:
            await db.execute(
                update(ChunkEmbedding)
                .where(ChunkEmbedding.id.in_(common_ids))
                .values(is_common=True)
            )

        if not_common_ids:
            await db.execute(
                update(ChunkEmbedding)
                .where(ChunkEmbedding.id.in_(not_common_ids))
                .values(is_common=False)
            )

        result_map = {cid: cid in common_ids for cid in unique_ids}

        logger.debug(
            "Batch updated is_common flags",
            extra={
                "chunk_count": len(unique_ids),
                "common_count": len(common_ids),
                "not_common_count": len(not_common_ids),
            },
        )

        return result_map

    async def chunk_and_embed_fact_check(
        self,
        db: AsyncSession,
        fact_check_id: UUID,
        text: str,
        community_server_id: UUID | None = None,
        chunk_texts: list[str] | None = None,
    ) -> list[ChunkEmbedding]:
        """
        Chunk text and create/reuse embeddings for a FactCheckItem.

        This operation is idempotent: calling it multiple times for the same
        fact_check_id will produce the same result. Uses upsert (INSERT ON
        CONFLICT) to create or update FactCheckChunk entries, then removes
        any stale entries that are no longer part of the current chunking.

        Splits text into semantic chunks, creates or retrieves ChunkEmbedding
        records for each, and creates FactCheckChunk join entries.

        Uses batch embedding for optimal performance when processing multiple chunks.

        Args:
            db: Database session
            fact_check_id: UUID of the FactCheckItem
            text: Text content to chunk and embed
            community_server_id: Community server UUID for LLM credentials,
                or None for global fallback
            chunk_texts: Pre-computed chunk texts. When provided, skips the
                chunking_service.chunk_text() call. Callers that need to
                control lock scope around NeuralChunker can chunk externally
                and pass the results here.

        Returns:
            List of ChunkEmbedding records (new or existing)
        """
        if chunk_texts is None:
            chunk_texts = self.chunking_service.chunk_text(text)

        chunk_results = await self.get_or_create_chunks_batch(
            db=db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        chunks: list[ChunkEmbedding] = []
        chunk_ids: list[UUID] = []
        join_entries: list[dict[str, Any]] = []
        seen_chunk_ids: set[UUID] = set()

        for idx, (chunk, _) in enumerate(chunk_results):
            chunks.append(chunk)
            chunk_ids.append(chunk.id)
            if chunk.id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk.id)
                join_entries.append(
                    {
                        "chunk_id": chunk.id,
                        "fact_check_id": fact_check_id,
                        "chunk_index": idx,
                        "created_at": datetime.now(UTC),
                    }
                )

        # Use upsert to handle race conditions and ensure idempotency
        # If a duplicate (chunk_id, fact_check_id) exists, update the chunk_index
        if join_entries:
            stmt = pg_insert(FactCheckChunk).values(join_entries)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_fact_check_chunks_chunk_fact_check",
                set_={"chunk_index": stmt.excluded.chunk_index},
            )
            await db.execute(stmt)

        # Delete stale chunk references that are no longer part of this fact check
        # (e.g., if a fact check went from chunks A,B,C to A,B, we clean up C)
        if chunk_ids:
            await db.execute(
                delete(FactCheckChunk).where(
                    FactCheckChunk.fact_check_id == fact_check_id,
                    FactCheckChunk.chunk_id.notin_(chunk_ids),
                )
            )
        else:
            # No chunks means delete all references for this fact check
            await db.execute(
                delete(FactCheckChunk).where(FactCheckChunk.fact_check_id == fact_check_id)
            )

        await self.batch_update_is_common_flags(db, chunk_ids)

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
        community_server_id: UUID | None = None,
    ) -> list[ChunkEmbedding]:
        """
        Chunk text and create/reuse embeddings for a PreviouslySeenMessage.

        This operation is idempotent: calling it multiple times for the same
        previously_seen_id will produce the same result. Uses upsert (INSERT ON
        CONFLICT) to create or update PreviouslySeenChunk entries, then removes
        any stale entries that are no longer part of the current chunking.

        Splits text into semantic chunks, creates or retrieves ChunkEmbedding
        records for each, and creates PreviouslySeenChunk join entries.

        Uses batch embedding for optimal performance when processing multiple chunks.

        Args:
            db: Database session
            previously_seen_id: UUID of the PreviouslySeenMessage
            text: Text content to chunk and embed
            community_server_id: Community server UUID for LLM credentials,
                or None for global fallback

        Returns:
            List of ChunkEmbedding records (new or existing)
        """
        chunk_texts = self.chunking_service.chunk_text(text)

        chunk_results = await self.get_or_create_chunks_batch(
            db=db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        chunks: list[ChunkEmbedding] = []
        chunk_ids: list[UUID] = []
        join_entries: list[dict[str, Any]] = []
        seen_chunk_ids: set[UUID] = set()

        for idx, (chunk, _) in enumerate(chunk_results):
            chunks.append(chunk)
            chunk_ids.append(chunk.id)
            if chunk.id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk.id)
                join_entries.append(
                    {
                        "chunk_id": chunk.id,
                        "previously_seen_id": previously_seen_id,
                        "chunk_index": idx,
                        "created_at": datetime.now(UTC),
                    }
                )

        # Use upsert to handle race conditions and ensure idempotency
        # If a duplicate (chunk_id, previously_seen_id) exists, update the chunk_index
        if join_entries:
            stmt = pg_insert(PreviouslySeenChunk).values(join_entries)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_previously_seen_chunks_chunk_previously_seen",
                set_={"chunk_index": stmt.excluded.chunk_index},
            )
            await db.execute(stmt)

        # Delete stale chunk references that are no longer part of this message
        # (e.g., if a message went from chunks A,B,C to A,B, we clean up C)
        if chunk_ids:
            await db.execute(
                delete(PreviouslySeenChunk).where(
                    PreviouslySeenChunk.previously_seen_id == previously_seen_id,
                    PreviouslySeenChunk.chunk_id.notin_(chunk_ids),
                )
            )
        else:
            # No chunks means delete all references for this message
            await db.execute(
                delete(PreviouslySeenChunk).where(
                    PreviouslySeenChunk.previously_seen_id == previously_seen_id
                )
            )

        await self.batch_update_is_common_flags(db, chunk_ids)

        logger.info(
            "Chunked and embedded previously seen message",
            extra={
                "previously_seen_id": str(previously_seen_id),
                "text_length": len(text),
                "chunk_count": len(chunks),
            },
        )

        return chunks
