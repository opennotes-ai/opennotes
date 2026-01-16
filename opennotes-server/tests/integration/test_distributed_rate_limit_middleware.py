"""Integration tests for DistributedRateLimitMiddleware with real Redis.

Tests the middleware's integration with Redis and AsyncSemaphore,
verifying actual rate limiting behavior (not mocked).

Test coverage includes:
- Basic semaphore acquisition and release
- Concurrent execution limits
- 429 behavior when job already in progress (MaxSleepExceededError -> RateLimitExceededError)
- Different communities can run concurrent rechunk jobs
- Graceful handling when Redis unavailable
- Proper cleanup when task fails
"""

import asyncio
import os
import uuid
from unittest.mock import MagicMock

import pytest

from src.tasks.rate_limit_middleware import (
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_EXPIRY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_NAME,
    DistributedRateLimitMiddleware,
    RateLimitExceededError,
)


def get_redis_url() -> str:
    """Get Redis URL from environment or use default for local development."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@pytest.fixture
async def middleware():
    """Create and start middleware with real Redis connection."""
    mw = DistributedRateLimitMiddleware(get_redis_url())
    await mw.startup()
    yield mw
    await mw.shutdown()


def create_message(
    labels: dict, task_id: str | None = None, kwargs: dict | None = None
) -> MagicMock:
    """Create a mock TaskiqMessage with the given labels.

    Args:
        labels: Task labels including rate_limit_name, capacity, etc.
        task_id: Unique task identifier (auto-generated if not provided)
        kwargs: Task kwargs for template variable substitution in rate_limit_name
    """
    message = MagicMock()
    message.labels = labels
    message.task_name = "test_task"
    message.task_id = task_id or str(uuid.uuid4())
    message.kwargs = kwargs or {}
    return message


class TestDistributedRateLimitMiddlewareIntegration:
    """Integration tests for DistributedRateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_startup_creates_redis_connection(self):
        """Verify startup creates a working Redis connection."""
        mw = DistributedRateLimitMiddleware(get_redis_url())
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
        mw = DistributedRateLimitMiddleware(get_redis_url())

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
        assert message.task_id in middleware._active_semaphores

        await middleware.post_execute(message, MagicMock())
        assert message.task_id not in middleware._active_semaphores

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
        assert message.task_id in middleware._active_semaphores

        await middleware.post_execute(message, MagicMock())
        assert message.task_id not in middleware._active_semaphores

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
        assert message.task_id in middleware._active_semaphores

        error = ValueError("test error")
        await middleware.on_error(message, error, error)
        assert message.task_id not in middleware._active_semaphores

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
            semaphore = middleware._active_semaphores[message.task_id]
            assert semaphore is not None
        finally:
            await middleware.post_execute(message, MagicMock())

    @pytest.mark.asyncio
    async def test_no_labels_skips_rate_limiting(self, middleware):
        """Verify tasks without rate_limit_name skip rate limiting."""
        message = create_message({"component": "test"})

        result = await middleware.pre_execute(message)
        assert result == message
        assert message.task_id not in middleware._active_semaphores

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
            assert message.task_id in middleware._active_semaphores
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

        assert message1.task_id in middleware._active_semaphores
        assert message2.task_id in middleware._active_semaphores
        assert message1.task_id != message2.task_id

        await middleware.post_execute(message1, MagicMock())
        assert message1.task_id not in middleware._active_semaphores
        assert message2.task_id in middleware._active_semaphores

        await middleware.post_execute(message2, MagicMock())
        assert message2.task_id not in middleware._active_semaphores


class TestMiddleware429Behavior:
    """Tests for 429 response when rechunk job is already in progress (AC#1).

    When a task cannot acquire the semaphore within max_sleep time,
    RateLimitExceededError is raised, which should result in 429 at API level.
    """

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_when_semaphore_unavailable(self, middleware):
        """Verify RateLimitExceededError is raised when semaphore cannot be acquired.

        This simulates the 429 scenario:
        1. First task acquires the semaphore (capacity=1)
        2. Second task tries to acquire but cannot within max_sleep
        3. RateLimitExceededError is raised (which API converts to 429)
        """
        lock_name = f"test:429:exceeded:{uuid.uuid4()}"

        message1 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "1",
            }
        )

        await middleware.pre_execute(message1)

        try:
            message2 = create_message(
                {
                    RATE_LIMIT_NAME: lock_name,
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: "1",
                }
            )

            with pytest.raises(RateLimitExceededError) as exc_info:
                await middleware.pre_execute(message2)

            assert lock_name in str(exc_info.value)
            assert "1s" in str(exc_info.value)
        finally:
            await middleware.post_execute(message1, MagicMock())

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_contains_lock_name_and_timeout(self, middleware):
        """Verify RateLimitExceededError has correct attributes."""
        lock_name = f"test:429:attributes:{uuid.uuid4()}"
        max_sleep = 1

        message1 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: str(max_sleep),
            }
        )

        await middleware.pre_execute(message1)

        try:
            message2 = create_message(
                {
                    RATE_LIMIT_NAME: lock_name,
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: str(max_sleep),
                }
            )

            with pytest.raises(RateLimitExceededError) as exc_info:
                await middleware.pre_execute(message2)

            assert exc_info.value.rate_limit_name == lock_name
            assert exc_info.value.max_sleep == max_sleep
        finally:
            await middleware.post_execute(message1, MagicMock())

    @pytest.mark.asyncio
    async def test_second_task_succeeds_after_first_releases(self, middleware):
        """Verify second task can acquire semaphore after first releases it.

        This ensures the 429 is temporary and new requests succeed after job completes.
        """
        lock_name = f"test:429:release:{uuid.uuid4()}"

        message1 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            }
        )

        await middleware.pre_execute(message1)
        await middleware.post_execute(message1, MagicMock())

        message2 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            }
        )

        await middleware.pre_execute(message2)
        assert message2.task_id in middleware._active_semaphores

        await middleware.post_execute(message2, MagicMock())


class TestTemplateVariableFailFast:
    """Tests for fail-fast behavior when template variables are missing."""

    @pytest.mark.asyncio
    async def test_missing_template_variable_raises_error_immediately(self, middleware):
        """Verify RateLimitExceededError is raised immediately when template variable missing.

        This ensures fail-fast behavior: tasks with missing template variables
        fail immediately rather than continuing with un-interpolated lock names.
        """
        message = create_message(
            {
                RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "30",
            },
            kwargs={},
        )

        with pytest.raises(RateLimitExceededError) as exc_info:
            await middleware.pre_execute(message)

        assert exc_info.value.rate_limit_name == "rechunk:previously_seen:{community_server_id}"
        assert exc_info.value.max_sleep == 0

    @pytest.mark.asyncio
    async def test_missing_one_of_multiple_template_variables_raises_error(self, middleware):
        """Verify error when any one of multiple template variables is missing."""
        message = create_message(
            {
                RATE_LIMIT_NAME: "task:{job_type}:{community_id}",
                RATE_LIMIT_CAPACITY: "1",
            },
            kwargs={"job_type": "rechunk"},
        )

        with pytest.raises(RateLimitExceededError) as exc_info:
            await middleware.pre_execute(message)

        assert exc_info.value.rate_limit_name == "task:{job_type}:{community_id}"
        assert exc_info.value.max_sleep == 0


class TestConcurrentRechunkForDifferentCommunities:
    """Tests for concurrent rechunk for different communities (AC#2).

    Previously seen rechunk uses rate_limit_name="rechunk:previously_seen:{community_server_id}"
    which means different communities should be able to run rechunk concurrently.
    """

    @pytest.mark.asyncio
    async def test_different_communities_can_run_concurrent_rechunk(self, middleware):
        """Verify different community_server_ids can acquire semaphores concurrently.

        This simulates the real rechunk scenario where:
        - Community A starts rechunk (acquires rechunk:previously_seen:community_a)
        - Community B starts rechunk (acquires rechunk:previously_seen:community_b)
        - Both should run concurrently without blocking each other
        """
        community_a = str(uuid.uuid4())
        community_b = str(uuid.uuid4())

        message_a = create_message(
            {
                RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            },
            kwargs={"community_server_id": community_a},
        )

        message_b = create_message(
            {
                RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            },
            kwargs={"community_server_id": community_b},
        )

        await middleware.pre_execute(message_a)
        await middleware.pre_execute(message_b)

        assert message_a.task_id in middleware._active_semaphores
        assert message_b.task_id in middleware._active_semaphores

        await middleware.post_execute(message_a, MagicMock())
        await middleware.post_execute(message_b, MagicMock())

    @pytest.mark.asyncio
    async def test_same_community_blocked_when_rechunk_in_progress(self, middleware):
        """Verify same community_server_id cannot run concurrent rechunk.

        If community A has rechunk in progress, another rechunk for community A
        should be blocked (get 429 after max_sleep).
        """
        community_id = str(uuid.uuid4())
        lock_name = f"rechunk:previously_seen:{community_id}"

        message1 = create_message(
            {
                RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "1",
            },
            kwargs={"community_server_id": community_id},
        )

        await middleware.pre_execute(message1)

        try:
            message2 = create_message(
                {
                    RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: "1",
                },
                kwargs={"community_server_id": community_id},
            )

            with pytest.raises(RateLimitExceededError) as exc_info:
                await middleware.pre_execute(message2)

            assert lock_name in str(exc_info.value)
        finally:
            await middleware.post_execute(message1, MagicMock())

    @pytest.mark.asyncio
    async def test_concurrent_execution_timing_for_different_communities(self, middleware):
        """Verify different communities actually run concurrently (not sequentially)."""
        community_a = str(uuid.uuid4())
        community_b = str(uuid.uuid4())
        results = []

        async def rechunk_task(community_id: str, duration: float):
            message = create_message(
                {
                    RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: "10",
                },
                kwargs={"community_server_id": community_id},
            )

            await middleware.pre_execute(message)
            try:
                results.append(f"{community_id[:8]}_start")
                await asyncio.sleep(duration)
                results.append(f"{community_id[:8]}_end")
            finally:
                await middleware.post_execute(message, MagicMock())

        await asyncio.gather(
            rechunk_task(community_a, 0.1),
            rechunk_task(community_b, 0.05),
        )

        assert results[0] in (f"{community_a[:8]}_start", f"{community_b[:8]}_start")
        assert results[1] in (f"{community_a[:8]}_start", f"{community_b[:8]}_start")
        assert results[0] != results[1]


class TestRedisUnavailableHandling:
    """Tests for graceful handling when Redis unavailable (AC#3)."""

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_not_started(self):
        """Verify RuntimeError is raised when middleware not started."""
        mw = DistributedRateLimitMiddleware(get_redis_url())

        message = create_message(
            {
                RATE_LIMIT_NAME: "test:redis:unavailable",
                RATE_LIMIT_CAPACITY: "1",
            }
        )

        with pytest.raises(RuntimeError, match="Middleware not started"):
            await mw.pre_execute(message)

    @pytest.mark.asyncio
    async def test_shutdown_clears_redis_connection(self):
        """Verify shutdown properly clears Redis connection."""
        mw = DistributedRateLimitMiddleware(get_redis_url())
        await mw.startup()

        assert mw._redis is not None

        await mw.shutdown()

        assert mw._redis is None

        message = create_message(
            {
                RATE_LIMIT_NAME: "test:redis:after_shutdown",
                RATE_LIMIT_CAPACITY: "1",
            }
        )

        with pytest.raises(RuntimeError, match="Middleware not started"):
            await mw.pre_execute(message)

    @pytest.mark.asyncio
    async def test_tasks_without_rate_limit_work_even_before_startup(self):
        """Verify tasks without rate_limit_name still work when Redis unavailable.

        Tasks that don't use rate limiting should not be affected by Redis availability.
        """
        mw = DistributedRateLimitMiddleware(get_redis_url())

        message = create_message({"component": "test"})

        result = await mw.pre_execute(message)
        assert result == message


class TestCleanupOnTaskFailure:
    """Tests for proper cleanup when task dispatch fails (AC#4)."""

    @pytest.mark.asyncio
    async def test_on_error_releases_semaphore_on_task_failure(self, middleware):
        """Verify semaphore is released when task fails via on_error callback."""
        lock_name = f"test:cleanup:on_error:{uuid.uuid4()}"

        message = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            }
        )

        await middleware.pre_execute(message)
        assert message.task_id in middleware._active_semaphores

        error = Exception("Task execution failed")
        mock_result = MagicMock()
        await middleware.on_error(message, mock_result, error)

        assert message.task_id not in middleware._active_semaphores

        message2 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "2",
            }
        )
        await middleware.pre_execute(message2)
        assert message2.task_id in middleware._active_semaphores
        await middleware.post_execute(message2, MagicMock())

    @pytest.mark.asyncio
    async def test_cleanup_allows_subsequent_task_to_acquire_semaphore(self, middleware):
        """Verify after cleanup, new task can immediately acquire semaphore."""
        lock_name = f"test:cleanup:subsequent:{uuid.uuid4()}"

        message1 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
            }
        )

        await middleware.pre_execute(message1)
        await middleware.post_execute(message1, MagicMock())

        message2 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "1",
            }
        )

        await middleware.pre_execute(message2)
        assert message2.task_id in middleware._active_semaphores
        await middleware.post_execute(message2, MagicMock())

    @pytest.mark.asyncio
    async def test_semaphore_not_tracked_when_pre_execute_fails(self, middleware):
        """Verify semaphore is not left tracked when pre_execute fails."""
        lock_name = f"test:cleanup:preexec_fail:{uuid.uuid4()}"

        message1 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "1",
            }
        )
        await middleware.pre_execute(message1)

        try:
            message2 = create_message(
                {
                    RATE_LIMIT_NAME: lock_name,
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: "1",
                }
            )

            with pytest.raises(RateLimitExceededError):
                await middleware.pre_execute(message2)

            assert message2.task_id not in middleware._active_semaphores
        finally:
            await middleware.post_execute(message1, MagicMock())

    @pytest.mark.asyncio
    async def test_post_execute_is_idempotent(self, middleware):
        """Verify calling post_execute multiple times doesn't cause errors."""
        lock_name = f"test:cleanup:idempotent:{uuid.uuid4()}"

        message = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
            }
        )

        await middleware.pre_execute(message)

        await middleware.post_execute(message, MagicMock())

        await middleware.post_execute(message, MagicMock())
        await middleware.post_execute(message, MagicMock())
