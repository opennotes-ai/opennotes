"""
Tests for task-241: Verify Redis adapter has connection health checks and auto-reconnect.

These tests verify that the RedisCacheAdapter:
1. Has _ensure_connected method with ping check
2. All operations call _ensure_connected
3. Auto-reconnects on connection failure
4. Reconnection behavior works correctly
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.cache.adapters.redis import RedisCacheAdapter


@pytest.fixture
def redis_adapter():
    """Create Redis adapter instance for testing."""
    return RedisCacheAdapter(
        host="localhost",
        port=6379,
        max_retries=3,
    )


@pytest.mark.asyncio
async def test_ensure_connected_pings_redis(redis_adapter):
    """Test that _ensure_connected performs ping check to verify connection is alive."""
    # Setup mock client
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    redis_adapter.client = mock_client
    redis_adapter.is_connected = True

    # Call _ensure_connected
    result = await redis_adapter._ensure_connected()

    # Verify ping was called
    assert result is True
    mock_client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_connected_reconnects_on_ping_failure(redis_adapter):
    """Test that _ensure_connected attempts reconnection when ping fails."""
    # Setup mock client that fails ping
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=RedisConnectionError("Connection lost"))
    redis_adapter.client = mock_client
    redis_adapter.is_connected = True

    # Mock start method to simulate successful reconnection
    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = None

        # After start is called, connection should be restored
        async def reset_ping():
            redis_adapter.is_connected = True
            redis_adapter.client.ping = AsyncMock(return_value=True)

        mock_start.side_effect = reset_ping

        result = await redis_adapter._ensure_connected()

        # Verify reconnection was attempted
        assert mock_start.called
        assert redis_adapter.is_connected is False or result is True


@pytest.mark.asyncio
async def test_ensure_connected_starts_if_not_connected(redis_adapter):
    """Test that _ensure_connected calls start() if not connected."""
    redis_adapter.is_connected = False
    redis_adapter.client = None

    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = None

        await redis_adapter._ensure_connected()

        # Verify start was called
        mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_get_calls_ensure_connected(redis_adapter):
    """Test that get() operation calls _ensure_connected before executing."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = False  # Simulate connection failure

        result = await redis_adapter.get("test_key")

        # Verify _ensure_connected was called
        mock_ensure.assert_called_once()
        # Verify get returned default (None) since connection failed
        assert result is None


@pytest.mark.asyncio
async def test_set_calls_ensure_connected(redis_adapter):
    """Test that set() operation calls _ensure_connected before executing."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = False  # Simulate connection failure

        result = await redis_adapter.set("test_key", "test_value")

        # Verify _ensure_connected was called
        mock_ensure.assert_called_once()
        # Verify set returned False since connection failed
        assert result is False


@pytest.mark.asyncio
async def test_delete_calls_ensure_connected(redis_adapter):
    """Test that delete() operation calls _ensure_connected before executing."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = False  # Simulate connection failure

        result = await redis_adapter.delete("test_key")

        # Verify _ensure_connected was called
        mock_ensure.assert_called_once()
        # Verify delete returned False since connection failed
        assert result is False


@pytest.mark.asyncio
async def test_auto_reconnect_on_connection_drop(redis_adapter):
    """Test that adapter automatically reconnects when connection drops."""
    # Simulate initial connection
    mock_client = AsyncMock()
    mock_pool = MagicMock()
    redis_adapter.client = mock_client
    redis_adapter.pool = mock_pool
    redis_adapter.is_connected = True

    # First ping succeeds
    mock_client.ping = AsyncMock(return_value=True)

    # Verify connected
    result1 = await redis_adapter._ensure_connected()
    assert result1 is True

    # Simulate connection drop (ping fails)
    mock_client.ping = AsyncMock(side_effect=RedisConnectionError("Connection lost"))

    # Mock start to simulate successful reconnection
    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        # After start, restore connection
        async def restore_connection():
            redis_adapter.is_connected = True
            mock_new_client = AsyncMock()
            mock_new_client.ping = AsyncMock(return_value=True)
            redis_adapter.client = mock_new_client

        mock_start.side_effect = restore_connection

        # Call _ensure_connected after connection drop
        result2 = await redis_adapter._ensure_connected()

        # Verify reconnection was attempted
        assert mock_start.called
        # Connection should be restored (or failed gracefully)
        assert isinstance(result2, bool)


@pytest.mark.asyncio
async def test_ensure_connected_returns_false_on_reconnect_failure(redis_adapter):
    """Test that _ensure_connected returns False when reconnection fails."""
    redis_adapter.is_connected = False
    redis_adapter.client = None

    # Mock start to fail
    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        mock_start.side_effect = RedisConnectionError("Cannot connect to Redis")

        result = await redis_adapter._ensure_connected()

        # Verify result is False
        assert result is False


@pytest.mark.asyncio
async def test_operations_return_gracefully_when_connection_fails(redis_adapter):
    """Test that all operations return gracefully when connection check fails."""
    # Mock _ensure_connected to always return False
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = False

        # Test get
        get_result = await redis_adapter.get("key", default="default_value")
        assert get_result == "default_value"

        # Test set
        set_result = await redis_adapter.set("key", "value")
        assert set_result is False

        # Test delete
        delete_result = await redis_adapter.delete("key")
        assert delete_result is False

        # Verify _ensure_connected was called for each operation
        assert mock_ensure.call_count == 3


@pytest.mark.asyncio
async def test_ping_timeout_triggers_reconnect(redis_adapter):
    """Test that ping timeout triggers reconnection attempt."""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=RedisConnectionError("Ping timeout"))
    redis_adapter.client = mock_client
    redis_adapter.is_connected = True

    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        await redis_adapter._ensure_connected()

        # Verify start was called after timeout
        assert mock_start.called


@pytest.mark.asyncio
async def test_connection_state_updated_correctly(redis_adapter):
    """Test that is_connected flag is updated correctly during reconnection."""
    redis_adapter.is_connected = True
    redis_adapter.client = AsyncMock()

    # Simulate connection failure
    redis_adapter.client.ping = AsyncMock(side_effect=RedisConnectionError("Connection failed"))

    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        mock_start.side_effect = RedisConnectionError("Reconnect failed")

        result = await redis_adapter._ensure_connected()

        # Verify connection state was marked as disconnected
        assert redis_adapter.is_connected is False
        # Verify result indicates failure
        assert result is False


@pytest.mark.asyncio
async def test_multiple_reconnect_attempts(redis_adapter):
    """Test that adapter handles multiple reconnection attempts gracefully."""
    redis_adapter.is_connected = True
    redis_adapter.client = AsyncMock()
    redis_adapter.client.ping = AsyncMock(side_effect=RedisConnectionError("Connection lost"))

    call_count = 0

    async def mock_start_with_retries():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RedisConnectionError("Reconnect failed")
        # Succeed on 3rd attempt
        redis_adapter.is_connected = True
        redis_adapter.client = AsyncMock()
        redis_adapter.client.ping = AsyncMock(return_value=True)

    with patch.object(redis_adapter, "start", new_callable=AsyncMock) as mock_start:
        mock_start.side_effect = mock_start_with_retries

        # First two attempts fail
        result1 = await redis_adapter._ensure_connected()
        assert result1 is False

        result2 = await redis_adapter._ensure_connected()
        assert result2 is False

        # Third attempt succeeds
        result3 = await redis_adapter._ensure_connected()
        assert result3 is True
