"""Cache monitoring integration with OpenTelemetry metrics."""

import logging
from typing import TYPE_CHECKING

from src.cache.interfaces import CacheMetrics
from src.monitoring.metrics import (
    cache_evictions_total,
    cache_hit_rate,
    cache_hits_total,
    cache_misses_total,
    cache_size_items,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_previous_metrics: dict[str, "CacheMetrics"] = {}


def update_cache_metrics(cache_type: str, metrics: "CacheMetrics") -> None:
    """
    Update OTEL metrics from cache adapter metrics.

    This function tracks deltas since the last update to avoid accumulating
    cumulative totals in counters, which should only increase
    by the delta since last update.

    Args:
        cache_type: Type of cache (e.g., 'redis', 'memory')
        metrics: CacheMetrics object from the cache adapter
    """
    try:
        prev = _previous_metrics.get(cache_type, CacheMetrics())

        hits_delta = metrics.hits - prev.hits
        misses_delta = metrics.misses - prev.misses
        evictions_delta = metrics.evictions - prev.evictions

        if hits_delta > 0:
            cache_hits_total.add(hits_delta, {"cache_type": cache_type, "key_prefix": ""})
        if misses_delta > 0:
            cache_misses_total.add(misses_delta, {"cache_type": cache_type, "key_prefix": ""})
        if evictions_delta > 0:
            cache_evictions_total.add(
                evictions_delta, {"cache_type": cache_type, "reason": "policy"}
            )

        cache_size_items.set(metrics.size, {"cache_type": cache_type})
        hit_rate = metrics.hit_rate() * 100
        cache_hit_rate.set(hit_rate, {"cache_type": cache_type})

        _previous_metrics[cache_type] = metrics

        logger.debug(
            f"Updated {cache_type} metrics: "
            f"hits={metrics.hits}(+{hits_delta}), misses={metrics.misses}(+{misses_delta}), "
            f"hit_rate={hit_rate:.2f}%, size={metrics.size}"
        )

    except ImportError:
        logger.debug("OTEL metrics not available, skipping cache metrics update")
    except Exception as e:
        logger.warning(f"Failed to update cache metrics: {e}")


def get_cache_metrics_summary(
    cache_type: str, metrics: "CacheMetrics"
) -> dict[str, str | int | float]:
    """
    Get a summary of cache metrics for logging/debugging.

    Args:
        cache_type: Type of cache
        metrics: CacheMetrics object

    Returns:
        Dictionary with metric summary
    """
    return {
        "cache_type": cache_type,
        "hits": metrics.hits,
        "misses": metrics.misses,
        "hit_rate": f"{metrics.hit_rate() * 100:.2f}%",
        "sets": metrics.sets,
        "deletes": metrics.deletes,
        "evictions": metrics.evictions,
        "size": metrics.size,
        "memory_bytes": metrics.memory_bytes,
    }
