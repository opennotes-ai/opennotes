"""Search analytics logging for fusion weight optimization.

Logs search queries with scores and metadata to enable analysis
for optimizing fusion weights (alpha). Uses structured logging for
easy aggregation and analysis.

Privacy considerations:
- Query text is hashed (SHA256) to avoid logging PII
- Only statistical data (scores, counts) are logged
- No user identifiers are logged

Usage:
    Log search results for analysis:
    ```python
    await log_search_results(
        query_hash=hash_query(query_text),
        alpha=0.7,
        dataset_tags=["snopes"],
        results=hybrid_results,
    )
    ```
"""

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import orjson
import pendulum

from src.cache.redis_client import RedisClient
from src.config import get_settings
from src.monitoring import get_logger
from src.monitoring.metrics import search_analytics_failures_total

if TYPE_CHECKING:
    from src.fact_checking.repository import HybridSearchResult

logger = get_logger(__name__)

SEARCH_LOG_KEY_PREFIX = "search:log:"
SEARCH_STATS_KEY = "search:fusion:stats"
SEARCH_LOG_TTL_SECONDS = 86400 * 7  # 7 days


@dataclass
class SearchAnalyticsEntry:
    """Analytics entry for a single search."""

    query_hash: str
    alpha: float
    dataset_tags: list[str]
    result_count: int
    top_score: float | None
    min_score: float | None
    max_score: float | None
    score_spread: float | None
    timestamp: str


def hash_query(query_text: str) -> str:
    """
    Hash a query for privacy-preserving logging.

    Args:
        query_text: The original query text

    Returns:
        SHA256 hash of the query (first 16 chars for brevity)
    """
    return hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:16]


def compute_score_stats(results: list["HybridSearchResult"]) -> dict[str, float | None]:
    """
    Compute score statistics from search results.

    Args:
        results: List of hybrid search results

    Returns:
        Dictionary with min, max, spread, and top score
    """
    if not results:
        return {
            "top_score": None,
            "min_score": None,
            "max_score": None,
            "score_spread": None,
        }

    scores = [r.cc_score for r in results]
    min_score = min(scores)
    max_score = max(scores)

    return {
        "top_score": scores[0] if scores else None,
        "min_score": min_score,
        "max_score": max_score,
        "score_spread": max_score - min_score if len(scores) > 1 else 0.0,
    }


async def log_search_results(
    redis: RedisClient | None,
    query_hash: str,
    alpha: float,
    dataset_tags: list[str] | None,
    results: list["HybridSearchResult"],
    query_duration_ms: float | None = None,
) -> None:
    """
    Log search results for fusion weight optimization analysis.

    Logs to both structured logger and optionally Redis for aggregation.

    Args:
        redis: Redis client (optional, for persistent storage)
        query_hash: Hashed query text
        alpha: Fusion weight used
        dataset_tags: Dataset tags used in search
        results: Search results
        query_duration_ms: Query duration in milliseconds
    """
    stats = compute_score_stats(results)

    entry = SearchAnalyticsEntry(
        query_hash=query_hash,
        alpha=alpha,
        dataset_tags=dataset_tags or [],
        result_count=len(results),
        top_score=stats["top_score"],
        min_score=stats["min_score"],
        max_score=stats["max_score"],
        score_spread=stats["score_spread"],
        timestamp=pendulum.now("UTC").isoformat(),
    )

    logger.info(
        "Search analytics",
        extra={
            "search_analytics": True,
            "query_hash": entry.query_hash,
            "alpha": entry.alpha,
            "dataset_tags": entry.dataset_tags,
            "result_count": entry.result_count,
            "top_score": entry.top_score,
            "score_spread": entry.score_spread,
            "query_duration_ms": query_duration_ms,
        },
    )

    if redis and redis.client:
        try:
            timestamp_ms = int(time.time() * 1000)
            key = f"{SEARCH_LOG_KEY_PREFIX}{timestamp_ms}:{query_hash}"

            entry_dict = {
                "query_hash": entry.query_hash,
                "alpha": entry.alpha,
                "dataset_tags": entry.dataset_tags,
                "result_count": entry.result_count,
                "top_score": entry.top_score,
                "min_score": entry.min_score,
                "max_score": entry.max_score,
                "score_spread": entry.score_spread,
                "timestamp": entry.timestamp,
                "query_duration_ms": query_duration_ms,
            }

            await redis.set(key, orjson.dumps(entry_dict).decode(), ttl=SEARCH_LOG_TTL_SECONDS)

            await _update_aggregate_stats(redis, entry)

        except Exception as e:
            settings = get_settings()
            search_analytics_failures_total.labels(
                operation="log_entry", instance_id=settings.INSTANCE_ID
            ).inc()
            logger.warning(
                "Failed to log search analytics to Redis",
                extra={"error": str(e)},
            )


async def _update_aggregate_stats(redis: RedisClient, entry: SearchAnalyticsEntry) -> None:
    """
    Update aggregate statistics in Redis.

    Maintains running statistics for analysis.
    """
    try:
        stats_raw = await redis.get(SEARCH_STATS_KEY)
        if stats_raw:
            stats = orjson.loads(stats_raw)
        else:
            stats = {
                "total_searches": 0,
                "total_results": 0,
                "avg_score_spread": 0.0,
                "alpha_usage": {},
            }

        stats["total_searches"] += 1  # pyright: ignore[reportOperatorIssue]
        stats["total_results"] += entry.result_count  # pyright: ignore[reportOperatorIssue]

        if entry.score_spread is not None:
            n = stats["total_searches"]
            old_avg = stats["avg_score_spread"]
            stats["avg_score_spread"] = old_avg + (entry.score_spread - old_avg) / n  # pyright: ignore[reportOperatorIssue]

        alpha_key = str(entry.alpha)
        if alpha_key not in stats["alpha_usage"]:  # pyright: ignore[reportOperatorIssue]
            stats["alpha_usage"][alpha_key] = 0  # pyright: ignore[reportIndexIssue]
        stats["alpha_usage"][alpha_key] += 1  # pyright: ignore[reportIndexIssue]

        await redis.set(SEARCH_STATS_KEY, orjson.dumps(stats).decode())

    except Exception as e:
        settings = get_settings()
        search_analytics_failures_total.labels(
            operation="update_stats", instance_id=settings.INSTANCE_ID
        ).inc()
        logger.warning(
            "Failed to update aggregate search stats",
            extra={"error": str(e)},
        )


async def get_search_stats(redis: RedisClient) -> dict[str, Any] | None:
    """
    Get aggregate search statistics.

    Args:
        redis: Redis client

    Returns:
        Aggregate statistics or None if not available
    """
    try:
        stats_raw = await redis.get(SEARCH_STATS_KEY)
        if stats_raw:
            return orjson.loads(stats_raw)
        return None
    except Exception as e:
        settings = get_settings()
        search_analytics_failures_total.labels(
            operation="get_stats", instance_id=settings.INSTANCE_ID
        ).inc()
        logger.warning(
            "Failed to get search stats",
            extra={"error": str(e)},
        )
        return None
