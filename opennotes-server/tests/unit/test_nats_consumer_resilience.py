"""Tests for NATS consumer resilience.

These tests verify that:
1. Subscribing does NOT delete existing consumers with the same config
2. Multiple instances can share the same durable consumer
3. Only conflicting consumers (different config) are deleted
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
    return client


@pytest.fixture
def mock_jsm(nats_client):
    """Create a mock JetStream manager."""
    jsm = MagicMock()
    nats_client.js._jsm = jsm
    return jsm


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_does_not_delete_existing_consumer_on_first_attempt(nats_client, mock_jsm):
    """Subscribe should try to join existing consumer first without deleting.

    This is the core fix for the race condition: we should NOT delete
    existing consumers before trying to subscribe.
    """
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)
    mock_jsm.delete_consumer = AsyncMock()

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    mock_jsm.delete_consumer.assert_not_called()
    nats_client.js.subscribe.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_deletes_consumer_only_on_conflict_error(nats_client, mock_jsm):
    """Only delete consumer when subscribe fails with a conflict error.

    If the initial subscribe fails because of a config mismatch,
    THEN we delete and retry.
    """
    mock_subscription = MagicMock()

    conflict_error = BadRequestError(
        code=400, err_code=0, description="consumer name already in use"
    )

    nats_client.js.subscribe = AsyncMock(
        side_effect=[
            conflict_error,
            mock_subscription,
        ]
    )
    mock_jsm.delete_consumer = AsyncMock()
    mock_jsm.consumers_info = AsyncMock(return_value=[])

    callback = AsyncMock()
    result = await nats_client.subscribe("OPENNOTES.test_subject", callback)

    assert mock_jsm.delete_consumer.called
    assert result == mock_subscription


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_succeeds_when_joining_existing_consumer(nats_client, mock_jsm):
    """Multiple instances should be able to join the same consumer group.

    When another instance has already created the consumer, we should
    successfully join without any deletion.
    """
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)
    mock_jsm.delete_consumer = AsyncMock()

    callback = AsyncMock()
    result = await nats_client.subscribe("OPENNOTES.test_subject", callback)

    assert result == mock_subscription
    mock_jsm.delete_consumer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_tracks_active_subscriptions(nats_client, mock_jsm):
    """NATSClientManager should track active subscriptions for health monitoring."""
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    assert hasattr(nats_client, "active_subscriptions")
    assert len(nats_client.active_subscriptions) == 1
    assert "OPENNOTES.test_subject" in nats_client.active_subscriptions


@pytest.mark.asyncio
@pytest.mark.unit
async def test_can_verify_subscription_health(nats_client, mock_jsm):
    """Should be able to check if subscriptions are still valid."""
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)

    mock_consumer_info = MagicMock(spec=ConsumerInfo)
    mock_jsm.consumer_info = AsyncMock(return_value=mock_consumer_info)

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    is_healthy = await nats_client.verify_subscriptions_healthy()
    assert is_healthy is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_detects_deleted_consumer(nats_client, mock_jsm):
    """Should detect when our consumer has been deleted by another instance."""
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)

    mock_jsm.consumer_info = AsyncMock(side_effect=Exception("consumer not found"))

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    is_healthy = await nats_client.verify_subscriptions_healthy()
    assert is_healthy is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_can_resubscribe_after_consumer_deleted(nats_client, mock_jsm):
    """Should be able to re-subscribe when consumer is detected as deleted."""
    mock_subscription = MagicMock()
    nats_client.js.subscribe = AsyncMock(return_value=mock_subscription)

    callback = AsyncMock()
    await nats_client.subscribe("OPENNOTES.test_subject", callback)

    mock_jsm.consumer_info = AsyncMock(side_effect=Exception("consumer not found"))

    resubscribe_count = await nats_client.resubscribe_if_needed()
    assert resubscribe_count == 1
