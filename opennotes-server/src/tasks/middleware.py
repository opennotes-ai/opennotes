"""
Custom TaskIQ middleware with final retry callback support.

This module provides a middleware that extends TaskIQ's SimpleRetryMiddleware
with an `on_error_last_retry` callback that fires when all retries are exhausted.

Usage:
    from src.tasks.middleware import RetryWithFinalCallbackMiddleware

    async def handle_final_failure(message, result, exception):
        # Send alert, update status, etc.
        pass

    middleware = RetryWithFinalCallbackMiddleware(
        on_error_last_retry=handle_final_failure,
        default_retry_count=3,
    )

For task-specific handlers, use the RetryCallbackHandlerRegistry:

    from src.tasks.middleware import (
        RetryCallbackHandlerRegistry,
        RetryWithFinalCallbackMiddleware,
    )

    registry = RetryCallbackHandlerRegistry()
    registry.register("my_task", my_task_error_handler)

    middleware = RetryWithFinalCallbackMiddleware(
        on_error_last_retry=registry.dispatch,
        default_retry_count=3,
    )
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from taskiq import SimpleRetryMiddleware, TaskiqMessage, TaskiqResult

logger = logging.getLogger(__name__)

OnErrorLastRetryCallback = Callable[
    [TaskiqMessage, TaskiqResult[Any], BaseException],
    Awaitable[None] | None,
]


class RetryWithFinalCallbackMiddleware(SimpleRetryMiddleware):
    """
    Middleware that extends SimpleRetryMiddleware with a final retry callback.

    When all retries are exhausted, the `on_error_last_retry` callback is called
    with the message, result, and exception. This allows tasks to perform cleanup,
    send alerts, or update status when a task permanently fails.

    The callback is called AFTER the parent's on_error() method, ensuring the
    standard retry logic runs first.

    Args:
        on_error_last_retry: Optional async callback called when all retries exhausted.
            Signature: (message, result, exception) -> None
        default_retry_count: Default number of retries (passed to parent).
        **kwargs: Additional arguments passed to SimpleRetryMiddleware.
    """

    def __init__(
        self,
        on_error_last_retry: OnErrorLastRetryCallback | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._on_error_last_retry = on_error_last_retry

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        """
        Handle task error with final retry callback support.

        First calls the parent's on_error() to handle standard retry logic,
        then checks if this is the last retry and calls the callback if so.

        The logic for determining last retry:
        - _retries = number of retries already attempted (from message labels)
        - retries = _retries + 1 (current attempt number, 1-indexed)
        - max_retries = task-specific label or default_retry_count

        A retry is considered "last" when:
        - retries >= max_retries (exhausted retry budget), AND
        - Either _retries > 0 (not the first attempt) OR max_retries == 0 (no retries allowed)

        This ensures that when max_retries > 0, the first failure (_retries=0)
        does not trigger the callback since there are still retries available.
        """
        await super().on_error(message, result, exception)

        _retries = int(message.labels.get("_retries", 0))
        retries = _retries + 1
        max_retries = int(message.labels.get("max_retries", self.default_retry_count))
        is_last_retry = (retries >= max_retries) and (_retries > 0 or max_retries == 0)

        if is_last_retry and self._on_error_last_retry is not None:
            callback_result = self._on_error_last_retry(message, result, exception)
            if asyncio.iscoroutine(callback_result):
                await callback_result


class RetryCallbackHandlerRegistry:
    """
    Registry for task-specific error handlers.

    Allows registering different callbacks for different task types,
    enabling task-specific error handling (e.g., different notifications
    or cleanup actions per task).

    Usage:
        registry = RetryCallbackHandlerRegistry()
        registry.register("task_a", handle_task_a_failure)
        registry.register("task_b", handle_task_b_failure)

        # Use registry.dispatch as the middleware callback
        middleware = RetryWithFinalCallbackMiddleware(
            on_error_last_retry=registry.dispatch,
            default_retry_count=3,
        )

    Args:
        default_handler: Optional default handler called when no specific
            handler is registered for a task.
    """

    def __init__(
        self,
        default_handler: OnErrorLastRetryCallback | None = None,
    ) -> None:
        self._handlers: dict[str, OnErrorLastRetryCallback] = {}
        self._default_handler = default_handler

    def register(
        self,
        task_name: str,
        handler: OnErrorLastRetryCallback,
    ) -> None:
        """
        Register a handler for a specific task.

        Args:
            task_name: The task name to register the handler for.
            handler: Async callback with signature (message, result, exception) -> None.
        """
        self._handlers[task_name] = handler

    async def dispatch(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        """
        Dispatch to the appropriate handler based on task name.

        Looks up the handler for the task's name. If no specific handler
        is registered, uses the default handler (if one was provided).
        If no handler is found, does nothing.

        Args:
            message: The TaskIQ message for the failed task.
            result: The TaskIQ result containing error information.
            exception: The exception that caused the failure.
        """
        handler = self._handlers.get(message.task_name)
        if handler is None:
            handler = self._default_handler
        if handler is None:
            return

        callback_result = handler(message, result, exception)
        if asyncio.iscoroutine(callback_result):
            await callback_result


__all__ = [
    "OnErrorLastRetryCallback",
    "RetryCallbackHandlerRegistry",
    "RetryWithFinalCallbackMiddleware",
]
