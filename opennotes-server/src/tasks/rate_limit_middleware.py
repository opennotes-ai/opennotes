"""Distributed rate limiting middleware for TaskIQ.

Wraps task execution with AsyncSemaphore from redis-rate-limiters library,
allowing task-level concurrency control via labels.

Designed to be extractable as a standalone package (taskiq-redis-ratelimit).

Label Configuration:
    rate_limit_name: Required. Lock signature/name (e.g., "import:fact_check").
        Supports template variables using Python format syntax, which are
        interpolated from task kwargs at runtime. For example,
        "rechunk:previously_seen:{community_server_id}" will be interpolated
        with the community_server_id kwarg value.
    rate_limit_capacity: Optional. Max concurrent permits (default: 1)
    rate_limit_max_sleep: Optional. Seconds before MaxSleepExceededError (default: 30)
    rate_limit_expiry: Optional. Redis key TTL in seconds (default: 1800)

Example:
    @register_task(
        task_name="import:candidates",
        rate_limit_name="import:fact_check",
        rate_limit_capacity="1",
    )
    async def my_task():
        ...

    @register_task(
        task_name="rechunk:previously_seen",
        rate_limit_name="rechunk:previously_seen:{community_server_id}",
        rate_limit_capacity="1",
    )
    async def my_per_community_task(community_server_id: str):
        ...
"""

from __future__ import annotations

import logging
from typing import Any

from limiters import AsyncSemaphore, MaxSleepExceededError
from redis.asyncio import Redis
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

logger = logging.getLogger(__name__)


class RateLimitExceededError(Exception):
    """Raised when a task cannot acquire a rate limit permit within max_sleep time."""

    def __init__(self, rate_limit_name: str, max_sleep: int) -> None:
        self.rate_limit_name = rate_limit_name
        self.max_sleep = max_sleep
        super().__init__(
            f"Rate limit '{rate_limit_name}' exceeded: could not acquire permit within {max_sleep}s"
        )


RATE_LIMIT_NAME = "rate_limit_name"
RATE_LIMIT_CAPACITY = "rate_limit_capacity"
RATE_LIMIT_MAX_SLEEP = "rate_limit_max_sleep"
RATE_LIMIT_EXPIRY = "rate_limit_expiry"

DEFAULT_CAPACITY = 1
DEFAULT_MAX_SLEEP = 30
DEFAULT_EXPIRY = 1800


class DistributedRateLimitMiddleware(TaskiqMiddleware):
    """TaskIQ middleware for distributed rate limiting using redis-rate-limiters."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Redis | None = None
        self._active_semaphores: dict[str, AsyncSemaphore] = {}

    async def startup(self) -> None:
        self._redis = Redis.from_url(self._redis_url)
        logger.info("DistributedRateLimitMiddleware started")

    async def shutdown(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("DistributedRateLimitMiddleware stopped")

    def _get_semaphore(
        self,
        name: str,
        capacity: int = DEFAULT_CAPACITY,
        max_sleep: int = DEFAULT_MAX_SLEEP,
        expiry: int = DEFAULT_EXPIRY,
    ) -> AsyncSemaphore:
        if self._redis is None:
            raise RuntimeError("Middleware not started - call startup() first")

        return AsyncSemaphore(
            name=name,
            capacity=capacity,
            max_sleep=max_sleep,
            expiry=expiry,
            connection=self._redis,
        )

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        labels = message.labels or {}
        rate_limit_name = labels.get(RATE_LIMIT_NAME)

        if not rate_limit_name:
            return message

        if "{" in rate_limit_name:
            try:
                rate_limit_name = rate_limit_name.format_map(message.kwargs)
            except KeyError as e:
                logger.warning(
                    f"Missing template variable for rate_limit_name '{rate_limit_name}': {e}"
                )

        capacity = int(labels.get(RATE_LIMIT_CAPACITY, DEFAULT_CAPACITY))
        max_sleep = int(labels.get(RATE_LIMIT_MAX_SLEEP, DEFAULT_MAX_SLEEP))
        expiry = int(labels.get(RATE_LIMIT_EXPIRY, DEFAULT_EXPIRY))

        logger.debug(f"Acquiring rate limit: name={rate_limit_name}, capacity={capacity}")

        semaphore = self._get_semaphore(rate_limit_name, capacity, max_sleep, expiry)

        self._active_semaphores[message.task_id] = semaphore
        try:
            await semaphore.__aenter__()
        except MaxSleepExceededError:
            del self._active_semaphores[message.task_id]
            raise RateLimitExceededError(rate_limit_name, max_sleep)
        except BaseException:
            del self._active_semaphores[message.task_id]
            raise

        return message

    async def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:  # noqa: ARG002
        await self._release_semaphore(message)

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
        exception: BaseException,  # noqa: ARG002
    ) -> None:
        await self._release_semaphore(message)

    async def _release_semaphore(self, message: TaskiqMessage) -> None:
        semaphore = self._active_semaphores.pop(message.task_id, None)
        if semaphore:
            try:
                await semaphore.__aexit__(None, None, None)
                logger.debug(f"Released rate limit for task {message.task_name}")
            except Exception as e:
                logger.error(f"Error releasing semaphore: {e}")
