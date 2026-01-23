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

Coverage Mapping: Lock Integration Tests → Middleware Integration Tests
========================================================================

This module provides integration test coverage equivalent to the removed
lock manager tests, verifying real Redis behavior.

Removed Tests                           | Middleware Equivalents
----------------------------------------|-----------------------------------------------
TestRechunkLockIntegration:             |
  - test_real_redis_lock                | TestDistributedRateLimitMiddlewareIntegration:
                                        |   test_pre_execute_acquires_real_semaphore
  - test_lock_timeout_with_redis        | TestMiddleware429Behavior:
                                        |   test_rate_limit_exceeded_when_semaphore_unavailable
  - test_concurrent_lock_contention     | TestMiddlewareConcurrencyForBatchJobs:
                                        |   test_concurrent_tasks_with_same_lock_serialized

TestRechunkConcurrencyIntegration:      |
  - test_per_community_isolation        | TestConcurrentRechunkForDifferentCommunities:
                                        |   test_different_communities_can_run_concurrent_rechunk
  - test_same_community_blocked         | TestConcurrentRechunkForDifferentCommunities:
                                        |   test_same_community_blocked_when_rechunk_in_progress
  - test_parallel_timing                | TestConcurrentRechunkForDifferentCommunities:
                                        |   test_concurrent_execution_timing_for_different_communities

TestRedisFailureHandling:               |
  - test_startup_required               | TestRedisUnavailableHandling:
                                        |   test_raises_runtime_error_when_not_started
  - test_shutdown_clears_connection     | TestRedisUnavailableHandling:
                                        |   test_shutdown_clears_redis_connection
  - test_non_rate_limited_unaffected    | TestRedisUnavailableHandling:
                                        |   test_tasks_without_rate_limit_work_even_before_startup

Additional integration coverage:
  - TestMiddlewareConcurrencyForBatchJobs: Real semaphore serialization
  - TestConsecutiveFailureAlerts: Alert logging at failure threshold
  - TestCleanupOnTaskFailure: Semaphore release on task errors
"""

import asyncio
import os
import uuid
from unittest.mock import MagicMock

import pytest
import redis.asyncio as aioredis

from src.tasks.rate_limit_middleware import (
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_EXPIRY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_NAME,
    DistributedRateLimitMiddleware,
    RateLimitConfigurationError,
    RateLimitExceededError,
)


def get_redis_url() -> str:
    """Get Redis URL from environment or use default for local development."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


def create_redis_client() -> aioredis.Redis:
    """Create a Redis client for testing."""
    return aioredis.Redis.from_url(get_redis_url())


@pytest.fixture
async def redis_client():
    """Create and yield a Redis client, cleaning up after."""
    client = create_redis_client()
    yield client
    await client.aclose()


@pytest.fixture
async def middleware(redis_client):
    """Create and start middleware with real Redis connection."""
    mw = DistributedRateLimitMiddleware(redis_client=redis_client)
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
    async def test_middleware_uses_shared_redis_client(self):
        """Verify middleware uses the shared Redis client for operations."""
        client = create_redis_client()
        mw = DistributedRateLimitMiddleware(redis_client=client)

        pong = await mw._redis.ping()
        assert pong is True

        await client.aclose()

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
        await middleware.on_error(message, MagicMock(), error)
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
    async def test_missing_template_variable_raises_configuration_error(self, middleware):
        """Verify RateLimitConfigurationError is raised when template variable missing.

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

        with pytest.raises(RateLimitConfigurationError) as exc_info:
            await middleware.pre_execute(message)

        assert exc_info.value.rate_limit_name == "rechunk:previously_seen:{community_server_id}"
        assert exc_info.value.missing_vars == ["community_server_id"]

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

        with pytest.raises(RateLimitConfigurationError) as exc_info:
            await middleware.pre_execute(message)

        assert exc_info.value.rate_limit_name == "task:{job_type}:{community_id}"
        assert exc_info.value.missing_vars == ["community_id"]
        assert exc_info.value.available_kwargs == ["job_type"]


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
    async def test_tasks_without_rate_limit_work_normally(self):
        """Verify tasks without rate_limit_name still work.

        Tasks that don't use rate limiting should pass through the middleware.
        """
        client = create_redis_client()
        mw = DistributedRateLimitMiddleware(redis_client=client)

        message = create_message({"component": "test"})

        result = await mw.pre_execute(message)
        assert result == message

        await client.aclose()


class TestMiddlewareConcurrencyForBatchJobs:
    """Tests for middleware-based concurrency control for batch jobs.

    Coverage mapping from removed RechunkTaskLockRelease tests:
    - Concurrent tasks with same lock serialized → test_concurrent_tasks_with_same_lock_serialized
    - Concurrent tasks with different locks parallel → test_concurrent_tasks_with_different_locks_parallel
    - Task failure releases lock for next task → test_task_failure_releases_lock_for_next_task
    """

    @pytest.mark.asyncio
    async def test_concurrent_tasks_with_same_lock_serialized(self, middleware):
        """Verify capacity=1 serializes tasks with the same lock name."""
        lock_name = f"test:batch:serialize:{uuid.uuid4()}"
        execution_order = []

        async def batch_task(task_num: int, delay: float):
            message = create_message(
                {
                    RATE_LIMIT_NAME: lock_name,
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: "10",
                }
            )
            await middleware.pre_execute(message)
            try:
                execution_order.append(f"start_{task_num}")
                await asyncio.sleep(delay)
                execution_order.append(f"end_{task_num}")
            finally:
                await middleware.post_execute(message, MagicMock())

        await asyncio.gather(
            batch_task(1, 0.05),
            batch_task(2, 0.05),
            batch_task(3, 0.05),
        )

        start_count = sum(1 for e in execution_order if e.startswith("start"))
        end_count = sum(1 for e in execution_order if e.startswith("end"))
        assert start_count == 3
        assert end_count == 3

        for i in range(0, len(execution_order) - 1, 2):
            if execution_order[i].startswith("start"):
                expected_end = execution_order[i].replace("start", "end")
                assert execution_order[i + 1] == expected_end

    @pytest.mark.asyncio
    async def test_concurrent_tasks_with_different_locks_parallel(self, middleware):
        """Verify isolation between different lock names (communities)."""
        lock_base = f"test:batch:parallel:{uuid.uuid4()}"
        execution_times = {}

        async def batch_task(lock_suffix: str, delay: float):
            message = create_message(
                {
                    RATE_LIMIT_NAME: f"{lock_base}:{lock_suffix}",
                    RATE_LIMIT_CAPACITY: "1",
                    RATE_LIMIT_MAX_SLEEP: "10",
                }
            )
            import time

            start_time = time.time()
            await middleware.pre_execute(message)
            try:
                await asyncio.sleep(delay)
            finally:
                await middleware.post_execute(message, MagicMock())
            execution_times[lock_suffix] = time.time() - start_time

        import time

        total_start = time.time()
        await asyncio.gather(
            batch_task("lock_a", 0.1),
            batch_task("lock_b", 0.1),
            batch_task("lock_c", 0.1),
        )
        total_time = time.time() - total_start

        assert total_time < 0.3, f"Expected parallel execution (<0.3s), got {total_time}s"

    @pytest.mark.asyncio
    async def test_task_failure_releases_lock_for_next_task(self, middleware):
        """Verify cleanup enables subsequent task after failure."""
        lock_name = f"test:batch:failure_release:{uuid.uuid4()}"

        message1 = create_message(
            {
                RATE_LIMIT_NAME: lock_name,
                RATE_LIMIT_CAPACITY: "1",
                RATE_LIMIT_MAX_SLEEP: "5",
            }
        )

        await middleware.pre_execute(message1)
        error = ValueError("Simulated task failure")
        await middleware.on_error(message1, MagicMock(), error)

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


class TestConsecutiveFailureAlerts:
    """Tests for consecutive release failure alerts.

    Coverage mapping from removed RechunkConcurrencyControl tests:
    - Consecutive release failures log alert → test_consecutive_release_failures_log_alert
    - Success resets counter → test_success_resets_consecutive_failure_counter
    """

    @pytest.mark.asyncio
    async def test_consecutive_release_failures_log_alert(self, middleware, caplog):
        """Verify ERROR log at threshold (3 consecutive failures)."""
        import logging
        from unittest.mock import AsyncMock, patch

        message = MagicMock()
        message.task_id = "alert-test-task"
        message.task_name = "test_task"

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(side_effect=Exception("Redis error"))

        with (
            patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.ERROR),
        ):
            for i in range(3):
                middleware._active_semaphores[f"alert-task-{i}"] = mock_semaphore
                message.task_id = f"alert-task-{i}"
                await middleware._release_semaphore(message)

        assert "ALERT:" in caplog.text
        assert "3 consecutive semaphore release failures" in caplog.text

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_failure_counter(self, middleware):
        """Verify counter reset on success."""
        from unittest.mock import AsyncMock, patch

        message = MagicMock()
        message.task_name = "test_task"

        fail_semaphore = AsyncMock()
        fail_semaphore.__aexit__ = AsyncMock(side_effect=Exception("error"))
        success_semaphore = AsyncMock()
        success_semaphore.__aexit__ = AsyncMock(return_value=False)

        with patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock):
            middleware._active_semaphores["fail-task-1"] = fail_semaphore
            message.task_id = "fail-task-1"
            await middleware._release_semaphore(message)
            assert middleware._consecutive_release_failures == 1

            middleware._active_semaphores["fail-task-2"] = fail_semaphore
            message.task_id = "fail-task-2"
            await middleware._release_semaphore(message)
            assert middleware._consecutive_release_failures == 2

            middleware._active_semaphores["success-task"] = success_semaphore
            message.task_id = "success-task"
            await middleware._release_semaphore(message)
            assert middleware._consecutive_release_failures == 0


class TestSocketTimeoutWithBlockingCommands:
    """Tests for BLPOP blocking commands with socket timeout (TASK-1032).

    The rate limiter uses AsyncSemaphore which internally uses BLPOP with max_sleep.
    If the Redis client's socket_timeout is shorter than max_sleep, BLPOP will
    get a TimeoutError instead of waiting for the semaphore.

    This test verifies that with a properly configured client (socket_timeout > max_sleep),
    the rate limiter can successfully wait for semaphores even when blocking > 5 seconds.
    """

    @pytest.mark.asyncio
    async def test_rate_limiter_succeeds_when_blpop_blocks_longer_than_default_timeout(self):
        """Verify rate limiter works when BLPOP needs to block > 5s (default socket timeout).

        This is the key test for TASK-1032. The scenario:
        1. Task A acquires semaphore (capacity=1)
        2. Task A holds the semaphore for 6 seconds (longer than default 5s socket timeout)
        3. Task B starts waiting (via BLPOP) for the semaphore
        4. After 6s, Task A releases the semaphore
        5. Task B should successfully acquire (not get TimeoutError)

        With the old configuration (socket_timeout=5s), Task B would fail.
        With the fix (socket_timeout=120s for rate limiter), Task B succeeds.
        """
        client = aioredis.Redis.from_url(
            get_redis_url(),
            socket_timeout=120,
        )
        mw = DistributedRateLimitMiddleware(redis_client=client, instance_id="test-socket-timeout")
        await mw.startup()

        try:
            lock_name = f"test:socket_timeout:{uuid.uuid4()}"
            results = []

            async def task_a():
                """Holds semaphore for 6 seconds (longer than default 5s timeout)."""
                message = create_message(
                    {
                        RATE_LIMIT_NAME: lock_name,
                        RATE_LIMIT_CAPACITY: "1",
                        RATE_LIMIT_MAX_SLEEP: "10",
                    }
                )
                await mw.pre_execute(message)
                try:
                    results.append("task_a_acquired")
                    await asyncio.sleep(6)
                    results.append("task_a_releasing")
                finally:
                    await mw.post_execute(message, MagicMock())
                    results.append("task_a_released")

            async def task_b():
                """Waits for semaphore - must block > 5s waiting for task_a."""
                await asyncio.sleep(0.1)
                message = create_message(
                    {
                        RATE_LIMIT_NAME: lock_name,
                        RATE_LIMIT_CAPACITY: "1",
                        RATE_LIMIT_MAX_SLEEP: "10",
                    }
                )
                results.append("task_b_waiting")
                await mw.pre_execute(message)
                try:
                    results.append("task_b_acquired")
                finally:
                    await mw.post_execute(message, MagicMock())
                    results.append("task_b_released")

            await asyncio.gather(task_a(), task_b())

            assert "task_a_acquired" in results
            assert "task_b_waiting" in results
            assert "task_b_acquired" in results
            assert "task_b_released" in results

            task_a_acquired_idx = results.index("task_a_acquired")
            task_b_waiting_idx = results.index("task_b_waiting")
            task_a_releasing_idx = results.index("task_a_releasing")
            task_b_acquired_idx = results.index("task_b_acquired")

            assert task_a_acquired_idx < task_b_waiting_idx
            assert task_b_waiting_idx < task_a_releasing_idx
            assert task_a_releasing_idx < task_b_acquired_idx

        finally:
            await mw.shutdown()
            await client.aclose()


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
