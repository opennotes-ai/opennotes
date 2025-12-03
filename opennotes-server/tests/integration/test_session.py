import pytest

from src.cache.redis_client import redis_client
from src.cache.session import SessionManager


@pytest.fixture
async def setup_redis():
    await redis_client.connect()
    yield
    if redis_client.client:
        await redis_client.client.flushdb()
    await redis_client.disconnect()


@pytest.fixture
def session_manager(setup_redis):
    """Provide a SessionManager instance with connected Redis client."""
    return SessionManager(redis_client)


@pytest.mark.asyncio
async def test_create_session(session_manager):
    session = await session_manager.create_session(
        user_id=1,
        username="testuser",
        device_id="device_123",
        ttl=3600,
    )

    assert session.session_id is not None
    assert session.user_id == 1
    assert session.username == "testuser"
    assert session.device_id == "device_123"


@pytest.mark.asyncio
async def test_get_session(session_manager):
    created_session = await session_manager.create_session(
        user_id=1,
        username="testuser",
    )

    retrieved_session = await session_manager.get_session(created_session.session_id)
    assert retrieved_session is not None
    assert retrieved_session.session_id == created_session.session_id
    assert retrieved_session.user_id == 1


@pytest.mark.asyncio
async def test_refresh_session(session_manager):
    session = await session_manager.create_session(
        user_id=1,
        username="testuser",
        ttl=60,
    )

    original_expires_at = session.expires_at

    refreshed = await session_manager.refresh_session(session.session_id, ttl=120)
    assert refreshed is not None
    assert refreshed.expires_at > original_expires_at


@pytest.mark.asyncio
async def test_delete_session(session_manager):
    session = await session_manager.create_session(
        user_id=1,
        username="testuser",
    )

    deleted = await session_manager.delete_session(session.session_id)
    assert deleted is True

    retrieved = await session_manager.get_session(session.session_id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_get_user_sessions(session_manager):
    user_id = 1

    session1 = await session_manager.create_session(
        user_id=user_id,
        username="testuser",
        device_id="device_1",
    )

    session2 = await session_manager.create_session(
        user_id=user_id,
        username="testuser",
        device_id="device_2",
    )

    sessions = await session_manager.get_user_sessions(user_id)
    assert len(sessions) == 2
    session_ids = [s.session_id for s in sessions]
    assert session1.session_id in session_ids
    assert session2.session_id in session_ids


@pytest.mark.asyncio
async def test_delete_user_sessions(session_manager):
    user_id = 1

    await session_manager.create_session(user_id=user_id, username="testuser")
    await session_manager.create_session(user_id=user_id, username="testuser")

    count = await session_manager.delete_user_sessions(user_id)
    assert count == 2

    sessions = await session_manager.get_user_sessions(user_id)
    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_delete_device_session(session_manager):
    user_id = 1

    await session_manager.create_session(
        user_id=user_id,
        username="testuser",
        device_id="device_1",
    )

    await session_manager.create_session(
        user_id=user_id,
        username="testuser",
        device_id="device_2",
    )

    deleted = await session_manager.delete_device_session(user_id, "device_1")
    assert deleted is True

    sessions = await session_manager.get_user_sessions(user_id)
    assert len(sessions) == 1
    assert sessions[0].device_id == "device_2"


@pytest.mark.asyncio
async def test_session_expiration(session_manager):
    import time

    session = await session_manager.create_session(
        user_id=1,
        username="testuser",
        ttl=1,
    )

    time.sleep(1.5)

    retrieved = await session_manager.get_session(session.session_id)
    assert retrieved is None
