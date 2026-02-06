"""Repository functions for fact-checking data access.

Provides database access patterns for fact-checking features, including
hybrid search combining full-text search (FTS) and vector similarity
using Convex Combination (CC) score fusion.
"""

import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.fact_checking.models import FactCheckItem
from src.monitoring import get_logger

logger = get_logger(__name__)

# Default fusion weight (alpha) for Convex Combination.
# Used when Redis is unavailable or no alpha is specified.
# alpha = 0.7 is semantic-weighted, based on research showing semantic search
# generally outperforms keyword search for fact-checking queries.
# Reference: ACM 2023 https://dl.acm.org/doi/10.1145/3596512
DEFAULT_ALPHA = 0.7

FUSION_K_CONSTANT = 60

# Default weight factor for common chunks in TF-IDF-like scoring.
# Common chunks (is_common=True) are reduced by this factor to decrease their
# contribution to scores, similar to inverse document frequency in TF-IDF.
# Value of 0.5 means common chunks contribute 50% of their normal score.
DEFAULT_COMMON_CHUNK_WEIGHT_FACTOR = 0.5

# BM25 length normalization parameter (b).
# Controls how much document length affects scoring:
# - b=0.0: No length normalization (all documents treated equally regardless of length)
# - b=1.0: Full length normalization (longer docs heavily penalized)
# - b=0.75: Standard BM25 value, balanced normalization
# The formula: score / (1 - b + b * (doc_len / avgdl))
# Reference: Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond"
BM25_LENGTH_NORMALIZATION_B = 0.75

# Pre-filter limit for each CTE (Common Table Expression) in hybrid search.
# Each search method (semantic and keyword) retrieves this many candidates
# before fusion combines them into final rankings.
#
# Why 20?
# - Balances performance vs. recall for typical fact-checking queries
# - Maximum unique results after fusion = 2 * CTE_PRELIMIT (40) when
#   semantic and keyword results have zero overlap
# - In practice, good queries have overlap, so final results < 40
# - Higher values increase recall but slow down vector distance calculations
#
# If you need more results, increase this value, but be aware:
# - Semantic search cost scales with this limit (pgvector distance computations)
# - Keyword search is cheaper but still benefits from bounded results
HYBRID_SEARCH_CTE_PRELIMIT = 20

# Multiplier applied to CTE_PRELIMIT for chunk-level CTEs.
# When searching chunks, multiple chunks can map to the same parent fact_check_item.
# We fetch more chunk candidates (PRELIMIT * 3 = 60) to ensure enough unique
# parent items remain after the GROUP BY aggregation step.
# Higher values improve recall but increase query cost; 3x provides good balance.
CHUNK_PRELIMIT_MULTIPLIER = 3


@dataclass
class HybridSearchResult:
    """Result from hybrid search including Convex Combination fusion score."""

    item: FactCheckItem
    cc_score: float  # Convex Combination score in [0, 1] range
    semantic_score: float = 0.0  # Raw cosine similarity before CC fusion


async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    limit: int = 10,
    dataset_tags: list[str] | None = None,
    semantic_similarity_threshold: float = 0.0,
    keyword_relevance_threshold: float = 0.0,
    alpha: float = DEFAULT_ALPHA,
) -> list[HybridSearchResult]:
    """
    Perform hybrid search combining FTS and vector similarity using Convex Combination.

    Uses Convex Combination (CC) to fuse scores from:
    - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
    - pgvector embedding similarity (cosine similarity)

    The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
    where:
    - semantic_similarity = 1 - cosine_distance (already in 0-1 range)
    - keyword_norm = min-max normalized ts_rank_cd within result set
    - alpha ∈ [0, 1] controls the balance (default 0.7, semantic-weighted)

    CC preserves score magnitude information, enabling better relevance
    discrimination and threshold-based filtering compared to RRF.

    Note: Each search method (semantic/keyword) pre-filters to top
    HYBRID_SEARCH_CTE_PRELIMIT (20) results before CC fusion, so maximum
    possible results is 2 * HYBRID_SEARCH_CTE_PRELIMIT (40) when no overlap.

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
        alpha: Fusion weight alpha ∈ [0, 1] for Convex Combination.
            alpha = 1.0 means pure semantic search
            alpha = 0.0 means pure keyword search
            Default 0.7 (semantic-weighted, based on research)

    Returns:
        List of HybridSearchResult containing FactCheckItem and CC score,
        ranked by combined CC score (highest first)

    Raises:
        ValueError: If embedding has wrong dimensions or alpha out of range
    """
    if len(query_embedding) != settings.EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding must have {settings.EMBEDDING_DIMENSIONS} dimensions, got {len(query_embedding)}"
        )

    if not (0.0 <= alpha <= 1.0):
        raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")

    query_embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    tags_filter = ""
    if dataset_tags:
        tags_filter = "AND dataset_tags && CAST(:dataset_tags AS text[])"

    # Convert similarity threshold to max distance (cosine distance = 1 - similarity)
    max_semantic_distance = 1.0 - semantic_similarity_threshold

    # Convex Combination query with min-max normalization for keyword scores.
    #
    # The query uses CTEs to:
    # 1. semantic: Get semantic similarity scores (1 - cosine_distance)
    # 2. keyword_raw: Get raw ts_rank_cd scores
    # 3. keyword_stats: Calculate min/max for normalization
    # 4. keyword: Apply min-max normalization to keyword scores
    # 5. Final SELECT: Apply CC formula: alpha * semantic + (1-alpha) * keyword_norm
    cc_query = text(f"""
        WITH semantic AS (
            -- Get semantic similarity scores (1 - cosine_distance, range 0-1)
            SELECT
                id,
                1.0 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM fact_check_items
            WHERE embedding IS NOT NULL
                AND (embedding <=> CAST(:embedding AS vector)) <= :max_semantic_distance
                {tags_filter}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT {HYBRID_SEARCH_CTE_PRELIMIT}
        ),
        keyword_raw AS (
            -- Get raw ts_rank_cd scores
            SELECT
                id,
                ts_rank_cd(search_vector, query) AS relevance
            FROM fact_check_items, plainto_tsquery('english', :query_text) query
            WHERE search_vector @@ query
                AND ts_rank_cd(search_vector, query) >= :min_keyword_relevance
                {tags_filter}
            ORDER BY ts_rank_cd(search_vector, query) DESC
            LIMIT {HYBRID_SEARCH_CTE_PRELIMIT}
        ),
        keyword_stats AS (
            -- Calculate min/max for normalization
            SELECT
                MIN(relevance) AS min_rel,
                MAX(relevance) AS max_rel
            FROM keyword_raw
        ),
        keyword AS (
            -- Apply min-max normalization: (x - min) / (max - min)
            -- Handle edge case where min == max (returns 1.0 for single result)
            SELECT
                kr.id,
                CASE
                    WHEN ks.max_rel = ks.min_rel THEN 1.0
                    ELSE (kr.relevance - ks.min_rel) / (ks.max_rel - ks.min_rel)
                END AS keyword_norm
            FROM keyword_raw kr
            CROSS JOIN keyword_stats ks
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
            COALESCE(s.similarity, 0.0) AS semantic_score,
            -- Convex Combination: alpha * semantic + (1-alpha) * keyword
            :alpha * COALESCE(s.similarity, 0.0) + (1.0 - :alpha) * COALESCE(k.keyword_norm, 0.0) AS cc_score
        FROM fact_check_items fci
        LEFT JOIN semantic s ON fci.id = s.id
        LEFT JOIN keyword k ON fci.id = k.id
        WHERE s.id IS NOT NULL OR k.id IS NOT NULL
        ORDER BY cc_score DESC
        LIMIT :limit
    """)

    params: dict[str, str | int | float | list[str]] = {
        "embedding": query_embedding_str,
        "query_text": query_text,
        "limit": limit,
        "max_semantic_distance": max_semantic_distance,
        "min_keyword_relevance": keyword_relevance_threshold,
        "alpha": alpha,
    }
    if dataset_tags:
        params["dataset_tags"] = dataset_tags

    query_start = time.perf_counter()
    try:
        result = await session.execute(cc_query, params)
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
                "alpha": alpha,
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
        results.append(
            HybridSearchResult(
                item=item, cc_score=float(row.cc_score), semantic_score=float(row.semantic_score)
            )
        )

    logger.info(
        "Hybrid search completed",
        extra={
            "query_text_length": len(query_text),
            "results_count": len(results),
            "limit": limit,
            "dataset_tags": dataset_tags,
            "alpha": alpha,
            "query_duration_ms": round(query_duration_ms, 2),
        },
    )

    return results


async def hybrid_search_with_chunks(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    limit: int = 10,
    dataset_tags: list[str] | None = None,
    semantic_similarity_threshold: float = 0.0,
    keyword_relevance_threshold: float = 0.05,
    common_chunk_weight_factor: float = DEFAULT_COMMON_CHUNK_WEIGHT_FACTOR,
    alpha: float = DEFAULT_ALPHA,
) -> list[HybridSearchResult]:
    """
    Perform hybrid search using chunk embeddings with Convex Combination fusion.

    This function searches through chunk_embeddings for both semantic and keyword
    searches, providing true chunk-level hybrid search. It applies weight reduction
    to common chunks (is_common=True) similar to inverse document frequency in TF-IDF,
    reducing the contribution of frequently occurring text patterns.

    Uses Convex Combination (CC) to fuse scores from:
    - Chunk-based semantic search via chunk_embeddings.embedding (pgvector HNSW index)
    - Chunk-based full-text search via chunk_embeddings.search_vector (GIN index)

    The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
    where:
    - semantic_similarity = 1 - cosine_distance (already in 0-1 range)
    - keyword_norm = min-max normalized ts_rank_cd within result set
    - alpha ∈ [0, 1] controls the balance (default 0.7, semantic-weighted)

    Multiple chunks per fact_check_item are aggregated using MAX() to select
    the best-matching chunk's score from each search method.

    Args:
        session: Async database session
        query_text: Text query for keyword search
        query_embedding: Vector embedding for semantic search (1536 dimensions)
        limit: Maximum results to return (default: 10)
        dataset_tags: Optional list of dataset tags to filter by. If provided,
            only items with at least one matching tag are returned.
        semantic_similarity_threshold: Minimum cosine similarity (0.0-1.0) for
            semantic search results. Default 0.0 (no filtering).
        keyword_relevance_threshold: Minimum ts_rank_cd score for keyword search
            results. Default 0.05 (filters low-quality keyword matches).
        common_chunk_weight_factor: Weight multiplier for common chunks (0.0-1.0).
            Default 0.5 means common chunks contribute 50% of their normal score.
            Set to 1.0 to disable weight reduction, 0.0 to ignore common chunks.
        alpha: Fusion weight alpha ∈ [0, 1] for Convex Combination.
            alpha = 1.0 means pure semantic search
            alpha = 0.0 means pure keyword search
            Default 0.7 (semantic-weighted, based on research)

    Returns:
        List of HybridSearchResult containing FactCheckItem and CC score,
        ranked by combined CC score (highest first)

    Raises:
        ValueError: If embedding has wrong dimensions or parameters out of range
    """
    if len(query_embedding) != settings.EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding must have {settings.EMBEDDING_DIMENSIONS} dimensions, got {len(query_embedding)}"
        )

    if not (0.0 <= common_chunk_weight_factor <= 1.0):
        raise ValueError(
            f"common_chunk_weight_factor must be between 0.0 and 1.0, got {common_chunk_weight_factor}"
        )

    if not (0.0 <= alpha <= 1.0):
        raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")

    query_embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    # Convert similarity threshold to max distance (cosine distance = 1 - similarity)
    max_semantic_distance = 1.0 - semantic_similarity_threshold

    # Build tags filter for chunk CTEs (joins fact_check_items as fci_chunk)
    chunk_tags_filter = ""
    if dataset_tags:
        chunk_tags_filter = "AND fci_chunk.dataset_tags && CAST(:dataset_tags AS text[])"

    # Convex Combination query for chunk-based search.
    #
    # The query uses CTEs to:
    # 1. chunk_semantic: Get semantic similarity scores from chunks
    # 2. semantic_scores: Aggregate per fact_check_item using MAX()
    # 3. chunk_keyword_raw: Get raw ts_rank_cd scores from chunks
    # 4. keyword_raw_scores: Aggregate per fact_check_item using MAX()
    # 5. keyword_stats: Calculate min/max for normalization
    # 6. keyword_scores: Apply min-max normalization
    # 7. Final SELECT: Apply CC formula: alpha * semantic + (1-alpha) * keyword_norm
    cc_query = text(f"""
        WITH chunk_semantic AS (
            -- Find semantically similar chunks using HNSW index
            -- Calculate similarity score: 1 - cosine_distance
            SELECT
                ce.id AS chunk_id,
                fcc.fact_check_id,
                ce.is_common,
                1.0 - (ce.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunk_embeddings ce
            JOIN fact_check_chunks fcc ON fcc.chunk_id = ce.id
            JOIN fact_check_items fci_chunk ON fci_chunk.id = fcc.fact_check_id
            WHERE ce.embedding IS NOT NULL
                AND (ce.embedding <=> CAST(:embedding AS vector)) <= :max_semantic_distance
                {chunk_tags_filter}
            ORDER BY ce.embedding <=> CAST(:embedding AS vector)
            LIMIT {HYBRID_SEARCH_CTE_PRELIMIT * CHUNK_PRELIMIT_MULTIPLIER}
        ),
        semantic_scores AS (
            -- Aggregate chunk semantic scores per fact_check_item using MAX()
            -- Apply weight reduction for common chunks (TF-IDF-like IDF)
            SELECT
                fact_check_id,
                MAX(
                    similarity *
                    CASE WHEN is_common THEN :common_weight ELSE 1.0 END
                ) AS semantic_score
            FROM chunk_semantic
            GROUP BY fact_check_id
            ORDER BY semantic_score DESC
            LIMIT {HYBRID_SEARCH_CTE_PRELIMIT}
        ),
        chunk_stats_cte AS (
            -- Get corpus statistics for BM25-style length normalization
            SELECT COALESCE(avg_chunk_length, 1.0) AS avg_chunk_length
            FROM chunk_stats
        ),
        pgroonga_scores AS (
            -- CRITICAL: Get PGroonga scores WITHOUT JOINs first!
            -- pgroonga_score() stores scores in an internal hash table keyed by (tableoid, ctid).
            -- When JOINs are present in the same query, PostgreSQL's planner may execute
            -- the scan differently, causing the score lookup to return 0.
            -- Solution: Get scores in isolation, then JOIN the results.
            SELECT
                id AS chunk_id,
                word_count,
                is_common,
                pgroonga_score(tableoid, ctid) AS raw_score
            FROM chunk_embeddings
            WHERE chunk_text &@~ :query_text
        ),
        chunk_keyword_with_bm25 AS (
            -- Apply BM25-lite length normalization and JOIN with fact_check relationships
            -- BM25 formula: score / (1 - b + b * (doc_len / avgdl))
            -- where b is BM25_LENGTH_NORMALIZATION_B (passed as :bm25_b parameter)
            -- COALESCE handles NULL word_count (returns 1 as fallback)
            SELECT
                ps.chunk_id,
                fcc.fact_check_id,
                ps.is_common,
                ps.raw_score / (
                    1.0 - :bm25_b + :bm25_b * (
                        COALESCE(ps.word_count, 1)::float /
                        NULLIF((SELECT avg_chunk_length FROM chunk_stats_cte), 0)
                    )
                ) AS relevance
            FROM pgroonga_scores ps
            JOIN fact_check_chunks fcc ON fcc.chunk_id = ps.chunk_id
            JOIN fact_check_items fci_chunk ON fci_chunk.id = fcc.fact_check_id
            WHERE ps.raw_score > 0
                {chunk_tags_filter}
        ),
        chunk_keyword_raw AS (
            -- Filter by minimum relevance threshold and limit results
            SELECT chunk_id, fact_check_id, is_common, relevance
            FROM chunk_keyword_with_bm25
            WHERE relevance >= :min_keyword_relevance
            ORDER BY relevance DESC
            LIMIT {HYBRID_SEARCH_CTE_PRELIMIT * CHUNK_PRELIMIT_MULTIPLIER}
        ),
        keyword_raw_scores AS (
            -- Aggregate chunk keyword scores per fact_check_item using MAX()
            -- Apply weight reduction for common chunks (TF-IDF-like IDF)
            SELECT
                fact_check_id,
                MAX(
                    relevance *
                    CASE WHEN is_common THEN :common_weight ELSE 1.0 END
                ) AS keyword_raw
            FROM chunk_keyword_raw
            GROUP BY fact_check_id
        ),
        keyword_stats AS (
            -- Calculate min/max for normalization across aggregated scores
            SELECT
                MIN(keyword_raw) AS min_rel,
                MAX(keyword_raw) AS max_rel
            FROM keyword_raw_scores
        ),
        keyword_scores AS (
            -- Apply min-max normalization and limit to top results
            SELECT
                krs.fact_check_id,
                CASE
                    WHEN ks.max_rel = ks.min_rel THEN 1.0
                    ELSE (krs.keyword_raw - ks.min_rel) / (ks.max_rel - ks.min_rel)
                END AS keyword_norm
            FROM keyword_raw_scores krs
            CROSS JOIN keyword_stats ks
            ORDER BY krs.keyword_raw DESC
            LIMIT {HYBRID_SEARCH_CTE_PRELIMIT}
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
            COALESCE(ss.semantic_score, 0.0) AS semantic_score,
            -- Convex Combination: alpha * semantic + (1-alpha) * keyword
            :alpha * COALESCE(ss.semantic_score, 0.0) + (1.0 - :alpha) * COALESCE(ks.keyword_norm, 0.0) AS cc_score
        FROM fact_check_items fci
        LEFT JOIN semantic_scores ss ON fci.id = ss.fact_check_id
        LEFT JOIN keyword_scores ks ON fci.id = ks.fact_check_id
        WHERE ss.fact_check_id IS NOT NULL OR ks.fact_check_id IS NOT NULL
        ORDER BY cc_score DESC
        LIMIT :limit
    """)

    params: dict[str, str | int | float | list[str]] = {
        "embedding": query_embedding_str,
        "query_text": query_text,
        "limit": limit,
        "max_semantic_distance": max_semantic_distance,
        "min_keyword_relevance": keyword_relevance_threshold,
        "common_weight": common_chunk_weight_factor,
        "alpha": alpha,
        "bm25_b": BM25_LENGTH_NORMALIZATION_B,
    }
    if dataset_tags:
        params["dataset_tags"] = dataset_tags

    query_start = time.perf_counter()
    try:
        result = await session.execute(cc_query, params)
        rows = result.fetchall()
        query_duration_ms = (time.perf_counter() - query_start) * 1000
    except Exception as e:
        query_duration_ms = (time.perf_counter() - query_start) * 1000
        logger.error(
            "Chunk-based hybrid search query failed",
            extra={
                "query_text_length": len(query_text),
                "embedding_dimensions": len(query_embedding),
                "limit": limit,
                "dataset_tags": dataset_tags,
                "common_chunk_weight_factor": common_chunk_weight_factor,
                "alpha": alpha,
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
        results.append(
            HybridSearchResult(
                item=item, cc_score=float(row.cc_score), semantic_score=float(row.semantic_score)
            )
        )

    logger.info(
        "Chunk-based hybrid search completed",
        extra={
            "query_text_length": len(query_text),
            "results_count": len(results),
            "limit": limit,
            "dataset_tags": dataset_tags,
            "common_chunk_weight_factor": common_chunk_weight_factor,
            "alpha": alpha,
            "query_duration_ms": round(query_duration_ms, 2),
        },
    )

    return results
