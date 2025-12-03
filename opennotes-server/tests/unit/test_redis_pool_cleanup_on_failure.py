"""
Tests for Redis connection pool cleanup on failure (task-797.06).

This test file verifies that:
1. Connection pool is properly cleaned up when ping() fails during start()
2. No resource leaks occur when connection test fails
"""

from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.cache.adapters.redis import RedisCacheAdapter


@pytest.fixture
def redis_adapter():
    """Create a Redis adapter for testing."""
    return RedisCacheAdapter(
        host="localhost", port=6379, socket_timeout=1.0, socket_connect_timeout=1.0
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pool_cleanup_when_ping_fails(redis_adapter):
    """Test that connection pool is cleaned up when ping() fails during start().

    This test verifies that when the Redis client successfully creates a pool
    but then fails the connection test (ping), the pool is properly closed
    to prevent resource leaks.
    """
    mock_pool = AsyncMock()
    mock_pool.aclose = AsyncMock()

    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=RedisConnectionError("Connection refused"))
    mock_client.aclose = AsyncMock()

    with (
        patch("src.cache.adapters.redis.ConnectionPool.from_url", return_value=mock_pool),
        patch("src.cache.adapters.redis.Redis", return_value=mock_client),
    ):
        # start() should raise an exception when ping fails
        with pytest.raises(RedisConnectionError, match="Failed to connect to Redis"):
            await redis_adapter.start()

        # Verify the pool was cleaned up
        mock_pool.aclose.assert_called_once()

        # Verify the adapter state is clean
        assert redis_adapter.is_connected is False
        assert redis_adapter.pool is None
        assert redis_adapter.client is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pool_cleanup_when_ping_times_out(redis_adapter):
    """Test that connection pool is cleaned up when ping() times out during start()."""
    from redis.exceptions import TimeoutError as RedisTimeoutError

    mock_pool = AsyncMock()
    mock_pool.aclose = AsyncMock()

    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=RedisTimeoutError("Connection timed out"))
    mock_client.aclose = AsyncMock()

    with (
        patch("src.cache.adapters.redis.ConnectionPool.from_url", return_value=mock_pool),
        patch("src.cache.adapters.redis.Redis", return_value=mock_client),
    ):
        # start() should raise an exception when ping times out
        with pytest.raises(RedisConnectionError, match="Failed to connect to Redis"):
            await redis_adapter.start()

        # Verify the pool was cleaned up
        mock_pool.aclose.assert_called_once()

        # Verify the adapter state is clean
        assert redis_adapter.is_connected is False
        assert redis_adapter.pool is None
        assert redis_adapter.client is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_client_cleanup_when_ping_fails(redis_adapter):
    """Test that Redis client is also cleaned up when ping() fails."""
    mock_pool = AsyncMock()
    mock_pool.aclose = AsyncMock()

    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=RedisConnectionError("Connection refused"))
    mock_client.aclose = AsyncMock()

    with (
        patch("src.cache.adapters.redis.ConnectionPool.from_url", return_value=mock_pool),
        patch("src.cache.adapters.redis.Redis", return_value=mock_client),
    ):
        with pytest.raises(RedisConnectionError):
            await redis_adapter.start()

        # Verify the client was also cleaned up
        mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_successful_start_does_not_close_pool(redis_adapter):
    """Test that a successful start() does not prematurely close the pool."""
    mock_pool = AsyncMock()
    mock_pool.aclose = AsyncMock()

    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.aclose = AsyncMock()

    with (
        patch("src.cache.adapters.redis.ConnectionPool.from_url", return_value=mock_pool),
        patch("src.cache.adapters.redis.Redis", return_value=mock_client),
    ):
        await redis_adapter.start()

        # Verify the pool was NOT closed
        mock_pool.aclose.assert_not_called()

        # Verify the adapter state is connected
        assert redis_adapter.is_connected is True
        assert redis_adapter.pool is mock_pool
        assert redis_adapter.client is mock_client
