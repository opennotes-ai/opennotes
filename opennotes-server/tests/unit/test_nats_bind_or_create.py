"""Tests for NATS bind-or-create consumer pattern.

These tests verify that:
1. When a consumer exists, we bind to it without recreating
2. When a consumer doesn't exist, we create it
3. We NEVER delete other instances' consumers
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.js.api import ConsumerInfo
from nats.js.errors import BadRequestError

from src.events.nats_client import NATSClientManager


@pytest.fixture
def nats_client():
    """Create a NATSClientManager with mocked NATS connection."""
    client = NATSClientManager()
    client.nc = MagicMock()
    client.nc.is_connected = True
    client.js = MagicMock()
    client.js._jsm = MagicMock()
    return client


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_binds_to_existing_consumer(nats_client):
    """When consumer already exists, subscribe should bind to it without creating.

    This is critical for multi-instance startup: if Instance 1 creates a consumer,
    Instance 2 should bind to it (join queue group) instead of trying to create
    a new one.
    """
    mock_jsm = nats_client.js._jsm

    existing_consumer = MagicMock(spec=ConsumerInfo)
    existing_consumer.config = MagicMock()
    existing_consumer.config.durable_name = "opennotes_OPENNOTES_test_subject"
    existing_consumer.config.deliver_group = "opennotes_OPENNOTES_test_subject"
    mock_jsm.consumer_info = AsyncMock(return_value=existing_consumer)

    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    call_args = nats_client.js.subscribe.call_args
    assert call_args is not None
    _, kwargs = call_args
    assert "config" not in kwargs or kwargs.get("config") is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_creates_consumer_when_not_exists(nats_client):
    """When consumer doesn't exist, subscribe should create it with config."""
    mock_jsm = nats_client.js._jsm

    mock_jsm.consumer_info = AsyncMock(side_effect=Exception("consumer not found"))

    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    call_args = nats_client.js.subscribe.call_args
    assert call_args is not None
    _, kwargs = call_args
    assert "config" in kwargs
    assert kwargs["config"] is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_never_deletes_existing_consumers(nats_client):
    """Subscribe should NEVER delete consumers, even on conflict.

    This is the critical safety guarantee: we must not delete other instances'
    consumers under any circumstances. The proper solution for conflicts is
    to retry binding, not to delete.
    """
    mock_jsm = nats_client.js._jsm

    existing_consumer = MagicMock(spec=ConsumerInfo)
    mock_jsm.consumer_info = AsyncMock(return_value=existing_consumer)
    mock_jsm.delete_consumer = AsyncMock()

    conflict_error = BadRequestError(
        code=400, err_code=0, description="consumer name already in use"
    )
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(side_effect=[conflict_error, mock_subscription])

    callback = AsyncMock()

    try:
        await nats_client.subscribe("OPENNOTES.test_subject", callback)
    except BadRequestError:
        pass

    mock_jsm.delete_consumer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_method_is_deprecated_noop(nats_client):
    """_cleanup_conflicting_consumers should be a no-op (deprecated).

    The method should exist but do nothing, to prevent any code paths
    from accidentally deleting consumers.
    """
    mock_jsm = nats_client.js._jsm
    mock_jsm.delete_consumer = AsyncMock()
    mock_jsm.consumers_info = AsyncMock(return_value=[])

    await nats_client._cleanup_conflicting_consumers("OPENNOTES.test_subject", "test_consumer")

    mock_jsm.delete_consumer.assert_not_called()
