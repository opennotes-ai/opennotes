"""Service for generating embeddings and performing similarity searches."""

import hashlib
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.fact_checking.embedding_schemas import FactCheckMatch, SimilaritySearchResponse
from src.fact_checking.previously_seen_schemas import PreviouslySeenMessageMatch
from src.fact_checking.repository import RRF_K_CONSTANT, hybrid_search_with_chunks
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)

# =============================================================================
# Hybrid Search Thresholds and RRF Score Scaling Documentation
# =============================================================================
#
# OVERVIEW
# --------
# Hybrid search uses TWO separate thresholds for quality filtering:
#
# 1. similarity_threshold (SQL-level, pre-RRF):
#    - Filters semantic search results by cosine similarity BEFORE RRF fusion
#    - Ensures only semantically relevant results enter the ranking
#    - Prevents poor-quality results from getting high RRF scores just by
#      being "least bad" in the corpus
#    - Default: settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD (0.6)
#
# 2. rrf_score_threshold (post-RRF):
#    - Filters scaled RRF scores AFTER fusion
#    - Controls the minimum combined ranking quality
#    - Default: 0.1 (permissive, filters only very poor matches)
#
# RRF SCORE CALCULATION
# ---------------------
# For each search method (semantic/keyword), RRF score = 1/(k + rank)
# where k = RRF_K_CONSTANT (60, the de facto standard).
#
# For hybrid search, we sum scores from both methods:
#   total_rrf = 1/(k + semantic_rank) + 1/(k + keyword_rank)  # noqa: ERA001
#
# If a result appears in only one ranking (semantic OR keyword), the other
# term contributes 0.
#
# EXPECTED RRF SCORE RANGES
# -------------------------
# Single-source results (appears in semantic OR keyword only):
#   - Rank 1:  1/61 ≈ 0.0164
#   - Rank 5:  1/65 ≈ 0.0154
#   - Rank 10: 1/70 ≈ 0.0143
#   - Rank 20: 1/80 = 0.0125
#
# Dual-source results (appears in BOTH rankings):
#   - Both rank 1:  2/61 ≈ 0.0328 (maximum possible)
#   - Both rank 10: 2/70 ≈ 0.0286
#   - Both rank 20: 2/80 = 0.0250
#
# WHY SCALE FACTOR = 15.0?
# ------------------------
# We scale by 15.0 to map RRF scores to a 0.0-1.0 range:
#
#   scaled_score = min(rrf_score * 15.0, 1.0)  # noqa: ERA001
#
# Approximate mapping (RRF Rank → Raw RRF Score → Scaled Score):
#
#   Single-source results:
#   | Rank |  RRF Score | Scaled |
#   |------|------------|--------|
#   |    1 |    0.0164  |  0.246 |
#   |    5 |    0.0154  |  0.231 |
#   |   10 |    0.0143  |  0.214 |
#   |   20 |    0.0125  |  0.187 |
#
#   Dual-source results (same rank in both):
#   | Rank |  RRF Score | Scaled |
#   |------|------------|--------|
#   |    1 |    0.0328  |  0.492 |
#   |    5 |    0.0308  |  0.462 |
#   |   10 |    0.0286  |  0.429 |
#   |   20 |    0.0250  |  0.375 |
#
# With 15.0, top dual-source results map to ~0.5, and top single-source
# results map to ~0.25. Recommended rrf_score_threshold values:
#   - >= 0.4: Only top dual-source matches (very strict)
#   - >= 0.2: Top results from either method
#   - >= 0.1: Broader results including lower ranks (default)
#
# ⚠️  IMPORTANT WARNING
# ---------------------
# These scaled RRF scores are NOT cosine similarity scores! They are derived
# from ranking positions, not vector distances. A scaled score of 0.3 does
# NOT mean "30% similar" - it indicates relative ranking position in the
# combined FTS + vector search results.
#
# The similarity_threshold parameter IS true cosine similarity (0.0-1.0).
#
# For direct vector distance searches without RRF, use search_previously_seen()
# which performs pure cosine similarity calculations.
#
# =============================================================================
RRF_TO_SIMILARITY_SCALE_FACTOR = 15.0

# Re-export RRF_K_CONSTANT for documentation purposes and to avoid unused import warnings.
# The actual value is used in repository.py SQL; we import it here for documentation coherence.
__all__ = ["RRF_K_CONSTANT", "RRF_TO_SIMILARITY_SCALE_FACTOR", "EmbeddingService"]
_RRF_K = RRF_K_CONSTANT  # Reference to suppress F401; value is 60


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
        rrf_score_threshold: float = 0.1,
        limit: int = 5,
    ) -> SimilaritySearchResponse:
        """
        Search for similar fact-check items using hybrid search (FTS + vector similarity).

        Uses Reciprocal Rank Fusion (RRF) to combine full-text search and
        vector similarity for improved retrieval quality.

        Note on dataset_tags filtering:
            Dataset tags filtering is applied at the SQL level via the hybrid_search
            repository function. This ensures efficient filtering and guarantees
            that up to `limit` results matching the tags are returned.

        Note on thresholds:
            - similarity_threshold: Applied at SQL level to filter semantic search
              results by cosine similarity before RRF fusion.
            - rrf_score_threshold: Applied after RRF fusion to filter the scaled
              RRF scores (0.0-1.0 range). Default 0.1 filters out poor matches
              while being permissive enough for reasonable results.

        Args:
            db: Database session
            query_text: Query text to search for
            community_server_id: Community server (guild) ID
            dataset_tags: Dataset tags to filter by (e.g., ['snopes'])
            similarity_threshold: Minimum cosine similarity (0.0-1.0) for semantic
                search pre-filtering. Defaults to SIMILARITY_SEARCH_DEFAULT_THRESHOLD.
            rrf_score_threshold: Minimum scaled RRF score (0.0-1.0) for post-fusion
                filtering. Default 0.1 filters weak matches while remaining permissive.
            limit: Maximum number of results

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
                "similarity_threshold": threshold,
                "rrf_score_threshold": rrf_score_threshold,
                "limit": limit,
            },
        )

        query_embedding = await self.generate_embedding(db, query_text, community_server_id)

        hybrid_results = await hybrid_search_with_chunks(
            session=db,
            query_text=query_text,
            query_embedding=query_embedding,
            limit=limit,
            dataset_tags=dataset_tags if dataset_tags else None,
            semantic_similarity_threshold=threshold,
        )

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
            for result in hybrid_results
        ]

        matches = [m for m in matches if m.similarity_score >= rrf_score_threshold]

        matches = matches[:limit]

        logger.info(
            "Hybrid similarity search completed",
            extra={
                "text_length": len(query_text),
                "community_server_id": community_server_id,
                "dataset_tags": dataset_tags,
                "similarity_threshold": threshold,
                "rrf_score_threshold": rrf_score_threshold,
                "matches_found": len(matches),
                "top_score": matches[0].similarity_score if matches else None,
                "hybrid_search_count": len(hybrid_results),
            },
        )

        return SimilaritySearchResponse(
            matches=matches,
            query_text=query_text,
            dataset_tags=dataset_tags,
            similarity_threshold=threshold,
            rrf_score_threshold=rrf_score_threshold,
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
