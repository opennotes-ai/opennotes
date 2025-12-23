"""Repository functions for fact-checking data access.

Provides database access patterns for fact-checking features, including
hybrid search combining full-text search (FTS) and vector similarity.
"""

import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.fact_checking.models import FactCheckItem
from src.monitoring import get_logger

logger = get_logger(__name__)

# RRF (Reciprocal Rank Fusion) constant 'k'.
# Standard value (60) that balances contribution of high and low ranked results.
# Used in formula: score = 1/(k + rank)
# Higher k values reduce the impact of rank differences; k=60 is the de facto standard.
RRF_K_CONSTANT = 60

# Pre-filter limit for each CTE (Common Table Expression) in hybrid search.
# Each search method (semantic and keyword) retrieves this many candidates
# before RRF fusion combines them into final rankings.
#
# Why 20?
# - Balances performance vs. recall for typical fact-checking queries
# - Maximum unique results after RRF = 2 * RRF_CTE_PRELIMIT (40) when
#   semantic and keyword results have zero overlap
# - In practice, good queries have overlap, so final results < 40
# - Higher values increase recall but slow down vector distance calculations
#
# If you need more results, increase this value, but be aware:
# - Semantic search cost scales with this limit (pgvector distance computations)
# - Keyword search is cheaper but still benefits from bounded results
RRF_CTE_PRELIMIT = 20


@dataclass
class HybridSearchResult:
    """Result from hybrid search including RRF score."""

    item: FactCheckItem
    rrf_score: float


async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    limit: int = 10,
    dataset_tags: list[str] | None = None,
    semantic_similarity_threshold: float = 0.0,
    keyword_relevance_threshold: float = 0.0,
) -> list[HybridSearchResult]:
    """
    Perform hybrid search combining FTS and vector similarity using RRF.

    Uses Reciprocal Rank Fusion (RRF) to combine rankings from:
    - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
    - pgvector embedding similarity (cosine distance)

    The RRF formula: score = 1/(k + rank_semantic) + 1/(k + rank_keyword)
    where k=60 (RRF_K_CONSTANT) is the standard RRF constant that balances
    the contribution of high and low ranked results.

    Note: Each search method (semantic/keyword) pre-filters to top
    RRF_CTE_PRELIMIT (20) results before RRF combination, so maximum
    possible results is 2 * RRF_CTE_PRELIMIT (40) when no overlap.

    Args:
        session: Async database session
        query_text: Text query for keyword search
        query_embedding: Vector embedding for semantic search (1536 dimensions)
        limit: Maximum results to return (default: 10)
        dataset_tags: Optional list of dataset tags to filter by. If provided,
            only items with at least one matching tag are returned. Uses
            PostgreSQL array overlap operator (&&) for efficient filtering
            at the SQL level.
        semantic_similarity_threshold: Minimum cosine similarity (0.0-1.0) for
            semantic search results. Results below this threshold are excluded
            from the semantic ranking. Default 0.0 (no filtering).
        keyword_relevance_threshold: Minimum ts_rank_cd score for keyword search
            results. Results below this threshold are excluded from the keyword
            ranking. Default 0.0 (no filtering).

    Returns:
        List of HybridSearchResult containing FactCheckItem and RRF score,
        ranked by combined RRF score (highest first)

    Raises:
        ValueError: If embedding has wrong dimensions
    """
    if len(query_embedding) != settings.EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding must have {settings.EMBEDDING_DIMENSIONS} dimensions, got {len(query_embedding)}"
        )

    query_embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    tags_filter = ""
    if dataset_tags:
        tags_filter = "AND dataset_tags && CAST(:dataset_tags AS text[])"

    # Convert similarity threshold to max distance (cosine distance = 1 - similarity)
    max_semantic_distance = 1.0 - semantic_similarity_threshold

    rrf_query = text(f"""
        WITH semantic AS (
            SELECT id, RANK() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS rank
            FROM fact_check_items
            WHERE embedding IS NOT NULL
                AND (embedding <=> CAST(:embedding AS vector)) <= :max_semantic_distance
                {tags_filter}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT {RRF_CTE_PRELIMIT}
        ),
        keyword AS (
            SELECT id, RANK() OVER (ORDER BY ts_rank_cd(search_vector, query) DESC) AS rank
            FROM fact_check_items, plainto_tsquery('english', :query_text) query
            WHERE search_vector @@ query
                AND ts_rank_cd(search_vector, query) >= :min_keyword_relevance
                {tags_filter}
            ORDER BY ts_rank_cd(search_vector, query) DESC
            LIMIT {RRF_CTE_PRELIMIT}
        )
        SELECT
            fci.id,
            fci.dataset_name,
            fci.dataset_tags,
            fci.title,
            fci.content,
            fci.summary,
            fci.source_url,
            fci.original_id,
            fci.published_date,
            fci.author,
            fci.rating,
            fci.embedding,
            fci.embedding_provider,
            fci.embedding_model,
            fci.metadata as extra_metadata,
            fci.search_vector,
            fci.created_at,
            fci.updated_at,
            COALESCE(1.0/({RRF_K_CONSTANT}+s.rank), 0.0) + COALESCE(1.0/({RRF_K_CONSTANT}+k.rank), 0.0) AS rrf_score
        FROM fact_check_items fci
        LEFT JOIN semantic s ON fci.id = s.id
        LEFT JOIN keyword k ON fci.id = k.id
        WHERE s.id IS NOT NULL OR k.id IS NOT NULL
        ORDER BY rrf_score DESC
        LIMIT :limit
    """)

    params: dict[str, str | int | float | list[str]] = {
        "embedding": query_embedding_str,
        "query_text": query_text,
        "limit": limit,
        "max_semantic_distance": max_semantic_distance,
        "min_keyword_relevance": keyword_relevance_threshold,
    }
    if dataset_tags:
        params["dataset_tags"] = dataset_tags

    query_start = time.perf_counter()
    try:
        result = await session.execute(rrf_query, params)
        rows = result.fetchall()
        query_duration_ms = (time.perf_counter() - query_start) * 1000
    except Exception as e:
        query_duration_ms = (time.perf_counter() - query_start) * 1000
        logger.error(
            "Hybrid search query failed",
            extra={
                "query_text_length": len(query_text),
                "embedding_dimensions": len(query_embedding),
                "limit": limit,
                "dataset_tags": dataset_tags,
                "query_duration_ms": round(query_duration_ms, 2),
                "error": str(e),
            },
        )
        raise

    results = []
    for row in rows:
        item = FactCheckItem(
            id=row.id,
            dataset_name=row.dataset_name,
            dataset_tags=row.dataset_tags,
            title=row.title,
            content=row.content,
            summary=row.summary,
            source_url=row.source_url,
            original_id=row.original_id,
            published_date=row.published_date,
            author=row.author,
            rating=row.rating,
            embedding=row.embedding,
            embedding_provider=row.embedding_provider,
            embedding_model=row.embedding_model,
            extra_metadata=row.extra_metadata or {},
            search_vector=row.search_vector,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        results.append(HybridSearchResult(item=item, rrf_score=float(row.rrf_score)))

    logger.info(
        "Hybrid search completed",
        extra={
            "query_text_length": len(query_text),
            "results_count": len(results),
            "limit": limit,
            "dataset_tags": dataset_tags,
            "query_duration_ms": round(query_duration_ms, 2),
        },
    )

    return results
