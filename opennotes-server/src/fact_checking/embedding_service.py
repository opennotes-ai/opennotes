"""Service for generating embeddings and performing similarity searches."""

import hashlib
from uuid import UUID

from cachetools import TTLCache
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.redis_client import redis_client
from src.config import settings
from src.fact_checking.embedding_schemas import FactCheckMatch, SimilaritySearchResponse
from src.fact_checking.previously_seen_schemas import PreviouslySeenMessageMatch
from src.fact_checking.repository import DEFAULT_ALPHA, FUSION_K_CONSTANT, hybrid_search_with_chunks
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.search.search_analytics import hash_query, log_search_results

logger = get_logger(__name__)
_tracer = trace.get_tracer(__name__)

# =============================================================================
# Hybrid Search Thresholds and Convex Combination Score Documentation
# =============================================================================
#
# OVERVIEW
# --------
# Hybrid search uses TWO separate thresholds for quality filtering:
#
# 1. similarity_threshold (SQL-level, pre-fusion):
#    - Filters semantic search results by cosine similarity BEFORE CC fusion
#    - Ensures only semantically relevant results enter the ranking
#    - Prevents poor-quality results from getting high CC scores just by
#      being "least bad" in the corpus
#    - Default: settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD (0.6)
#
# 2. score_threshold (post-fusion):
#    - Filters CC scores AFTER fusion
#    - Controls the minimum combined ranking quality
#    - Default: 0.1 (permissive, filters only very poor matches)
#
# CONVEX COMBINATION (CC) SCORE CALCULATION
# -----------------------------------------
# The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
#
# Where:
# - semantic_similarity = 1 - cosine_distance (already in 0-1 range)
# - keyword_norm = min-max normalized ts_rank_cd within result set (0-1)
# - alpha ∈ [0, 1] controls the balance (default 0.7, semantic-weighted)
#
# CC SCORE RANGES
# ---------------
# CC scores are ALREADY in the 0.0-1.0 range (no scaling needed):
#
# Single-source results (appears in semantic OR keyword only):
#   - High semantic only: alpha * similarity (e.g., 0.7 * 0.9 = 0.63)
#   - High keyword only: (1-alpha) * 1.0 (e.g., 0.3 * 1.0 = 0.30)
#
# Dual-source results (appears in BOTH rankings):
#   - High both: alpha * 0.9 + (1-alpha) * 1.0 = 0.7 * 0.9 + 0.3 = 0.93 (maximum)
#   - Medium both: alpha * 0.7 + (1-alpha) * 0.8 = 0.7 * 0.7 + 0.3 * 0.8 = 0.73
#
# Recommended score_threshold values:
#   - >= 0.5: Only strong dual-source matches (very strict)
#   - >= 0.3: Good results from either method
#   - >= 0.1: Broader results including lower ranks (default)
#
# ✅ KEY BENEFIT: CC PRESERVES SCORE MAGNITUDE
# --------------------------------------------
# Unlike RRF which discards score magnitude (only uses ranks), CC preserves
# the actual similarity/relevance values. This enables:
# - Better relevance discrimination between similar-ranked results
# - More meaningful threshold-based filtering
# - Score values that represent actual relevance, not just relative ranking
#
# Reference: ACM 2023 https://dl.acm.org/doi/10.1145/3596512
# Research shows CC outperforms RRF in both in-domain and out-of-domain settings.
#
# =============================================================================
# Scale factor for CC scores (CC scores are already 0-1, no scaling needed)
CC_SCORE_SCALE_FACTOR = 1.0

__all__ = ["CC_SCORE_SCALE_FACTOR", "FUSION_K_CONSTANT", "EmbeddingService"]
_FUSION_K = FUSION_K_CONSTANT


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
        with _tracer.start_as_current_span("embedding.generate") as span:
            span.set_attribute("embedding.text_length", len(text))
            span.set_attribute("embedding.community_server_id", community_server_id)

            try:
                cache_key = self._get_cache_key(text)
                if cache_key in self.embedding_cache:
                    span.set_attribute("embedding.cache_hit", True)
                    logger.debug(
                        "Embedding cache hit",
                        extra={"text_length": len(text), "cache_key": cache_key[:16]},
                    )
                    return self.embedding_cache[cache_key]  # type: ignore[no-any-return]

                span.set_attribute("embedding.cache_hit", False)

                # Convert guild ID string to UUID for LLMService
                # Get CommunityServer UUID from platform_community_server_id (Discord guild ID)
                result = await db.execute(
                    select(CommunityServer.id).where(
                        CommunityServer.platform_community_server_id == community_server_id
                    )
                )
                community_server_uuid = result.scalar_one_or_none()

                if not community_server_uuid:
                    raise ValueError(
                        f"Community server not found for platform_community_server_id: {community_server_id}"
                    )

                # Generate embedding via LLMService (handles retries internally)
                # LLMService returns tuple of (embedding, provider, model)
                embedding, _, _ = await self.llm_service.generate_embedding(
                    db, text, community_server_uuid
                )

                self.embedding_cache[cache_key] = embedding

                return embedding
            except Exception as e:
                span.record_exception(e)
                span.set_status(StatusCode.ERROR, str(e))
                raise

    async def similarity_search(
        self,
        db: AsyncSession,
        query_text: str,
        community_server_id: str,
        dataset_tags: list[str],
        similarity_threshold: float | None = None,
        score_threshold: float = 0.1,
        limit: int = 5,
    ) -> SimilaritySearchResponse:
        """
        Search for similar fact-check items using hybrid search (FTS + vector similarity).

        Uses hybrid search to combine full-text search and
        vector similarity for improved retrieval quality.

        Note on dataset_tags filtering:
            Dataset tags filtering is applied at the SQL level via the hybrid_search
            repository function. This ensures efficient filtering and guarantees
            that up to `limit` results matching the tags are returned.

        Note on thresholds:
            - similarity_threshold: Applied at SQL level to filter semantic search
              results by cosine similarity before CC fusion.
            - score_threshold: Applied after CC fusion to filter the
              CC scores (0.0-1.0 range). Default 0.1 filters out poor matches
              while being permissive enough for reasonable results.

        Args:
            db: Database session
            query_text: Query text to search for
            community_server_id: Community server (guild) ID
            dataset_tags: Dataset tags to filter by (e.g., ['snopes'])
            similarity_threshold: Minimum cosine similarity (0.0-1.0) for semantic
                search pre-filtering. Defaults to SIMILARITY_SEARCH_DEFAULT_THRESHOLD.
            score_threshold: Minimum CC score (0.0-1.0) for post-fusion
                filtering. Default 0.1 filters weak matches while remaining permissive.
            limit: Maximum number of results

        Returns:
            Similarity search response with matching items

        Raises:
            ValueError: If embedding generation fails
        """
        with _tracer.start_as_current_span("embedding.similarity_search") as span:
            threshold = similarity_threshold or settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD

            span.set_attribute("search.query_text_length", len(query_text))
            span.set_attribute("search.community_server_id", community_server_id)
            span.set_attribute(
                "search.dataset_tags", ",".join(dataset_tags) if dataset_tags else ""
            )
            span.set_attribute("search.similarity_threshold", threshold)
            span.set_attribute("search.score_threshold", score_threshold)
            span.set_attribute("search.limit", limit)

            try:
                logger.debug(
                    "Starting hybrid similarity search",
                    extra={
                        "text_length": len(query_text),
                        "community_server_id": community_server_id,
                        "dataset_tags": dataset_tags,
                        "similarity_threshold": threshold,
                        "score_threshold": score_threshold,
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
                        similarity_score=min(result.cc_score * CC_SCORE_SCALE_FACTOR, 1.0),
                        cosine_similarity=result.semantic_score,
                    )
                    for result in hybrid_results
                ]

                matches = [m for m in matches if m.similarity_score >= score_threshold]

                matches = matches[:limit]

                span.set_attribute("search.result_count", len(matches))
                span.set_attribute("search.hybrid_search_count", len(hybrid_results))
                if matches:
                    span.set_attribute("search.top_score", matches[0].similarity_score)

                logger.info(
                    "Hybrid similarity search completed",
                    extra={
                        "text_length": len(query_text),
                        "community_server_id": community_server_id,
                        "dataset_tags": dataset_tags,
                        "similarity_threshold": threshold,
                        "score_threshold": score_threshold,
                        "matches_found": len(matches),
                        "top_score": matches[0].similarity_score if matches else None,
                        "cosine_similarity": matches[0].cosine_similarity if matches else None,
                        "hybrid_search_count": len(hybrid_results),
                        "alpha": DEFAULT_ALPHA,
                    },
                )

                await log_search_results(
                    redis=redis_client,
                    query_hash=hash_query(query_text),
                    alpha=DEFAULT_ALPHA,
                    dataset_tags=dataset_tags,
                    results=hybrid_results,
                )

                return SimilaritySearchResponse(
                    matches=matches,
                    query_text=query_text,
                    dataset_tags=dataset_tags,
                    similarity_threshold=threshold,
                    score_threshold=score_threshold,
                    total_matches=len(matches),
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(StatusCode.ERROR, str(e))
                raise

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
