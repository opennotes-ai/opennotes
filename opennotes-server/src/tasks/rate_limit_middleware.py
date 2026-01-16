"""Distributed rate limiting middleware for TaskIQ.

Wraps task execution with AsyncSemaphore from redis-rate-limiters library,
allowing task-level concurrency control via labels.

Designed to be extractable as a standalone package (taskiq-redis-ratelimit).

Label Configuration:
    rate_limit_name: Required. Lock signature/name (e.g., "import:fact_check")
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
"""

from __future__ import annotations

import logging
from typing import Any

from limiters import AsyncSemaphore
from redis.asyncio import Redis
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

logger = logging.getLogger(__name__)

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
        self._active_semaphores: dict[int, AsyncSemaphore] = {}

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

        capacity = int(labels.get(RATE_LIMIT_CAPACITY, DEFAULT_CAPACITY))
        max_sleep = int(labels.get(RATE_LIMIT_MAX_SLEEP, DEFAULT_MAX_SLEEP))
        expiry = int(labels.get(RATE_LIMIT_EXPIRY, DEFAULT_EXPIRY))

        logger.debug(f"Acquiring rate limit: name={rate_limit_name}, capacity={capacity}")

        semaphore = self._get_semaphore(rate_limit_name, capacity, max_sleep, expiry)
        await semaphore.__aenter__()

        self._active_semaphores[id(message)] = semaphore

        return message

    async def post_execute(self, message: TaskiqMessage, _result: TaskiqResult[Any]) -> None:
        await self._release_semaphore(message)

    async def on_error(
        self,
        message: TaskiqMessage,
        _result: BaseException,
        _exception: BaseException,
    ) -> None:
        await self._release_semaphore(message)

    async def _release_semaphore(self, message: TaskiqMessage) -> None:
        semaphore = self._active_semaphores.pop(id(message), None)
        if semaphore:
            try:
                await semaphore.__aexit__(None, None, None)
                logger.debug(f"Released rate limit for task {message.task_name}")
            except Exception as e:
                logger.error(f"Error releasing semaphore: {e}")
