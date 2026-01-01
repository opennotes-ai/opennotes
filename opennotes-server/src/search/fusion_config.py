"""Fusion weight configuration for Convex Combination hybrid search.

Provides Redis-backed configuration for the fusion weight (alpha) used in
Convex Combination score fusion:

    final_score = alpha * semantic_similarity + (1-alpha) * keyword_norm

Where:
- alpha ∈ [0, 1] controls the balance between semantic and keyword search
- alpha = 1.0 means pure semantic search
- alpha = 0.0 means pure keyword search
- alpha = 0.7 (default) is semantic-weighted, based on research showing
  semantic search generally outperforms keyword search

Redis Key Structure:
    search:fusion:default_alpha = 0.7          # Global default
    search:fusion:alpha:<dataset> = 0.75       # Per-dataset override

Self-healing pattern:
    On cache miss, restore the key with fallback value to prevent
    repeated cache misses and ensure consistent behavior.

References:
- ACM 2023: https://dl.acm.org/doi/10.1145/3596512
"""

from src.cache.redis_client import RedisClient
from src.monitoring import get_logger

logger = get_logger(__name__)

FALLBACK_ALPHA = 0.7
DEFAULT_ALPHA_KEY = "search:fusion:default_alpha"
DATASET_ALPHA_KEY_PREFIX = "search:fusion:alpha:"


async def get_fusion_alpha(
    redis: RedisClient,
    dataset: str | None = None,
) -> float:
    """
    Get the fusion weight (alpha) for Convex Combination scoring.

    Implements a self-healing cache pattern: on cache miss, restores the key
    with the fallback value to prevent repeated misses.

    Args:
        redis: Redis client instance
        dataset: Optional dataset name for dataset-specific override

    Returns:
        Fusion weight alpha ∈ [0, 1]
    """
    key = f"{DATASET_ALPHA_KEY_PREFIX}{dataset}" if dataset else DEFAULT_ALPHA_KEY

    try:
        value = await redis.get(key)

        if value is None:
            logger.info(
                "Fusion alpha cache miss, restoring with fallback",
                extra={"key": key, "fallback_alpha": FALLBACK_ALPHA},
            )
            await redis.set(key, str(FALLBACK_ALPHA))
            return FALLBACK_ALPHA

        try:
            alpha = float(value)
            if not (0.0 <= alpha <= 1.0):
                logger.warning(
                    "Invalid alpha value in cache, restoring fallback",
                    extra={"key": key, "invalid_value": value},
                )
                await redis.set(key, str(FALLBACK_ALPHA))
                return FALLBACK_ALPHA
            return alpha
        except (ValueError, TypeError):
            logger.warning(
                "Non-numeric alpha value in cache, restoring fallback",
                extra={"key": key, "invalid_value": value},
            )
            await redis.set(key, str(FALLBACK_ALPHA))
            return FALLBACK_ALPHA

    except Exception as e:
        logger.error(
            "Redis error getting fusion alpha, using fallback",
            extra={"key": key, "error": str(e)},
        )
        return FALLBACK_ALPHA


async def set_fusion_alpha(
    redis: RedisClient,
    alpha: float,
    dataset: str | None = None,
) -> bool:
    """
    Set the fusion weight (alpha) for Convex Combination scoring.

    Args:
        redis: Redis client instance
        alpha: Fusion weight alpha ∈ [0, 1]
        dataset: Optional dataset name for dataset-specific override

    Returns:
        True if successfully set, False on error

    Raises:
        ValueError: If alpha is not in [0, 1]
    """
    if not (0.0 <= alpha <= 1.0):
        raise ValueError(f"Alpha must be between 0.0 and 1.0, got {alpha}")

    key = f"{DATASET_ALPHA_KEY_PREFIX}{dataset}" if dataset else DEFAULT_ALPHA_KEY

    try:
        await redis.set(key, str(alpha))
        logger.info(
            "Fusion alpha updated",
            extra={"key": key, "alpha": alpha},
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to set fusion alpha",
            extra={"key": key, "alpha": alpha, "error": str(e)},
        )
        return False


class FusionConfig:
    """
    Fusion weight configuration manager.

    Provides a class-based interface for managing fusion weights
    with methods for getting/setting individual and bulk alphas.
    """

    def __init__(self, redis: RedisClient) -> None:
        """
        Initialize FusionConfig with Redis client.

        Args:
            redis: Redis client instance
        """
        self.redis = redis

    async def get_alpha(self, dataset: str | None = None) -> float:
        """
        Get fusion weight alpha for given dataset or default.

        Args:
            dataset: Optional dataset name for specific override

        Returns:
            Fusion weight alpha ∈ [0, 1]
        """
        return await get_fusion_alpha(self.redis, dataset)

    async def set_alpha(self, alpha: float, dataset: str | None = None) -> bool:
        """
        Set fusion weight alpha for given dataset or default.

        Args:
            alpha: Fusion weight alpha ∈ [0, 1]
            dataset: Optional dataset name for specific override

        Returns:
            True if successfully set, False on error
        """
        return await set_fusion_alpha(self.redis, alpha, dataset)

    async def get_all_alphas(self) -> dict[str, float]:
        """
        Get all configured fusion weights.

        Returns:
            Dictionary with 'default' key and any dataset-specific overrides
        """
        result: dict[str, float] = {}

        default_alpha = await get_fusion_alpha(self.redis)
        result["default"] = default_alpha

        try:
            keys = await self.redis.keys(f"{DATASET_ALPHA_KEY_PREFIX}*")
            if keys:
                values = await self.redis.mget(keys)
                for key, value in zip(keys, values, strict=False):
                    if value is not None:
                        dataset = key.replace(DATASET_ALPHA_KEY_PREFIX, "")
                        try:
                            result[dataset] = float(value)
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.error(
                "Failed to get dataset-specific alphas",
                extra={"error": str(e)},
            )

        return result
