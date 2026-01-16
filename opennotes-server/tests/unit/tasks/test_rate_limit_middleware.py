"""Unit tests for DistributedRateLimitMiddleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.rate_limit_middleware import (
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_MAX_SLEEP,
    RATE_LIMIT_NAME,
    DistributedRateLimitMiddleware,
    RateLimitExceededError,
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
        """Create middleware instance."""
        redis_url = "redis://localhost:6379"
        return DistributedRateLimitMiddleware(redis_url)

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
    async def test_missing_template_variable_raises_rate_limit_error(self, middleware):
        """Missing template variables raise RateLimitExceededError (fail-fast)."""
        message = MagicMock()
        message.task_id = "test-task-123"
        message.kwargs = {}
        message.labels = {
            RATE_LIMIT_NAME: "task:{missing_var}",
            RATE_LIMIT_CAPACITY: "1",
        }

        with pytest.raises(RateLimitExceededError) as exc_info:
            await middleware.pre_execute(message)

        assert exc_info.value.rate_limit_name == "task:{missing_var}"
        assert exc_info.value.max_sleep == 0

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
        redis_url = "redis://localhost:6379"
        return DistributedRateLimitMiddleware(redis_url, instance_id="test")

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


class TestSemaphoreLeakPrevention:
    """Tests for semaphore leak prevention when task_id already tracked."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        redis_url = "redis://localhost:6379"
        return DistributedRateLimitMiddleware(redis_url, instance_id="test")

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
