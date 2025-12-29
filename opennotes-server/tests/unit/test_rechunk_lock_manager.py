"""
Unit tests for RechunkLockManager.

Task: task-871.20 - Add rate limiting and concurrency control for rechunk endpoints
"""

from unittest.mock import AsyncMock

import pytest

from src.fact_checking.rechunk_lock import RECHUNK_LOCK_PREFIX, RechunkLockManager


class TestRechunkLockManager:
    """Unit tests for the RechunkLockManager class."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self):
        """Successfully acquire a lock when none exists."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.acquire_lock("test_operation")

        assert result is True
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"{RECHUNK_LOCK_PREFIX}:test_operation"
        assert call_args[0][1] == "locked"
        assert call_args[1]["nx"] is True
        assert "ex" in call_args[1]

    @pytest.mark.asyncio
    async def test_acquire_lock_with_resource_id(self):
        """Lock key includes resource_id when provided."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        manager = RechunkLockManager(redis=mock_redis)
        await manager.acquire_lock("test_operation", "resource_123")

        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"{RECHUNK_LOCK_PREFIX}:test_operation:resource_123"

    @pytest.mark.asyncio
    async def test_acquire_lock_fails_when_locked(self):
        """Returns False when lock already exists."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.acquire_lock("test_operation")

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_lock_allows_operation_without_redis(self):
        """When Redis is not available, allow the operation."""
        manager = RechunkLockManager(redis=None)
        result = await manager.acquire_lock("test_operation")

        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_lock_handles_exception(self):
        """On Redis exception, allow operation gracefully."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Redis error"))

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.acquire_lock("test_operation")

        assert result is True

    @pytest.mark.asyncio
    async def test_release_lock_success(self):
        """Successfully release a lock."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.release_lock("test_operation")

        assert result is True
        mock_redis.delete.assert_called_once_with(f"{RECHUNK_LOCK_PREFIX}:test_operation")

    @pytest.mark.asyncio
    async def test_release_lock_with_resource_id(self):
        """Release lock key includes resource_id when provided."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        manager = RechunkLockManager(redis=mock_redis)
        await manager.release_lock("test_operation", "resource_123")

        mock_redis.delete.assert_called_once_with(
            f"{RECHUNK_LOCK_PREFIX}:test_operation:resource_123"
        )

    @pytest.mark.asyncio
    async def test_release_lock_no_redis(self):
        """When Redis is not available, return True."""
        manager = RechunkLockManager(redis=None)
        result = await manager.release_lock("test_operation")

        assert result is True

    @pytest.mark.asyncio
    async def test_release_lock_handles_exception(self):
        """On Redis exception, return False gracefully."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis error"))

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.release_lock("test_operation")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_locked_true(self):
        """Returns True when lock exists."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.is_locked("test_operation")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_locked_false(self):
        """Returns False when lock does not exist."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.is_locked("test_operation")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_locked_no_redis(self):
        """When Redis is not available, return False."""
        manager = RechunkLockManager(redis=None)
        result = await manager.is_locked("test_operation")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_locked_handles_exception(self):
        """On Redis exception, return False gracefully."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis error"))

        manager = RechunkLockManager(redis=mock_redis)
        result = await manager.is_locked("test_operation")

        assert result is False

    @pytest.mark.asyncio
    async def test_custom_ttl(self):
        """Custom TTL is passed to Redis SET."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        manager = RechunkLockManager(redis=mock_redis)
        await manager.acquire_lock("test_operation", ttl=7200)

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 7200

    def test_get_lock_key_without_resource(self):
        """Lock key generation without resource_id."""
        manager = RechunkLockManager()
        key = manager._get_lock_key("fact_check")
        assert key == f"{RECHUNK_LOCK_PREFIX}:fact_check"

    def test_get_lock_key_with_resource(self):
        """Lock key generation with resource_id."""
        manager = RechunkLockManager()
        key = manager._get_lock_key("previously_seen", "community_123")
        assert key == f"{RECHUNK_LOCK_PREFIX}:previously_seen:community_123"

    @pytest.mark.asyncio
    async def test_redis_property_returns_injected_redis(self):
        """Redis property returns injected Redis client."""
        mock_redis = AsyncMock()
        manager = RechunkLockManager(redis=mock_redis)
        assert manager.redis is mock_redis

    @pytest.mark.asyncio
    async def test_redis_property_returns_none_when_not_injected(self):
        """Redis property returns None when not injected (no global fallback in base class)."""
        manager = RechunkLockManager(redis=None)
        assert manager.redis is None
