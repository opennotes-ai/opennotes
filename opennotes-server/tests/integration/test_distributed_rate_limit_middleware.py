"""Integration tests for DistributedRateLimitMiddleware with real Redis.

Tests the middleware's integration with Redis and AsyncSemaphore,
verifying actual rate limiting behavior (not mocked).
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.tasks.rate_limit_middleware import (
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_EXPIRY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_NAME,
    DistributedRateLimitMiddleware,
)


@pytest.fixture
async def middleware():
    """Create and start middleware with real Redis connection."""
    mw = DistributedRateLimitMiddleware("redis://localhost:6379")
    await mw.startup()
    yield mw
    await mw.shutdown()


def create_message(labels: dict) -> MagicMock:
    """Create a mock TaskiqMessage with the given labels."""
    message = MagicMock()
    message.labels = labels
    message.task_name = "test_task"
    return message


class TestDistributedRateLimitMiddlewareIntegration:
    """Integration tests for DistributedRateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_startup_creates_redis_connection(self):
        """Verify startup creates a working Redis connection."""
        mw = DistributedRateLimitMiddleware("redis://localhost:6379")
        assert mw._redis is None

        await mw.startup()
        assert mw._redis is not None

        pong = await mw._redis.ping()
        assert pong is True

        await mw.shutdown()
        assert mw._redis is None

    @pytest.mark.asyncio
    async def test_get_semaphore_creates_real_semaphore(self, middleware):
        """Verify _get_semaphore creates a working AsyncSemaphore."""
        semaphore = middleware._get_semaphore(
            name="test:integration:semaphore",
            capacity=1,
            max_sleep=5,
            expiry=30,
        )

        async with semaphore:
            pass

    @pytest.mark.asyncio
    async def test_get_semaphore_raises_before_startup(self):
        """Verify _get_semaphore raises if middleware not started."""
        mw = DistributedRateLimitMiddleware("redis://localhost:6379")

        with pytest.raises(RuntimeError, match="Middleware not started"):
            mw._get_semaphore(name="test:error", capacity=1)

    @pytest.mark.asyncio
    async def test_pre_execute_acquires_real_semaphore(self, middleware):
        """Verify pre_execute actually acquires a semaphore."""
        message = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:pre_execute",
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            }
        )

        result = await middleware.pre_execute(message)
        assert result == message
        assert id(message) in middleware._active_semaphores

        await middleware.post_execute(message, MagicMock())
        assert id(message) not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_post_execute_releases_semaphore(self, middleware):
        """Verify post_execute releases the semaphore."""
        message = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:post_execute",
                RATE_LIMIT_CAPACITY: "1",
            }
        )

        await middleware.pre_execute(message)
        assert id(message) in middleware._active_semaphores

        await middleware.post_execute(message, MagicMock())
        assert id(message) not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_on_error_releases_semaphore(self, middleware):
        """Verify on_error releases the semaphore."""
        message = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:on_error",
                RATE_LIMIT_CAPACITY: "1",
            }
        )

        await middleware.pre_execute(message)
        assert id(message) in middleware._active_semaphores

        error = ValueError("test error")
        await middleware.on_error(message, error, error)
        assert id(message) not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_rate_limiting_actually_limits_concurrency(self, middleware):
        """Verify rate limiting actually prevents concurrent execution."""
        concurrent_count = [0]
        max_concurrent = [0]
        results = []

        async def simulated_task(task_id: int):
            message = create_message(
                {
                    RATE_LIMIT_NAME: "test:integration:concurrency",
                    RATE_LIMIT_CAPACITY: "2",
                    RATE_LIMIT_MAX_SLEEP: "10",
                }
            )

            await middleware.pre_execute(message)
            try:
                concurrent_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
                results.append(f"start_{task_id}")
                await asyncio.sleep(0.05)
                results.append(f"end_{task_id}")
                concurrent_count[0] -= 1
            finally:
                await middleware.post_execute(message, MagicMock())

        await asyncio.gather(*[simulated_task(i) for i in range(6)])

        assert max_concurrent[0] == 2, f"Expected max 2 concurrent, got {max_concurrent[0]}"
        assert len(results) == 12

    @pytest.mark.asyncio
    async def test_different_rate_limit_names_are_independent(self, middleware):
        """Verify different rate_limit_names don't block each other."""
        results = []

        async def task_a():
            message = create_message(
                {
                    RATE_LIMIT_NAME: "test:integration:name_a",
                    RATE_LIMIT_CAPACITY: "1",
                }
            )
            await middleware.pre_execute(message)
            try:
                results.append("a_start")
                await asyncio.sleep(0.1)
                results.append("a_end")
            finally:
                await middleware.post_execute(message, MagicMock())

        async def task_b():
            message = create_message(
                {
                    RATE_LIMIT_NAME: "test:integration:name_b",
                    RATE_LIMIT_CAPACITY: "1",
                }
            )
            await middleware.pre_execute(message)
            try:
                results.append("b_start")
                await asyncio.sleep(0.05)
                results.append("b_end")
            finally:
                await middleware.post_execute(message, MagicMock())

        await asyncio.gather(task_a(), task_b())

        assert results[0] in ("a_start", "b_start")
        assert results[1] in ("a_start", "b_start")
        assert results[0] != results[1]

    @pytest.mark.asyncio
    async def test_label_parsing_uses_correct_defaults(self, middleware):
        """Verify label parsing uses defaults when values not provided."""
        message = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:defaults",
            }
        )

        await middleware.pre_execute(message)
        try:
            semaphore = middleware._active_semaphores[id(message)]
            assert semaphore is not None
        finally:
            await middleware.post_execute(message, MagicMock())

    @pytest.mark.asyncio
    async def test_no_labels_skips_rate_limiting(self, middleware):
        """Verify tasks without rate_limit_name skip rate limiting."""
        message = create_message({"component": "test"})

        result = await middleware.pre_execute(message)
        assert result == message
        assert id(message) not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_custom_expiry_label(self, middleware):
        """Verify custom expiry label is respected."""
        message = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:expiry",
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_EXPIRY: "60",
            }
        )

        await middleware.pre_execute(message)
        try:
            assert id(message) in middleware._active_semaphores
        finally:
            await middleware.post_execute(message, MagicMock())

    @pytest.mark.asyncio
    async def test_multiple_messages_tracked_separately(self, middleware):
        """Verify multiple concurrent messages are tracked independently."""
        message1 = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:multi1",
                RATE_LIMIT_CAPACITY: "2",
            }
        )
        message2 = create_message(
            {
                RATE_LIMIT_NAME: "test:integration:multi2",
                RATE_LIMIT_CAPACITY: "2",
            }
        )

        await middleware.pre_execute(message1)
        await middleware.pre_execute(message2)

        assert id(message1) in middleware._active_semaphores
        assert id(message2) in middleware._active_semaphores
        assert id(message1) != id(message2)

        await middleware.post_execute(message1, MagicMock())
        assert id(message1) not in middleware._active_semaphores
        assert id(message2) in middleware._active_semaphores

        await middleware.post_execute(message2, MagicMock())
        assert id(message2) not in middleware._active_semaphores
