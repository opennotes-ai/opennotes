"""
Tests for task-797.07: Fix session pipeline partial state cleanup

This test verifies that when create_session's pipeline fails mid-way
(after some operations may have been partially committed), the
exception handler cleans up any orphaned keys.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.cache.session import SessionManager
from tests.redis_mock import StatefulRedisMock


class PartialFailurePipelineMock:
    """
    Mock pipeline that simulates partial state left behind after failure.

    This simulates a scenario where some data gets written to Redis
    before the pipeline execution fails (e.g., network error after
    partial commit, or non-atomic operations in some Redis configurations).
    """

    def __init__(
        self,
        redis_mock: StatefulRedisMock,
        session_key: str,
        user_sessions_key: str,
        session_id: str,
        serialized: bytes,
    ):
        self.redis_mock = redis_mock
        self.session_key = session_key
        self.user_sessions_key = user_sessions_key
        self.session_id = session_id
        self.serialized = serialized

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def set(self, key: str, value: bytes, ex: int | None = None):
        return self

    def sadd(self, key: str, *members):
        return self

    def expire(self, key: str, seconds: int):
        return self

    async def execute(self):
        """
        Simulate partial state being written before failure.

        In real scenarios, this can happen due to:
        - Network errors after partial batch execution
        - Redis server errors mid-execution
        - Non-atomic pipeline configurations
        """
        await self.redis_mock._set(self.session_key, self.serialized, ex=3600)
        await self.redis_mock._sadd(self.user_sessions_key, self.session_id)

        raise Exception("Pipeline execution failed mid-way")


@pytest.fixture
def stateful_redis_mock():
    """Create a stateful Redis mock that tracks actual state."""
    return StatefulRedisMock()


@pytest.fixture
def mock_redis_client(stateful_redis_mock):
    """Create a mock Redis client wrapper with the stateful mock."""
    client = MagicMock()
    client.client = stateful_redis_mock

    async def mock_delete(key: str) -> int:
        return await stateful_redis_mock._delete(key)

    client.delete = mock_delete
    return client


@pytest.fixture
def session_manager(mock_redis_client):
    """Create SessionManager with mock Redis client."""
    return SessionManager(mock_redis_client)


@pytest.mark.asyncio
async def test_create_session_cleans_up_partial_state_on_pipeline_failure(
    session_manager, mock_redis_client, stateful_redis_mock
):
    """
    Test that create_session cleans up partial state when pipeline fails.

    Scenario:
    1. Pipeline starts executing
    2. Some operations succeed (session key set, user sessions updated)
    3. Pipeline execute() raises exception
    4. Exception handler should clean up orphaned keys
    5. No partial state should remain in Redis
    """
    user_id = 123
    username = "testuser"

    session_id_holder = {}

    original_generate = session_manager._generate_session_id

    def capture_session_id():
        sid = original_generate()
        session_id_holder["session_id"] = sid
        return sid

    with patch.object(session_manager, "_generate_session_id", side_effect=capture_session_id):

        def create_failing_pipeline(transaction: bool = True):
            session_id = session_id_holder.get("session_id", "unknown")
            session_key = f"session:{session_id}"
            user_sessions_key = f"session:user:{user_id}:sessions"

            from datetime import UTC, datetime, timedelta

            from src.cache.models import SessionData
            from src.config import settings

            session_data = SessionData(
                session_id=session_id,
                user_id=user_id,
                username=username,
                device_id=None,
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.SESSION_TTL),
                metadata={},
            )
            serialized = session_data.model_dump_json().encode("utf-8")

            return PartialFailurePipelineMock(
                stateful_redis_mock,
                session_key,
                user_sessions_key,
                session_id,
                serialized,
            )

        stateful_redis_mock.pipeline = create_failing_pipeline

        with pytest.raises(RuntimeError) as exc_info:
            await session_manager.create_session(
                user_id=user_id,
                username=username,
            )

        assert "Failed to create session" in str(exc_info.value)

        session_id = session_id_holder["session_id"]
        session_key = f"session:{session_id}"
        user_sessions_key = f"session:user:{user_id}:sessions"

        session_key_exists = session_key in stateful_redis_mock.store
        user_sessions_key_exists = user_sessions_key in stateful_redis_mock.store

        assert not session_key_exists, (
            f"Session key {session_key} should have been cleaned up but still exists. "
            f"Current store keys: {list(stateful_redis_mock.store.keys())}"
        )
        assert not user_sessions_key_exists, (
            f"User sessions key {user_sessions_key} should have been cleaned up but still exists. "
            f"Current store keys: {list(stateful_redis_mock.store.keys())}"
        )


@pytest.mark.asyncio
async def test_create_session_cleanup_is_best_effort(
    session_manager, mock_redis_client, stateful_redis_mock
):
    """
    Test that cleanup failures don't mask the original error.

    Even if cleanup fails, the original pipeline failure error should
    be raised, not the cleanup error.
    """
    user_id = 456
    username = "testuser2"

    session_id_holder = {}

    original_generate = session_manager._generate_session_id

    def capture_session_id():
        sid = original_generate()
        session_id_holder["session_id"] = sid
        return sid

    with patch.object(session_manager, "_generate_session_id", side_effect=capture_session_id):

        def create_failing_pipeline(transaction: bool = True):
            session_id = session_id_holder.get("session_id", "unknown")
            session_key = f"session:{session_id}"
            user_sessions_key = f"session:user:{user_id}:sessions"

            from datetime import UTC, datetime, timedelta

            from src.cache.models import SessionData
            from src.config import settings

            session_data = SessionData(
                session_id=session_id,
                user_id=user_id,
                username=username,
                device_id=None,
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.SESSION_TTL),
                metadata={},
            )
            serialized = session_data.model_dump_json().encode("utf-8")

            return PartialFailurePipelineMock(
                stateful_redis_mock,
                session_key,
                user_sessions_key,
                session_id,
                serialized,
            )

        stateful_redis_mock.pipeline = create_failing_pipeline

        async def failing_delete(key: str) -> int:
            raise Exception("Cleanup also failed!")

        mock_redis_client.delete = failing_delete

        with pytest.raises(RuntimeError) as exc_info:
            await session_manager.create_session(
                user_id=user_id,
                username=username,
            )

        assert "Failed to create session" in str(exc_info.value)
        assert "Cleanup also failed" not in str(exc_info.value)
