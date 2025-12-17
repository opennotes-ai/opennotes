from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis

from src.webhooks.cache import InteractionCache
from src.webhooks.dependencies import (
    get_new_interaction_cache,
    get_new_rate_limiter,
)
from src.webhooks.rate_limit import RateLimiter
from tests.redis_mock import create_stateful_redis_mock

pytestmark = pytest.mark.unit


class TestInteractionCacheLifecycle:
    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self):
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()
            mock_from_url.return_value = mock_redis

            async with InteractionCache() as cache:
                assert cache.redis_client is not None
                mock_from_url.assert_called_once()

            mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_cleanup_on_exception(self):
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()
            mock_from_url.return_value = mock_redis

            with pytest.raises(ValueError, match="Test exception"):
                async with InteractionCache():
                    raise ValueError("Test exception")

            mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_when_not_connected(self):
        cache = InteractionCache()
        assert await cache.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_when_connected(self):
        cache = InteractionCache()
        mock_redis = create_stateful_redis_mock()
        mock_redis.ping = AsyncMock(return_value=True)
        cache.redis_client = mock_redis

        assert await cache.is_connected() is True
        mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_when_ping_fails(self):
        cache = InteractionCache()
        mock_redis = create_stateful_redis_mock()
        mock_redis.ping = AsyncMock(side_effect=redis.ConnectionError("Connection lost"))
        cache.redis_client = mock_redis

        assert await cache.is_connected() is False

    @pytest.mark.asyncio
    async def test_ping_returns_false_when_not_connected(self):
        cache = InteractionCache()
        assert await cache.ping() is False

    @pytest.mark.asyncio
    async def test_ping_returns_true_when_connected(self):
        cache = InteractionCache()
        mock_redis = create_stateful_redis_mock()
        mock_redis.ping = AsyncMock(return_value=True)
        cache.redis_client = mock_redis

        assert await cache.ping() is True

    @pytest.mark.asyncio
    async def test_auto_reconnection_on_disconnection(self):
        cache = InteractionCache()

        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.exists = AsyncMock(return_value=True)
            mock_from_url.return_value = mock_redis

            result = await cache.check_duplicate("test-interaction")

            assert result is True
            mock_from_url.assert_called()
            mock_redis.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnection_with_exponential_backoff(self):
        cache = InteractionCache()
        cache._max_retries = 3
        cache._retry_delay = 0.01

        call_count = 0

        async def mock_connect_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise redis.ConnectionError("Connection failed")
            cache.redis_client = AsyncMock()
            cache.redis_client.ping = AsyncMock(return_value=True)
            cache.redis_client.exists = AsyncMock(return_value=True)

        with patch.object(cache, "connect", side_effect=mock_connect_side_effect):
            result = await cache.check_duplicate("test-interaction")

            assert call_count == 3
            assert result is True

    @pytest.mark.asyncio
    async def test_reconnection_fails_after_max_retries(self):
        cache = InteractionCache()
        cache._max_retries = 2
        cache._retry_delay = 0.01

        with (
            patch.object(cache, "connect", side_effect=redis.ConnectionError("Connection failed")),
            pytest.raises(RuntimeError, match="Redis client not connected and reconnection failed"),
        ):
            await cache.check_duplicate("test-interaction")

    @pytest.mark.asyncio
    async def test_disconnect_sets_client_to_none(self):
        cache = InteractionCache()
        mock_redis = create_stateful_redis_mock()
        mock_redis.close = AsyncMock()
        cache.redis_client = mock_redis

        await cache.disconnect()

        assert cache.redis_client is None
        mock_redis.close.assert_called_once()


class TestRateLimiterLifecycle:
    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self):
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()
            mock_from_url.return_value = mock_redis

            async with RateLimiter() as limiter:
                assert limiter.redis_client is not None
                mock_from_url.assert_called_once()

            mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected(self):
        limiter = RateLimiter()
        assert await limiter.is_connected() is False

        mock_redis = create_stateful_redis_mock()
        mock_redis.ping = AsyncMock(return_value=True)
        limiter.redis_client = mock_redis

        assert await limiter.is_connected() is True

    @pytest.mark.asyncio
    async def test_auto_reconnection(self):
        limiter = RateLimiter()
        limiter._max_retries = 2
        limiter._retry_delay = 0.01

        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.pipeline = MagicMock()
            mock_pipeline = AsyncMock()
            mock_pipeline.execute = AsyncMock(return_value=[None, None, 50, None])
            mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
            mock_pipeline.__aexit__ = AsyncMock(return_value=None)
            mock_redis.pipeline.return_value = mock_pipeline
            mock_from_url.return_value = mock_redis

            allowed, _remaining = await limiter.check_rate_limit("community-123")

            assert allowed is True
            mock_from_url.assert_called()


class TestDependencyInjection:
    @pytest.mark.asyncio
    async def test_get_new_interaction_cache_cleanup(self):
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()
            mock_from_url.return_value = mock_redis

            async for cache in get_new_interaction_cache():
                assert cache.redis_client is not None

            mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_new_rate_limiter_cleanup(self):
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = create_stateful_redis_mock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()
            mock_from_url.return_value = mock_redis

            async for limiter in get_new_rate_limiter():
                assert limiter.redis_client is not None

            mock_redis.close.assert_called_once()
