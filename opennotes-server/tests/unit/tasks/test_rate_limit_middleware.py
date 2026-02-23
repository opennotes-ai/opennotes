"""Unit tests for DistributedRateLimitMiddleware.

Coverage Mapping: Lock Manager Tests → Middleware Tests
=========================================================

This module provides equivalent test coverage for the removed RechunkLockManager
and related lock test classes. The lock management was consolidated into the
DistributedRateLimitMiddleware, and these tests verify the middleware provides
equivalent functionality.

Removed Tests                           | Middleware Equivalents
----------------------------------------|-----------------------------------------------
TestRechunkLockManager:                 |
  - test_lock_acquire_success           | TestDistributedRateLimitMiddleware:
                                        |   test_pre_execute_acquires_semaphore_when_labels_present
  - test_lock_acquire_with_resource_id  | TestRateLimitNameTemplateInterpolation:
                                        |   test_template_variable_is_interpolated_from_kwargs
  - test_lock_timeout                   | TestMiddlewareBasedLockRelease:
                                        |   test_semaphore_not_leaked_on_pre_execute_timeout
  - test_lock_release_success           | TestDistributedRateLimitMiddleware:
                                        |   test_post_execute_releases_semaphore
  - test_lock_release_on_error          | TestDistributedRateLimitMiddleware:
                                        |   test_on_error_releases_semaphore
  - test_graceful_redis_failure         | Integration: TestRedisUnavailableHandling

TestRechunkTaskLockRelease:             |
  - test_lock_released_on_success       | TestMiddlewareBasedLockRelease:
                                        |   test_semaphore_released_on_success_path
  - test_lock_released_on_failure       | TestMiddlewareBasedLockRelease:
                                        |   test_semaphore_released_on_error_path

TestRechunkConcurrencyControl:          |
  - test_concurrent_tasks_serialized    | Integration: TestMiddlewareConcurrencyForBatchJobs:
                                        |   test_concurrent_tasks_with_same_lock_serialized
  - test_different_resources_parallel   | Integration: TestMiddlewareConcurrencyForBatchJobs:
                                        |   test_concurrent_tasks_with_different_locks_parallel
  - test_failure_releases_for_next      | Integration: TestMiddlewareConcurrencyForBatchJobs:
                                        |   test_task_failure_releases_lock_for_next_task

TestRechunkKiqFailure:                  |
  - test_kiq_failure_cleanup            | N/A - kiq-specific retry behavior not replicated
                                        |   (middleware handles semaphore cleanup via on_error)

Additional coverage provided by middleware tests:
  - Template variable validation (fail-fast on missing kwargs)
  - Expiry label propagation to AsyncSemaphore
  - Semaphore leak prevention (duplicate task_id handling)
  - Release retry with exponential backoff
  - Consecutive failure alerting (ERROR logs at threshold)
  - Prometheus metrics for release failures
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.rate_limit_middleware import (
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_EXPIRY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_NAME,
    DistributedRateLimitMiddleware,
    RateLimitConfigurationError,
    RateLimitExceededError,
)


class TestDistributedRateLimitMiddleware:
    """Tests for DistributedRateLimitMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance with mock Redis client."""
        mock_redis = MagicMock()
        return DistributedRateLimitMiddleware(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_pre_execute_acquires_semaphore_when_labels_present(self, middleware):
        """Middleware acquires semaphore when task has rate_limit_name label."""
        message = MagicMock()
        message.task_id = "test-task-123"
        message.kwargs = {}
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
        message.task_id = "test-task-123"
        message.labels = {RATE_LIMIT_NAME: "test:lock"}
        result = MagicMock()

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)
        middleware._active_semaphores[message.task_id] = mock_semaphore

        await middleware.post_execute(message, result)

        mock_semaphore.__aexit__.assert_called_once()
        assert message.task_id not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_on_error_releases_semaphore(self, middleware):
        """Middleware releases semaphore on task error."""
        message = MagicMock()
        message.task_id = "test-task-123"
        message.labels = {RATE_LIMIT_NAME: "test:lock"}
        result = MagicMock()
        error = ValueError("test error")

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)
        middleware._active_semaphores[message.task_id] = mock_semaphore

        await middleware.on_error(message, result, error)

        mock_semaphore.__aexit__.assert_called_once()


class TestRateLimitNameTemplateInterpolation:
    """Tests for rate_limit_name template variable interpolation."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance with mock Redis client."""
        mock_redis = MagicMock()
        return DistributedRateLimitMiddleware(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_template_variable_is_interpolated_from_kwargs(self, middleware):
        """Template variables in rate_limit_name are replaced with kwarg values."""
        community_id = "550e8400-e29b-41d4-a716-446655440000"
        message = MagicMock()
        message.task_id = "test-task-123"
        message.kwargs = {"community_server_id": community_id}
        message.labels = {
            RATE_LIMIT_NAME: "rechunk:previously_seen:{community_server_id}",
            RATE_LIMIT_CAPACITY: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore) as mock_get:
            await middleware.pre_execute(message)

        expected_name = f"rechunk:previously_seen:{community_id}"
        mock_get.assert_called_once()
        actual_name = mock_get.call_args[0][0]
        assert actual_name == expected_name

    @pytest.mark.asyncio
    async def test_multiple_template_variables_are_interpolated(self, middleware):
        """Multiple template variables are all replaced."""
        message = MagicMock()
        message.task_id = "test-task-123"
        message.kwargs = {"community_id": "comm-123", "job_type": "rechunk"}
        message.labels = {
            RATE_LIMIT_NAME: "task:{job_type}:{community_id}",
            RATE_LIMIT_CAPACITY: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore) as mock_get:
            await middleware.pre_execute(message)

        expected_name = "task:rechunk:comm-123"
        actual_name = mock_get.call_args[0][0]
        assert actual_name == expected_name

    @pytest.mark.asyncio
    async def test_missing_template_variable_raises_configuration_error(self, middleware):
        """Missing template variables raise RateLimitConfigurationError (fail-fast)."""
        message = MagicMock()
        message.task_id = "test-task-123"
        message.kwargs = {"other_var": "value"}
        message.labels = {
            RATE_LIMIT_NAME: "task:{missing_var}",
            RATE_LIMIT_CAPACITY: "1",
        }

        with pytest.raises(RateLimitConfigurationError) as exc_info:
            await middleware.pre_execute(message)

        assert exc_info.value.rate_limit_name == "task:{missing_var}"
        assert exc_info.value.missing_vars == ["missing_var"]
        assert exc_info.value.available_kwargs == ["other_var"]

    @pytest.mark.asyncio
    async def test_no_template_variable_unchanged(self, middleware):
        """Rate limit name without template variables is unchanged."""
        message = MagicMock()
        message.task_id = "test-task-123"
        message.kwargs = {"community_server_id": "ignored"}
        message.labels = {
            RATE_LIMIT_NAME: "rechunk:fact_check",
            RATE_LIMIT_CAPACITY: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore) as mock_get:
            await middleware.pre_execute(message)

        actual_name = mock_get.call_args[0][0]
        assert actual_name == "rechunk:fact_check"

    @pytest.mark.asyncio
    async def test_per_community_rate_limits_are_isolated(self, middleware):
        """Different community_server_ids result in different rate limit names."""
        community_id_1 = "comm-111"
        community_id_2 = "comm-222"

        template = "rechunk:{community_server_id}"
        captured_names = []

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        def capture_semaphore(name, *args, **kwargs):
            captured_names.append(name)
            return mock_semaphore

        with patch.object(middleware, "_get_semaphore", side_effect=capture_semaphore):
            message1 = MagicMock()
            message1.task_id = "task-1"
            message1.kwargs = {"community_server_id": community_id_1}
            message1.labels = {RATE_LIMIT_NAME: template, RATE_LIMIT_CAPACITY: "1"}
            await middleware.pre_execute(message1)

            message2 = MagicMock()
            message2.task_id = "task-2"
            message2.kwargs = {"community_server_id": community_id_2}
            message2.labels = {RATE_LIMIT_NAME: template, RATE_LIMIT_CAPACITY: "1"}
            await middleware.pre_execute(message2)

        assert captured_names[0] == f"rechunk:{community_id_1}"
        assert captured_names[1] == f"rechunk:{community_id_2}"
        assert captured_names[0] != captured_names[1]


class TestSemaphoreReleaseRetry:
    """Tests for semaphore release retry logic."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        mock_redis = MagicMock()
        return DistributedRateLimitMiddleware(redis_client=mock_redis, instance_id="test")

    @pytest.mark.asyncio
    async def test_release_with_retry_succeeds_first_attempt(self, middleware):
        """Semaphore release succeeds on first attempt."""
        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)

        result = await middleware._release_with_retry(mock_semaphore, "test_task")

        assert result is True
        mock_semaphore.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_with_retry_succeeds_after_transient_failure(self, middleware):
        """Semaphore release succeeds after transient failure on first attempt."""
        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(side_effect=[Exception("transient error"), None])

        with patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock):
            result = await middleware._release_with_retry(mock_semaphore, "test_task")

        assert result is True
        assert mock_semaphore.__aexit__.call_count == 2

    @pytest.mark.asyncio
    async def test_release_with_retry_exhausts_retries(self, middleware):
        """Semaphore release fails after exhausting all retries."""
        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(side_effect=Exception("persistent error"))

        with patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock):
            result = await middleware._release_with_retry(mock_semaphore, "test_task")

        assert result is False
        assert mock_semaphore.__aexit__.call_count == 3

    @pytest.mark.asyncio
    async def test_consecutive_failure_counter_increments_and_resets(self, middleware):
        """Consecutive failure counter increments on failure and resets on success."""
        message = MagicMock()
        message.task_id = "test-task"
        message.task_name = "test_task"

        mock_semaphore_fail = AsyncMock()
        mock_semaphore_fail.__aexit__ = AsyncMock(side_effect=Exception("error"))
        mock_semaphore_success = AsyncMock()
        mock_semaphore_success.__aexit__ = AsyncMock(return_value=False)

        with patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock):
            middleware._active_semaphores[message.task_id] = mock_semaphore_fail
            await middleware._release_semaphore(message)
            assert middleware._consecutive_release_failures == 1

            middleware._active_semaphores[message.task_id] = mock_semaphore_fail
            await middleware._release_semaphore(message)
            assert middleware._consecutive_release_failures == 2

            middleware._active_semaphores[message.task_id] = mock_semaphore_success
            await middleware._release_semaphore(message)
            assert middleware._consecutive_release_failures == 0

    @pytest.mark.asyncio
    async def test_alert_log_emitted_at_threshold(self, middleware, caplog):
        """ERROR log is emitted when consecutive failures reach threshold."""
        import logging

        message = MagicMock()
        message.task_id = "test-task"
        message.task_name = "test_task"

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(side_effect=Exception("error"))

        with (
            patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.ERROR),
        ):
            for _ in range(3):
                middleware._active_semaphores[message.task_id] = mock_semaphore
                await middleware._release_semaphore(message)

        assert "ALERT:" in caplog.text
        assert "3 consecutive semaphore release failures" in caplog.text

    def test_calculate_backoff_delay_returns_non_negative(self, middleware):
        """Backoff delay is always non-negative."""
        for attempt in range(10):
            delay = middleware._calculate_backoff_delay(attempt)
            assert delay >= 0.0, f"Delay should be non-negative, got {delay}"

    def test_calculate_backoff_delay_respects_max(self, middleware):
        """Backoff delay respects RELEASE_MAX_DELAY."""
        from src.tasks.rate_limit_middleware import RELEASE_JITTER, RELEASE_MAX_DELAY

        delay = middleware._calculate_backoff_delay(100)
        max_with_jitter = RELEASE_MAX_DELAY * (1 + RELEASE_JITTER)
        assert delay <= max_with_jitter, f"Delay {delay} exceeds max {max_with_jitter}"


class TestMiddlewareBasedLockRelease:
    """Tests for middleware-based lock release behavior.

    Coverage mapping from removed RechunkLockManager tests:
    - Lock release on success path → test_semaphore_released_on_success_path
    - Lock release on error path → test_semaphore_released_on_error_path
    - No semaphore leak on acquisition timeout → test_semaphore_not_leaked_on_pre_execute_timeout
    - Metrics updated on failure → test_release_failure_increments_prometheus_metrics
    """

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        mock_redis = MagicMock()
        return DistributedRateLimitMiddleware(redis_client=mock_redis, instance_id="test")

    @pytest.mark.asyncio
    async def test_semaphore_released_on_success_path(self, middleware):
        """Verify semaphore cleanup after normal task completion."""
        message = MagicMock()
        message.task_id = "success-task-123"
        message.task_name = "test_task"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "test:lock:success",
            RATE_LIMIT_CAPACITY: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore):
            await middleware.pre_execute(message)
            assert message.task_id in middleware._active_semaphores

            result = MagicMock()
            await middleware.post_execute(message, result)

        mock_semaphore.__aexit__.assert_called_once()
        assert message.task_id not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_semaphore_released_on_error_path(self, middleware):
        """Verify semaphore cleanup after task exception."""
        message = MagicMock()
        message.task_id = "error-task-123"
        message.task_name = "test_task"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "test:lock:error",
            RATE_LIMIT_CAPACITY: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(return_value=False)

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore):
            await middleware.pre_execute(message)
            assert message.task_id in middleware._active_semaphores

            error = ValueError("Task failed with exception")
            result = MagicMock()
            await middleware.on_error(message, result, error)

        mock_semaphore.__aexit__.assert_called_once()
        assert message.task_id not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_semaphore_not_leaked_on_pre_execute_timeout(self, middleware):
        """Verify no semaphore leak when acquisition times out."""
        from limiters import MaxSleepExceededError

        message = MagicMock()
        message.task_id = "timeout-task-123"
        message.task_name = "test_task"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "test:lock:timeout",
            RATE_LIMIT_CAPACITY: "1",
            RATE_LIMIT_MAX_SLEEP: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock(side_effect=MaxSleepExceededError())

        with (
            patch.object(middleware, "_get_semaphore", return_value=mock_semaphore),
            pytest.raises(RateLimitExceededError),
        ):
            await middleware.pre_execute(message)

        assert message.task_id not in middleware._active_semaphores

    @pytest.mark.asyncio
    async def test_release_failure_increments_otel_metrics(self, middleware):
        """Verify OTEL metrics updated on release failure."""
        message = MagicMock()
        message.task_id = "metrics-task-123"
        message.task_name = "test_task"

        mock_semaphore = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock(side_effect=Exception("Redis unavailable"))

        middleware._active_semaphores[message.task_id] = mock_semaphore

        with (
            patch("src.tasks.rate_limit_middleware.asyncio.sleep", new_callable=AsyncMock),
            patch(
                "src.tasks.rate_limit_middleware.semaphore_release_failures_total"
            ) as mock_metric,
        ):
            mock_metric.add = MagicMock()
            await middleware._release_semaphore(message)

            mock_metric.add.assert_called_once_with(1, {"task_name": "test_task"})


class TestRateLimitExpiryLabel:
    """Tests for rate_limit_expiry label propagation to AsyncSemaphore."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        mock_redis = MagicMock()
        return DistributedRateLimitMiddleware(redis_client=mock_redis, instance_id="test")

    @pytest.mark.asyncio
    async def test_expiry_label_passed_to_semaphore(self, middleware):
        """Verify rate_limit_expiry propagates to AsyncSemaphore."""
        message = MagicMock()
        message.task_id = "expiry-task-123"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "test:lock:expiry",
            RATE_LIMIT_CAPACITY: "2",
            RATE_LIMIT_MAX_SLEEP: "15",
            RATE_LIMIT_EXPIRY: "3600",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore) as mock_get:
            await middleware.pre_execute(message)

        mock_get.assert_called_once_with(
            "test:lock:expiry",
            2,
            15,
            3600,
        )

    @pytest.mark.asyncio
    async def test_default_expiry_when_label_not_provided(self, middleware):
        """Verify default expiry (1800) used when rate_limit_expiry not provided."""
        message = MagicMock()
        message.task_id = "default-expiry-task-123"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "test:lock:default_expiry",
            RATE_LIMIT_CAPACITY: "1",
        }

        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock()

        with patch.object(middleware, "_get_semaphore", return_value=mock_semaphore) as mock_get:
            await middleware.pre_execute(message)

        mock_get.assert_called_once_with(
            "test:lock:default_expiry",
            1,
            30,
            1800,
        )


class TestSemaphoreLeakPrevention:
    """Tests for semaphore leak prevention when task_id already tracked."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        mock_redis = MagicMock()
        return DistributedRateLimitMiddleware(redis_client=mock_redis, instance_id="test")

    @pytest.mark.asyncio
    async def test_pre_execute_skips_tracking_when_task_id_exists(self, middleware):
        """Pre-execute skips acquiring new semaphore when task_id already tracked."""
        existing_semaphore = AsyncMock()
        message = MagicMock()
        message.task_id = "existing-task"
        message.task_name = "test_task"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "test:lock",
            RATE_LIMIT_CAPACITY: "1",
        }

        middleware._active_semaphores[message.task_id] = existing_semaphore

        mock_new_semaphore = AsyncMock()
        with patch.object(
            middleware, "_get_semaphore", return_value=mock_new_semaphore
        ) as mock_get:
            result = await middleware.pre_execute(message)

        assert result == message
        mock_get.assert_not_called()
        assert middleware._active_semaphores[message.task_id] is existing_semaphore
