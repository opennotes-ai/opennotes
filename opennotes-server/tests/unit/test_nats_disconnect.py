from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.nats_client import NATSClientManager


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disconnect_handles_drain_failure():
    client = NATSClientManager()
    mock_nc = MagicMock()
    mock_nc.drain = AsyncMock(side_effect=Exception("Drain failed"))
    mock_nc.close = AsyncMock()

    client.nc = mock_nc
    client.js = MagicMock()

    await client.disconnect()

    mock_nc.drain.assert_called_once()
    mock_nc.close.assert_called_once()
    assert client.nc is None
    assert client.js is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disconnect_handles_close_failure():
    client = NATSClientManager()
    mock_nc = MagicMock()
    mock_nc.drain = AsyncMock()
    mock_nc.close = AsyncMock(side_effect=Exception("Close failed"))

    client.nc = mock_nc
    client.js = MagicMock()

    await client.disconnect()

    mock_nc.drain.assert_called_once()
    mock_nc.close.assert_called_once()
    assert client.nc is None
    assert client.js is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disconnect_handles_both_drain_and_close_failure():
    client = NATSClientManager()
    mock_nc = MagicMock()
    mock_nc.drain = AsyncMock(side_effect=Exception("Drain failed"))
    mock_nc.close = AsyncMock(side_effect=Exception("Close failed"))

    client.nc = mock_nc
    client.js = MagicMock()

    await client.disconnect()

    mock_nc.drain.assert_called_once()
    mock_nc.close.assert_called_once()
    assert client.nc is None
    assert client.js is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disconnect_succeeds_normally():
    client = NATSClientManager()
    mock_nc = MagicMock()
    mock_nc.drain = AsyncMock()
    mock_nc.close = AsyncMock()

    client.nc = mock_nc
    client.js = MagicMock()

    await client.disconnect()

    mock_nc.drain.assert_called_once()
    mock_nc.close.assert_called_once()
    assert client.nc is None
    assert client.js is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disconnect_when_not_connected():
    client = NATSClientManager()
    client.nc = None
    client.js = None

    await client.disconnect()

    assert client.nc is None
    assert client.js is None
