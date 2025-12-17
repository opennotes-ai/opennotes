"""Service for generating embeddings and performing similarity searches."""

import hashlib
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.fact_checking.embedding_schemas import FactCheckMatch, SimilaritySearchResponse
from src.fact_checking.previously_seen_schemas import PreviouslySeenMessageMatch
from src.fact_checking.repository import hybrid_search
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)

# Scale factor to convert RRF scores to similarity-like scores (0.0-1.0 range).
#
# RRF (Reciprocal Rank Fusion) scores are calculated as 1/(k+rank) where k=60.
# For top 20 results: rank 1 gives ~0.0164, rank 20 gives ~0.0125.
# Expected range is approximately 0.007 to 0.067 for reasonable result sets.
#
# We scale by 15.0 to convert to a 0.0-1.0 range for backward compatibility with
# the similarity_threshold parameter used by the API. This is an approximation
# since RRF scores don't map linearly to cosine similarity, but provides a
# reasonable mapping for threshold filtering.
RRF_TO_SIMILARITY_SCALE_FACTOR = 15.0


class EmbeddingService:
    """
    Service for generating OpenAI embeddings and performing similarity searches.

    Uses LLMService for credential management and provider abstraction.
    """

    def __init__(self, llm_service: LLMService) -> None:
        """
        Initialize embedding service.

        Args:
            llm_service: LLM service for generating embeddings
        """
        self.llm_service = llm_service
        self.embedding_cache: TTLCache[str, list[float]] = TTLCache(
            maxsize=10000, ttl=settings.EMBEDDING_CACHE_TTL_SECONDS
        )

    async def generate_embedding(
        self, db: AsyncSession, text: str, community_server_id: str
    ) -> list[float]:
        """
        Generate OpenAI embedding for text using community-server API key.

        Automatically retries on errors with exponential backoff.

        Args:
            db: Database session
            text: Text to embed
            community_server_id: Community server (guild) ID

        Returns:
            Embedding vector (1536 dimensions)

        Raises:
            ValueError: If no OpenAI configuration found for community server
            Exception: If API call fails after retries
        """
        cache_key = self._get_cache_key(text)
        if cache_key in self.embedding_cache:
            logger.debug(
                "Embedding cache hit", extra={"text_length": len(text), "cache_key": cache_key[:16]}
            )
            return self.embedding_cache[cache_key]  # type: ignore[no-any-return]

        # Convert guild ID string to UUID for LLMService
        # Get CommunityServer UUID from platform_id (Discord guild ID)
        result = await db.execute(
            select(CommunityServer.id).where(CommunityServer.platform_id == community_server_id)
        )
        community_server_uuid = result.scalar_one_or_none()

        if not community_server_uuid:
            raise ValueError(f"Community server not found for platform_id: {community_server_id}")

        # Generate embedding via LLMService (handles retries internally)
        # LLMService returns tuple of (embedding, provider, model)
        embedding, _, _ = await self.llm_service.generate_embedding(db, text, community_server_uuid)

        self.embedding_cache[cache_key] = embedding

        return embedding

    async def similarity_search(
        self,
        db: AsyncSession,
        query_text: str,
        community_server_id: str,
        dataset_tags: list[str],
        similarity_threshold: float | None = None,
        limit: int = 5,
    ) -> SimilaritySearchResponse:
        """
        Search for similar fact-check items using hybrid search (FTS + vector similarity).

        Uses Reciprocal Rank Fusion (RRF) to combine full-text search and
        vector similarity for improved retrieval quality.

        Note on dataset_tags filtering:
            Dataset tags filtering is applied post-search (after RRF ranking) rather
            than at the database level. This means the method may return fewer results
            than the requested limit if many top-ranked results don't match the tags.
            To compensate, we fetch 3x the limit from the database, but this is not
            guaranteed to always yield `limit` results.

        Note on similarity_threshold:
            After converting RRF scores to similarity-like scores (via scaling),
            results below the threshold are filtered out. This filtering happens
            after dataset_tags filtering but before truncating to the limit.

        Args:
            db: Database session
            query_text: Query text to search for
            community_server_id: Community server (guild) ID
            dataset_tags: Dataset tags to filter by (e.g., ['snopes'])
            similarity_threshold: Minimum similarity score (0.0-1.0) - results with
                scaled RRF scores below this are excluded
            limit: Maximum number of results (may return fewer, see notes above)

        Returns:
            Similarity search response with matching items

        Raises:
            ValueError: If embedding generation fails
        """
        threshold = similarity_threshold or settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD

        logger.debug(
            "Starting hybrid similarity search",
            extra={
                "text_length": len(query_text),
                "community_server_id": community_server_id,
                "dataset_tags": dataset_tags,
                "threshold": threshold,
                "limit": limit,
            },
        )

        query_embedding = await self.generate_embedding(db, query_text, community_server_id)

        hybrid_results = await hybrid_search(
            session=db,
            query_text=query_text,
            query_embedding=query_embedding,
            limit=limit * 3,
        )

        filtered_results = [
            result
            for result in hybrid_results
            if any(tag in result.item.dataset_tags for tag in dataset_tags)
        ]

        matches = [
            FactCheckMatch(
                id=result.item.id,
                dataset_name=result.item.dataset_name,
                dataset_tags=result.item.dataset_tags,
                title=result.item.title,
                content=result.item.content,
                summary=result.item.summary,
                rating=result.item.rating,
                source_url=result.item.source_url,
                published_date=result.item.published_date,
                author=result.item.author,
                embedding_provider=result.item.embedding_provider,
                embedding_model=result.item.embedding_model,
                similarity_score=min(result.rrf_score * RRF_TO_SIMILARITY_SCALE_FACTOR, 1.0),
            )
            for result in filtered_results
        ]

        matches = [m for m in matches if m.similarity_score >= threshold]

        matches = matches[:limit]

        logger.info(
            "Hybrid similarity search completed",
            extra={
                "text_length": len(query_text),
                "community_server_id": community_server_id,
                "dataset_tags": dataset_tags,
                "threshold": threshold,
                "matches_found": len(matches),
                "top_score": matches[0].similarity_score if matches else None,
                "pre_filter_count": len(hybrid_results),
            },
        )

        return SimilaritySearchResponse(
            matches=matches,
            query_text=query_text,
            dataset_tags=dataset_tags,
            similarity_threshold=threshold,
            total_matches=len(matches),
        )

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key from text content.

        Args:
            text: Text to hash

        Returns:
            SHA256 hash of text
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def search_previously_seen(
        self,
        db: AsyncSession,
        embedding: list[float],
        community_server_id: UUID,
        similarity_threshold: float,
        limit: int = 5,
    ) -> list[PreviouslySeenMessageMatch]:
        """
        Search for previously seen messages using pgvector cosine similarity.

        Args:
            db: Database session
            embedding: Query embedding vector (1536 dimensions)
            community_server_id: Community server UUID
            similarity_threshold: Minimum similarity score (0.0-1.0)
            limit: Maximum number of results

        Returns:
            List of matching previously seen messages with similarity scores
        """
        logger.debug(
            "Starting previously seen search",
            extra={
                "community_server_id": str(community_server_id),
                "threshold": similarity_threshold,
                "limit": limit,
            },
        )

        max_distance = 1.0 - similarity_threshold

        query_embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        query = text("""
            SELECT
                id,
                community_server_id,
                original_message_id,
                published_note_id,
                embedding_provider,
                embedding_model,
                metadata,
                created_at,
                1 - (embedding <=> CAST(:embedding AS vector)) AS similarity_score
            FROM previously_seen_messages
            WHERE
                community_server_id = :community_server_id
                AND embedding IS NOT NULL
                AND (embedding <=> CAST(:embedding AS vector)) <= :max_dist
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :result_limit
        """)

        result = await db.execute(
            query,
            {
                "embedding": query_embedding_str,
                "community_server_id": community_server_id,
                "max_dist": max_distance,
                "result_limit": limit,
            },
        )

        rows = result.fetchall()

        matches = [
            PreviouslySeenMessageMatch(
                id=row[0],
                community_server_id=row[1],
                original_message_id=row[2],
                published_note_id=row[3],
                embedding_provider=row[4],
                embedding_model=row[5],
                extra_metadata=row[6] or {},
                created_at=row[7],
                similarity_score=row[8],
            )
            for row in rows
        ]

        logger.info(
            "Previously seen search completed",
            extra={
                "community_server_id": str(community_server_id),
                "threshold": similarity_threshold,
                "matches_found": len(matches),
                "top_score": matches[0].similarity_score if matches else None,
            },
        )

        return matches

    def invalidate_cache(self, community_server_id: str | None = None) -> None:
        """
        Invalidate cached embeddings.

        Args:
            community_server_id: Specific community server ID (for logging only),
                                or None to clear all caches
        """
        self.embedding_cache.clear()
        logger.info(
            "Embedding cache invalidated",
            extra={"community_server_id": community_server_id},
        )
