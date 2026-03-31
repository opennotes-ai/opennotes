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


@pytest.fixture(autouse=True)
def bypass_startup_gate():
    """Allow unit tests using ASGITransport to bypass StartupGateMiddleware.

    ASGITransport does not run the app lifespan, so startup_complete is never
    set. Without this, endpoints return 503 'Server initializing'.
    """
    from src.main import app

    prev = getattr(app.state, "startup_complete", None)
    app.state.startup_complete = True
    yield
    if prev is None:
        try:
            del app.state.startup_complete
        except AttributeError:
            pass
    else:
        app.state.startup_complete = prev


@pytest.fixture
def no_db_setup():
    """
    Fixture that does nothing - used to override the autouse setup_database fixture
    for pure unit tests that don't need database access.
    """
