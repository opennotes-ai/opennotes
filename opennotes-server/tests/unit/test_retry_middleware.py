"""
Unit tests for RetryWithFinalCallbackMiddleware.

TDD tests for a middleware that extends TaskIQ's SimpleRetryMiddleware
with an `on_error_last_retry` callback that only fires when all retries
are exhausted.

These tests should FAIL initially (red phase) since the middleware
doesn't exist yet.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from taskiq import TaskiqMessage, TaskiqResult


def create_mock_message(
    task_id: str = "test-task-123",
    task_name: str = "test:task",
    retries: int = 0,
    max_retries: int | None = None,
) -> TaskiqMessage:
    """Create a mock TaskiqMessage with configurable retry labels."""
    labels: dict[str, str] = {"_retries": str(retries)}
    if max_retries is not None:
        labels["max_retries"] = str(max_retries)
    return TaskiqMessage(
        task_id=task_id,
        task_name=task_name,
        labels=labels,
        args=[],
        kwargs={},
    )


def create_mock_result(is_err: bool = True) -> TaskiqResult:
    """Create a mock TaskiqResult."""
    return TaskiqResult(
        is_err=is_err,
        log=None,
        return_value=None,
        execution_time=0.1,
    )


class TestRetryWithFinalCallbackMiddleware:
    """Tests for RetryWithFinalCallbackMiddleware behavior."""

    @pytest.mark.asyncio
    async def test_callback_not_called_on_first_retry(self) -> None:
        """
        When _retries=0 and max_retries=3, callback should NOT be called.

        First retry means retries=0, and we haven't exhausted max_retries=3 yet.
        The callback should only fire on the final (last) retry attempt.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = create_mock_message(retries=0, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_not_called_on_intermediate_retry(self) -> None:
        """
        When _retries=1 and max_retries=3, callback should NOT be called.

        This is an intermediate retry (2nd attempt out of 3), so we haven't
        exhausted all retries yet.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = create_mock_message(retries=1, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed again")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_called_on_last_retry(self) -> None:
        """
        When _retries=2 and max_retries=3, callback SHOULD be called.

        This is the last retry (3rd attempt = retries 0, 1, 2), so the callback
        should fire because all retries are exhausted.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = create_mock_message(retries=2, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed permanently")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_receives_correct_args(self) -> None:
        """
        Verify callback receives message, result, and exception arguments.

        The callback should receive the same arguments that on_error receives
        so it has full context about the failed task.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = create_mock_message(
            task_id="specific-task-id",
            task_name="myapp:specific_task",
            retries=2,
            max_retries=3,
        )
        result = create_mock_result()
        exception = ValueError("Specific error message")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_called_once_with(message, result, exception)

    @pytest.mark.asyncio
    async def test_no_callback_configured(self) -> None:
        """
        When on_error_last_retry=None, no error should occur on last retry.

        The middleware should gracefully handle the case where no callback
        is configured - it should just not call anything.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=None,
            default_retry_count=3,
        )

        message = create_mock_message(retries=2, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

    @pytest.mark.asyncio
    async def test_respects_task_specific_max_retries_label(self) -> None:
        """
        When task has custom max_retries label, use that instead of default.

        Tasks can override the default retry count via the max_retries label.
        The middleware should respect this task-specific setting.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=5,
        )

        message = create_mock_message(retries=1, max_retries=2)
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_default_retry_count_when_no_label(self) -> None:
        """
        When task has no max_retries label, use the default_retry_count.

        If the task doesn't specify max_retries, the middleware should
        fall back to its configured default_retry_count.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=2,
        )

        message = TaskiqMessage(
            task_id="test-task",
            task_name="test:task",
            labels={"_retries": "1"},
            args=[],
            kwargs={},
        )
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_parent_on_error_always_called(self) -> None:
        """
        Verify that parent's on_error is always called regardless of retry count.

        The parent SimpleRetryMiddleware's on_error handles the actual retry
        logic, so it must always be called before our callback logic.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = create_mock_message(retries=0, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ) as mock_parent_on_error:
            await middleware.on_error(message, result, exception)
            mock_parent_on_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_exception_is_logged_not_propagated(self) -> None:
        """
        If the callback raises an exception, it should be logged, not propagated.

        Callback exceptions should not mask the original task error. The middleware
        catches callback failures and logs them while allowing normal flow to continue.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock(side_effect=RuntimeError("Callback failed"))
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = create_mock_message(retries=2, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with (
            patch.object(
                middleware.__class__.__bases__[0],
                "on_error",
                new_callable=AsyncMock,
            ),
            patch("src.tasks.middleware.logger") as mock_logger,
        ):
            # Should NOT raise - callback exception is caught and logged
            await middleware.on_error(message, result, exception)

            # Verify callback was attempted
            mock_callback.assert_called_once()

            # Verify error was logged
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "Final retry callback failed" in call_args[0][0]
            assert message.task_name in call_args[0][1]


class TestRetryCallbackHandlerRegistry:
    """
    Tests for task-specific handler registry pattern.

    This tests a registry that allows different callbacks for different
    task types, enabling task-specific error handling.
    """

    @pytest.mark.asyncio
    async def test_registry_dispatch_to_correct_handler(self) -> None:
        """
        Test that the registry dispatches to the correct handler based on task name.

        Different tasks may need different error handling (e.g., sending
        different notifications or cleanup actions).
        """
        from src.tasks.middleware import (
            RetryCallbackHandlerRegistry,
            RetryWithFinalCallbackMiddleware,
        )

        handler_a = AsyncMock()
        handler_b = AsyncMock()

        registry = RetryCallbackHandlerRegistry()
        registry.register("task_a", handler_a)
        registry.register("task_b", handler_b)

        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=registry.dispatch,
            default_retry_count=3,
        )

        message_a = TaskiqMessage(
            task_id="task-a-123",
            task_name="task_a",
            labels={"_retries": "2", "max_retries": "3"},
            args=[],
            kwargs={},
        )
        result = create_mock_result()
        exception = RuntimeError("Task A failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message_a, result, exception)

        handler_a.assert_called_once_with(message_a, result, exception)
        handler_b.assert_not_called()

    @pytest.mark.asyncio
    async def test_registry_no_handler_registered(self) -> None:
        """
        When no handler is registered for a task, dispatch should be a no-op.

        Not all tasks need final retry callbacks, so missing handlers
        should be handled gracefully.
        """
        from src.tasks.middleware import (
            RetryCallbackHandlerRegistry,
            RetryWithFinalCallbackMiddleware,
        )

        registry = RetryCallbackHandlerRegistry()

        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=registry.dispatch,
            default_retry_count=3,
        )

        message = TaskiqMessage(
            task_id="unregistered-task-123",
            task_name="unregistered_task",
            labels={"_retries": "2", "max_retries": "3"},
            args=[],
            kwargs={},
        )
        result = create_mock_result()
        exception = RuntimeError("Unregistered task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

    @pytest.mark.asyncio
    async def test_registry_default_handler(self) -> None:
        """
        Test that a default handler is called when no specific handler exists.

        A default handler can be used as a catch-all for tasks that don't
        have specific error handling needs.
        """
        from src.tasks.middleware import (
            RetryCallbackHandlerRegistry,
            RetryWithFinalCallbackMiddleware,
        )

        default_handler = AsyncMock()
        specific_handler = AsyncMock()

        registry = RetryCallbackHandlerRegistry(default_handler=default_handler)
        registry.register("specific_task", specific_handler)

        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=registry.dispatch,
            default_retry_count=3,
        )

        message = TaskiqMessage(
            task_id="other-task-123",
            task_name="other_task",
            labels={"_retries": "2", "max_retries": "3"},
            args=[],
            kwargs={},
        )
        result = create_mock_result()
        exception = RuntimeError("Other task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        default_handler.assert_called_once_with(message, result, exception)
        specific_handler.assert_not_called()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_max_retries(self) -> None:
        """
        When max_retries=0, callback should be called on first error.

        Zero retries means no retries at all, so the first failure is
        also the last.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=0,
        )

        message = TaskiqMessage(
            task_id="test-task",
            task_name="test:task",
            labels={"_retries": "0", "max_retries": "0"},
            args=[],
            kwargs={},
        )
        result = create_mock_result()
        exception = RuntimeError("Immediate failure")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_retry_on_first_attempt(self) -> None:
        """
        When max_retries=1 and _retries=0, callback should NOT be called.

        First attempt (retries=0) with max_retries=1 means there's still
        one more retry left.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=1,
        )

        message = create_mock_message(retries=0, max_retries=1)
        result = create_mock_result()
        exception = RuntimeError("First attempt failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_retry_on_last_attempt(self) -> None:
        """
        When max_retries=1 and _retries=1, callback SHOULD be called.

        Second attempt (retries=1) with max_retries=1 means all retries
        are exhausted (we've had retries 0 and 1, that's 2 attempts total
        but only 1 retry).

        Note: This depends on interpretation. If max_retries=1 means
        "1 retry after initial attempt", then retries=1 is the last.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=1,
        )

        # _retries=1 means this is the second attempt (after first failure)
        message = create_mock_message(retries=1, max_retries=1)
        result = create_mock_result()
        exception = RuntimeError("Last attempt failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        # Callback SHOULD be called on last retry
        mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_retries_label_defaults_to_zero(self) -> None:
        """
        When _retries label is missing, treat as first attempt (0).

        The first time a task runs, it won't have a _retries label.
        We should treat this as retries=0.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        mock_callback = AsyncMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=mock_callback,
            default_retry_count=3,
        )

        message = TaskiqMessage(
            task_id="test-task",
            task_name="test:task",
            labels={},
            args=[],
            kwargs={},
        )
        result = create_mock_result()
        exception = RuntimeError("First attempt failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_callback_is_wrapped(self) -> None:
        """
        Test that synchronous callbacks are properly handled.

        While the middleware is async, users might provide sync callbacks.
        The middleware should handle this gracefully.
        """
        from src.tasks.middleware import RetryWithFinalCallbackMiddleware

        sync_callback = MagicMock()
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=sync_callback,
            default_retry_count=3,
        )

        message = create_mock_message(retries=2, max_retries=3)
        result = create_mock_result()
        exception = RuntimeError("Task failed")

        with patch.object(
            middleware.__class__.__bases__[0],
            "on_error",
            new_callable=AsyncMock,
        ):
            await middleware.on_error(message, result, exception)

        sync_callback.assert_called_once()
