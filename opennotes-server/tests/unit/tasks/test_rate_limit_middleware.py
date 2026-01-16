"""Unit tests for DistributedRateLimitMiddleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.rate_limit_middleware import (
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_NAME,
    DistributedRateLimitMiddleware,
)


class TestDistributedRateLimitMiddleware:
    """Tests for DistributedRateLimitMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        redis_url = "redis://localhost:6379"
        return DistributedRateLimitMiddleware(redis_url)

    @pytest.mark.asyncio
    async def test_pre_execute_acquires_semaphore_when_labels_present(self, middleware):
        """Middleware acquires semaphore when task has rate_limit_name label."""
        message = MagicMock()
        message.labels = {
            RATE_LIMIT_NAME: "import:fact_check",
            RATE_LIMIT_CAPACITY: "1",
            RATE_LIMIT_MAX_SLEEP: "30",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore):
            result = await middleware.pre_execute(message)

        assert result == message
        mock_semaphore.__aenter__.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_execute_skips_when_no_rate_limit_labels(self, middleware):
        """Middleware does nothing when task has no rate_limit_name label."""
        message = MagicMock()
        message.labels = {"component": "import_pipeline"}

        result = await middleware.pre_execute(message)

        assert result == message

    @pytest.mark.asyncio
    async def test_post_execute_releases_semaphore(self, middleware):
        """Middleware releases semaphore after task execution."""
        message = MagicMock()
        message.labels = {RATE_LIMIT_NAME: "test:lock"}
        result = {"status": "success"}

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)
        middleware._active_semaphores[id(message)] = mock_semaphore

        await middleware.post_execute(message, result)

        mock_semaphore.__aexit__.assert_called_once()
        assert id(message) not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_on_error_releases_semaphore(self, middleware):
        """Middleware releases semaphore on task error."""
        message = MagicMock()
        message.labels = {RATE_LIMIT_NAME: "test:lock"}
        error = ValueError("test error")

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)
        middleware._active_semaphores[id(message)] = mock_semaphore

        await middleware.on_error(message, error, error)

        mock_semaphore.__aexit__.assert_called_once()
