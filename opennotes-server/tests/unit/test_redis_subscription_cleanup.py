"""
Tests for Redis subscription task cleanup to prevent memory leaks (task-234).

This test file verifies that:
1. Subscription tasks are properly tracked
2. Tasks are cancelled when stop() is called
3. No memory leaks occur with multiple subscriptions
4. Proper cleanup happens even if tasks are still running
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.cache.adapters.redis import RedisCacheAdapter


@pytest.fixture
def redis_adapter():
    """Create a Redis adapter for testing."""
    return RedisCacheAdapter(
        host="localhost", port=6379, socket_timeout=1.0, socket_connect_timeout=1.0
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscription_tasks_are_tracked(redis_adapter):
    """Test that subscription tasks are added to tracking list."""
    # Mock Redis client
    mock_client = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = AsyncMock(return_value=asynciter([]))
    # Make pubsub() return the mock directly, not a coroutine
    mock_client.pubsub = MagicMock(return_value=mock_pubsub)

    redis_adapter.client = mock_client
    redis_adapter.is_connected = True

    # Initially no tasks
    assert len(redis_adapter.subscription_tasks) == 0

    # Subscribe to a channel
    handler = MagicMock()
    await redis_adapter.subscribe("test_channel", handler)

    # Task should be tracked
    assert len(redis_adapter.subscription_tasks) == 1
    assert isinstance(redis_adapter.subscription_tasks[0], asyncio.Task)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_multiple_subscriptions_all_tracked(redis_adapter):
    """Test that multiple subscription tasks are all tracked."""
    # Mock Redis client
    mock_client = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = AsyncMock(return_value=asynciter([]))
    # Make pubsub() return the mock directly, not a coroutine
    mock_client.pubsub = MagicMock(return_value=mock_pubsub)

    redis_adapter.client = mock_client
    redis_adapter.is_connected = True

    # Subscribe to multiple channels
    handler = MagicMock()
    await redis_adapter.subscribe("channel1", handler)
    await redis_adapter.subscribe("channel2", handler)
    await redis_adapter.subscribe("channel3", handler)

    # All tasks should be tracked
    assert len(redis_adapter.subscription_tasks) == 3
    assert all(isinstance(task, asyncio.Task) for task in redis_adapter.subscription_tasks)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_stop_cancels_all_subscription_tasks(redis_adapter):
    """Test that stop() cancels all subscription tasks."""
    # Mock Redis client
    mock_client = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    # listen() should return a NEW async iterator each time it's called
    mock_pubsub.listen = MagicMock(side_effect=lambda: async_message_iterator())
    # Make pubsub() return the mock directly, not a coroutine
    mock_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_client.aclose = AsyncMock()

    redis_adapter.client = mock_client
    redis_adapter.is_connected = True
    redis_adapter.pool = AsyncMock()
    redis_adapter.pool.aclose = AsyncMock()

    # Subscribe to channels
    handler = MagicMock()
    await redis_adapter.subscribe("channel1", handler)
    await redis_adapter.subscribe("channel2", handler)

    # Give tasks time to start
    await asyncio.sleep(0.1)

    # Verify tasks are running
    assert len(redis_adapter.subscription_tasks) == 2
    assert all(not task.done() for task in redis_adapter.subscription_tasks)

    # Stop the adapter
    await redis_adapter.stop()

    # All tasks should be cancelled
    assert len(redis_adapter.subscription_tasks) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscription_tasks_cleaned_up_on_stop(redis_adapter):
    """Test that subscription tasks list is cleared after stop()."""
    # Mock Redis client
    mock_client = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = AsyncMock(return_value=asynciter([]))
    # Make pubsub() return the mock directly, not a coroutine
    mock_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_client.aclose = AsyncMock()

    redis_adapter.client = mock_client
    redis_adapter.is_connected = True
    redis_adapter.pool = AsyncMock()
    redis_adapter.pool.aclose = AsyncMock()

    # Subscribe to a channel
    handler = MagicMock()
    await redis_adapter.subscribe("test_channel", handler)

    # Task should be tracked
    assert len(redis_adapter.subscription_tasks) == 1

    # Stop the adapter
    await redis_adapter.stop()

    # Task list should be cleared
    assert len(redis_adapter.subscription_tasks) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscription_handles_cancellation_gracefully(redis_adapter):
    """Test that subscription task handles cancellation and cleans up pubsub."""
    # Mock Redis client
    mock_client = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    # listen() should return a NEW async iterator each time it's called
    mock_pubsub.listen = MagicMock(side_effect=lambda: async_message_iterator())
    # Make pubsub() return the mock directly, not a coroutine
    mock_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_client.aclose = AsyncMock()

    redis_adapter.client = mock_client
    redis_adapter.is_connected = True
    redis_adapter.pool = AsyncMock()
    redis_adapter.pool.aclose = AsyncMock()

    # Subscribe to a channel
    handler = MagicMock()
    await redis_adapter.subscribe("test_channel", handler)

    # Give task time to start
    await asyncio.sleep(0.1)

    # Stop the adapter (which cancels tasks)
    await redis_adapter.stop()

    # Verify pubsub cleanup was called
    mock_pubsub.unsubscribe.assert_called_once_with("test_channel")
    mock_pubsub.aclose.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_no_task_leak_with_repeated_subscribe_and_stop():
    """Test that repeated subscribe/stop cycles don't leak tasks."""
    adapter = RedisCacheAdapter(host="localhost", port=6379)

    handler = MagicMock()

    # Perform multiple subscribe/stop cycles
    for _ in range(5):
        # Create fresh mocks for each iteration (since stop() clears them)
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = MagicMock(return_value=asynciter([]))
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        # Make pubsub() return the mock directly, not a coroutine
        mock_client.pubsub = MagicMock(return_value=mock_pubsub)
        mock_client.aclose = AsyncMock()

        pool_mock = AsyncMock()
        pool_mock.aclose = AsyncMock()

        adapter.client = mock_client
        adapter.pool = pool_mock
        adapter.is_connected = True

        await adapter.subscribe("test_channel", handler)
        assert len(adapter.subscription_tasks) == 1
        await adapter.stop()
        assert len(adapter.subscription_tasks) == 0


async def asynciter(items):
    """Helper to create async iterator from list."""
    for item in items:
        yield item


async def async_message_iterator():
    """Helper to create infinite async message iterator."""
    while True:
        await asyncio.sleep(0.1)
        yield {"type": "message", "data": b"test"}
