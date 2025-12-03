from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def clear_settings_singleton():
    """Clear Settings singleton before each unit test to avoid state leakage."""
    from src.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def mock_nats_client():
    """Mock NATS client for unit tests to avoid connection errors."""
    from nats.js.api import PubAck

    from src.events.nats_client import nats_client

    nats_client.nc = MagicMock()
    nats_client.js = MagicMock()

    mock_pub_ack = PubAck(stream="OPENNOTES", seq=1, duplicate=False)
    nats_client.publish = AsyncMock(return_value=mock_pub_ack)

    yield

    nats_client.nc = None
    nats_client.js = None
    nats_client.publish.reset_mock()


@pytest.fixture
def no_db_setup():
    """
    Fixture that does nothing - used to override the autouse setup_database fixture
    for pure unit tests that don't need database access.
    """
