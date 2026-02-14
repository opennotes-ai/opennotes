"""
Tests for task-233 and task-243: Verify SessionManager operations are atomic.

These tests verify that:
1. create_session uses Redis pipeline to ensure atomic operations (task-233)
2. delete_session uses Redis pipeline to ensure atomic operations (task-243)
3. No partial state if Redis operations fail
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pendulum
import pytest

from src.cache.models import SessionData
from src.cache.session import SessionManager
from tests.redis_mock import create_stateful_redis_mock


@pytest.fixture
def mock_redis_client():
    """
    Create a mock Redis client with centralized mocking.

    This fixture wraps the centralized StatefulRedisMock to provide
    consistent behavior for session manager atomicity tests.
    """
    client = MagicMock()
    client.client = create_stateful_redis_mock()
    return client


@pytest.fixture
def session_manager(mock_redis_client):
    """Create SessionManager with mock Redis client."""
    return SessionManager(mock_redis_client)


@pytest.mark.asyncio
async def test_create_session_uses_pipeline(session_manager, mock_redis_client):
    """Test that create_session uses Redis pipeline with transaction=True."""
    # Setup mock pipeline
    mock_pipeline = AsyncMock()
    mock_pipeline.set = MagicMock()
    mock_pipeline.sadd = MagicMock()
    mock_pipeline.expire = MagicMock()
    mock_pipeline.execute = AsyncMock(return_value=[True, 1, True])
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock(return_value=None)

    mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

    # Create session
    session = await session_manager.create_session(
        user_id=123,
        username="testuser",
        device_id="device1",
        ttl=3600,
    )

    # Verify pipeline was used with transaction=True
    mock_redis_client.client.pipeline.assert_called_once_with(transaction=True)

    # Verify all three operations were added to pipeline
    assert mock_pipeline.set.called
    assert mock_pipeline.sadd.called
    assert mock_pipeline.expire.called

    # Verify execute was called (atomic execution)
    mock_pipeline.execute.assert_called_once()

    # Verify session was created
    assert session.user_id == 123
    assert session.username == "testuser"
    assert session.device_id == "device1"


@pytest.mark.asyncio
async def test_create_session_atomic_failure(session_manager, mock_redis_client):
    """Test that create_session failure is atomic (all-or-nothing)."""
    # Setup mock pipeline that fails during execute
    mock_pipeline = AsyncMock()
    mock_pipeline.set = MagicMock()
    mock_pipeline.sadd = MagicMock()
    mock_pipeline.expire = MagicMock()
    mock_pipeline.execute = AsyncMock(side_effect=Exception("Redis pipeline failed"))
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock(return_value=None)

    mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

    # Attempt to create session
    with pytest.raises(RuntimeError) as exc_info:
        await session_manager.create_session(
            user_id=123,
            username="testuser",
        )

    # Verify error message
    assert "Failed to create session" in str(exc_info.value)

    # Verify pipeline operations were called (but failed atomically)
    mock_pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_session_no_client_raises_error(session_manager):
    """Test that create_session raises error when Redis client not connected."""
    session_manager.redis.client = None

    with pytest.raises(RuntimeError) as exc_info:
        await session_manager.create_session(
            user_id=123,
            username="testuser",
        )

    assert "Redis client not connected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_delete_session_uses_pipeline(session_manager, mock_redis_client):
    """Test that delete_session uses Redis pipeline with transaction=True."""
    # Mock get_session to return valid session
    session_data = SessionData(
        session_id="test_session_123",
        user_id=123,
        username="testuser",
        expires_at=pendulum.now("UTC") + pendulum.duration(hours=1),
    )

    with patch.object(session_manager, "get_session", return_value=session_data):
        # Setup mock pipeline
        mock_pipeline = AsyncMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.srem = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[1, 1])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

        # Delete session
        result = await session_manager.delete_session("test_session_123")

        # Verify result
        assert result is True

        # Verify pipeline was used with transaction=True
        mock_redis_client.client.pipeline.assert_called_once_with(transaction=True)

        # Verify both operations were added to pipeline
        assert mock_pipeline.delete.called
        assert mock_pipeline.srem.called

        # Verify execute was called (atomic execution)
        mock_pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_session_atomic_failure(session_manager, mock_redis_client):
    """Test that delete_session failure is atomic (all-or-nothing)."""
    # Mock get_session to return valid session
    session_data = SessionData(
        session_id="test_session_456",
        user_id=456,
        username="testuser2",
        expires_at=pendulum.now("UTC") + pendulum.duration(hours=1),
    )

    with patch.object(session_manager, "get_session", return_value=session_data):
        # Setup mock pipeline that fails during execute
        mock_pipeline = AsyncMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.srem = MagicMock()
        mock_pipeline.execute = AsyncMock(side_effect=Exception("Redis pipeline failed"))
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

        # Attempt to delete session
        result = await session_manager.delete_session("test_session_456")

        # Verify deletion failed
        assert result is False

        # Verify pipeline operations were called (but failed atomically)
        mock_pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_session_no_partial_state(session_manager, mock_redis_client):
    """Test that delete_session doesn't leave partial state on failure."""
    session_data = SessionData(
        session_id="test_session_789",
        user_id=789,
        username="testuser3",
        expires_at=pendulum.now("UTC") + pendulum.duration(hours=1),
    )

    with patch.object(session_manager, "get_session", return_value=session_data):
        # Mock pipeline that records which operations were attempted
        operations_executed = []

        mock_pipeline = AsyncMock()

        def mock_delete(*args):
            operations_executed.append("delete")

        def mock_srem(*args):
            operations_executed.append("srem")

        mock_pipeline.delete = MagicMock(side_effect=mock_delete)
        mock_pipeline.srem = MagicMock(side_effect=mock_srem)

        # Fail during execute
        async def mock_execute():
            raise Exception("Pipeline execution failed")

        mock_pipeline.execute = AsyncMock(side_effect=mock_execute)
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

        # Attempt deletion
        result = await session_manager.delete_session("test_session_789")

        # Verify deletion failed
        assert result is False

        # Verify both operations were queued (but not executed due to pipeline failure)
        assert "delete" in operations_executed
        assert "srem" in operations_executed


@pytest.mark.asyncio
async def test_delete_nonexistent_session(session_manager, mock_redis_client):
    """Test that deleting nonexistent session returns False gracefully."""
    with patch.object(session_manager, "get_session", return_value=None):
        result = await session_manager.delete_session("nonexistent_session")
        assert result is False


@pytest.mark.asyncio
async def test_delete_session_no_client_returns_false(session_manager):
    """Test that delete_session returns False when Redis client not connected."""
    session_data = SessionData(
        session_id="test_session",
        user_id=123,
        username="testuser",
        expires_at=pendulum.now("UTC") + pendulum.duration(hours=1),
    )

    with patch.object(session_manager, "get_session", return_value=session_data):
        session_manager.redis.client = None
        result = await session_manager.delete_session("test_session")
        assert result is False


@pytest.mark.asyncio
async def test_create_session_all_operations_in_single_transaction(
    session_manager, mock_redis_client
):
    """Test that all three Redis operations for create_session are in a single transaction."""
    operations_order = []

    mock_pipeline = AsyncMock()

    def track_set(*args, **kwargs):
        operations_order.append("set")

    def track_sadd(*args):
        operations_order.append("sadd")

    def track_expire(*args):
        operations_order.append("expire")

    mock_pipeline.set = MagicMock(side_effect=track_set)
    mock_pipeline.sadd = MagicMock(side_effect=track_sadd)
    mock_pipeline.expire = MagicMock(side_effect=track_expire)
    mock_pipeline.execute = AsyncMock(return_value=[True, 1, True])
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock(return_value=None)

    mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

    await session_manager.create_session(
        user_id=123,
        username="testuser",
    )

    # Verify all three operations were queued before execute
    assert operations_order == ["set", "sadd", "expire"]
    mock_pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_session_both_operations_in_single_transaction(
    session_manager, mock_redis_client
):
    """Test that both Redis operations for delete_session are in a single transaction."""
    session_data = SessionData(
        session_id="test_session",
        user_id=123,
        username="testuser",
        expires_at=pendulum.now("UTC") + pendulum.duration(hours=1),
    )

    with patch.object(session_manager, "get_session", return_value=session_data):
        operations_order = []

        mock_pipeline = AsyncMock()

        def track_delete(*args):
            operations_order.append("delete")

        def track_srem(*args):
            operations_order.append("srem")

        mock_pipeline.delete = MagicMock(side_effect=track_delete)
        mock_pipeline.srem = MagicMock(side_effect=track_srem)
        mock_pipeline.execute = AsyncMock(return_value=[1, 1])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client.client.pipeline = MagicMock(return_value=mock_pipeline)

        await session_manager.delete_session("test_session")

        # Verify both operations were queued before execute
        assert operations_order == ["delete", "srem"]
        mock_pipeline.execute.assert_called_once()
