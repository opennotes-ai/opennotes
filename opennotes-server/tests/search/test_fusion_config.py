"""Tests for fusion config service (Convex Combination alpha weights).

Tests the Redis-backed fusion weight configuration with self-healing cache pattern.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.search.fusion_config import (
    DATASET_ALPHA_KEY_PREFIX,
    DEFAULT_ALPHA_KEY,
    FALLBACK_ALPHA,
    FusionConfig,
    get_fusion_alpha,
    set_fusion_alpha,
)


class TestFusionConfigConstants:
    """Tests for fusion config constants."""

    def test_fallback_alpha_is_0_7(self):
        """Fallback alpha should be 0.7 (semantic-weighted per literature)."""
        assert FALLBACK_ALPHA == 0.7

    def test_default_alpha_key_format(self):
        """Default alpha key should follow Redis key convention."""
        assert DEFAULT_ALPHA_KEY == "search:fusion:default_alpha"

    def test_dataset_alpha_key_prefix(self):
        """Dataset-specific alpha key prefix should follow convention."""
        assert DATASET_ALPHA_KEY_PREFIX == "search:fusion:alpha:"


class TestGetFusionAlpha:
    """Tests for get_fusion_alpha function."""

    @pytest.mark.asyncio
    async def test_returns_cached_default_alpha(self):
        """Should return cached default alpha when available."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value="0.8")

        alpha = await get_fusion_alpha(redis_client)

        assert alpha == 0.8
        redis_client.get.assert_called_once_with(DEFAULT_ALPHA_KEY)

    @pytest.mark.asyncio
    async def test_returns_cached_dataset_alpha(self):
        """Should return cached dataset-specific alpha when dataset provided."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value="0.75")

        alpha = await get_fusion_alpha(redis_client, dataset="snopes")

        assert alpha == 0.75
        redis_client.get.assert_called_once_with("search:fusion:alpha:snopes")

    @pytest.mark.asyncio
    async def test_returns_fallback_and_self_heals_on_cache_miss(self):
        """Should return fallback alpha and restore key on cache miss."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=True)

        alpha = await get_fusion_alpha(redis_client)

        assert alpha == FALLBACK_ALPHA
        redis_client.set.assert_called_once_with(DEFAULT_ALPHA_KEY, str(FALLBACK_ALPHA))

    @pytest.mark.asyncio
    async def test_self_heals_dataset_specific_key_on_miss(self):
        """Should self-heal dataset-specific key on cache miss."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=True)

        alpha = await get_fusion_alpha(redis_client, dataset="politifact")

        assert alpha == FALLBACK_ALPHA
        redis_client.set.assert_called_once_with(
            "search:fusion:alpha:politifact", str(FALLBACK_ALPHA)
        )

    @pytest.mark.asyncio
    async def test_returns_fallback_on_redis_error(self):
        """Should return fallback alpha when Redis fails."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(side_effect=Exception("Redis connection failed"))

        alpha = await get_fusion_alpha(redis_client)

        assert alpha == FALLBACK_ALPHA

    @pytest.mark.asyncio
    async def test_handles_invalid_cached_value(self):
        """Should return fallback when cached value is not a valid float."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value="invalid_float")
        redis_client.set = AsyncMock(return_value=True)

        alpha = await get_fusion_alpha(redis_client)

        assert alpha == FALLBACK_ALPHA
        redis_client.set.assert_called_once()


class TestSetFusionAlpha:
    """Tests for set_fusion_alpha function."""

    @pytest.mark.asyncio
    async def test_sets_default_alpha(self):
        """Should set default alpha value."""
        redis_client = AsyncMock()
        redis_client.set = AsyncMock(return_value=True)

        result = await set_fusion_alpha(redis_client, 0.8)

        assert result is True
        redis_client.set.assert_called_once_with(DEFAULT_ALPHA_KEY, "0.8")

    @pytest.mark.asyncio
    async def test_sets_dataset_specific_alpha(self):
        """Should set dataset-specific alpha value."""
        redis_client = AsyncMock()
        redis_client.set = AsyncMock(return_value=True)

        result = await set_fusion_alpha(redis_client, 0.65, dataset="reuters")

        assert result is True
        redis_client.set.assert_called_once_with("search:fusion:alpha:reuters", "0.65")

    @pytest.mark.asyncio
    async def test_rejects_alpha_below_zero(self):
        """Should reject alpha values below 0."""
        redis_client = AsyncMock()

        with pytest.raises(ValueError, match=r"Alpha must be between 0\.0 and 1\.0"):
            await set_fusion_alpha(redis_client, -0.1)

    @pytest.mark.asyncio
    async def test_rejects_alpha_above_one(self):
        """Should reject alpha values above 1."""
        redis_client = AsyncMock()

        with pytest.raises(ValueError, match=r"Alpha must be between 0\.0 and 1\.0"):
            await set_fusion_alpha(redis_client, 1.5)

    @pytest.mark.asyncio
    async def test_returns_false_on_redis_error(self):
        """Should return False when Redis fails."""
        redis_client = AsyncMock()
        redis_client.set = AsyncMock(side_effect=Exception("Redis error"))

        result = await set_fusion_alpha(redis_client, 0.7)

        assert result is False


class TestFusionConfig:
    """Tests for FusionConfig class."""

    def test_fusion_config_initialization(self):
        """FusionConfig should initialize with redis client."""
        redis_client = MagicMock()
        config = FusionConfig(redis_client)
        assert config.redis is redis_client

    @pytest.mark.asyncio
    async def test_get_alpha_delegates_to_function(self):
        """FusionConfig.get_alpha should delegate to get_fusion_alpha."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value="0.8")

        config = FusionConfig(redis_client)
        alpha = await config.get_alpha()

        assert alpha == 0.8

    @pytest.mark.asyncio
    async def test_set_alpha_delegates_to_function(self):
        """FusionConfig.set_alpha should delegate to set_fusion_alpha."""
        redis_client = AsyncMock()
        redis_client.set = AsyncMock(return_value=True)

        config = FusionConfig(redis_client)
        result = await config.set_alpha(0.75)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_all_alphas_returns_dict(self):
        """FusionConfig.get_all_alphas should return all configured alphas."""
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value="0.7")
        redis_client.keys = AsyncMock(
            return_value=[
                "search:fusion:alpha:snopes",
                "search:fusion:alpha:politifact",
            ]
        )
        redis_client.mget = AsyncMock(return_value=["0.75", "0.65"])

        config = FusionConfig(redis_client)
        alphas = await config.get_all_alphas()

        assert alphas["default"] == 0.7
        assert alphas["snopes"] == 0.75
        assert alphas["politifact"] == 0.65
