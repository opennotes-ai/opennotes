"""Distributed rate limiting middleware for TaskIQ.

Wraps task execution with AsyncSemaphore from redis-rate-limiters library,
allowing task-level concurrency control via labels.

Designed to be extractable as a standalone package (taskiq-redis-ratelimit).

TODO: Consider transitioning from AsyncSemaphore to TokenBucket for rate limiting.
TokenBucket would provide built-in delay between requests rather than just concurrency control.
Current workaround: tasks add explicit sleep(base_delay + jitter) after semaphore acquisition.
See fetch_url_content in scrape_tasks.py for the current implementation pattern.

Label Configuration:
    rate_limit_name: Required. Lock signature/name (e.g., "import:fact_check").
        Supports template variables using Python format syntax, which are
        interpolated from task kwargs at runtime. For example,
        "rechunk:previously_seen:{community_server_id}" will be interpolated
        with the community_server_id kwarg value.
    rate_limit_capacity: Optional. Max concurrent permits (default: 1)
    rate_limit_max_sleep: Optional. Seconds before MaxSleepExceededError (default: 30)
    rate_limit_expiry: Optional. Redis key TTL in seconds (default: 1800)

Template Variable Requirements:
    Template variables in rate_limit_name MUST be provided as task kwargs.
    If a required variable is missing, RateLimitConfigurationError is raised
    immediately (fail-fast behavior). This exception type clearly indicates
    a configuration error vs. a timeout, allowing different retry behavior.

    Known templates and their required kwargs:
    - "rechunk:previously_seen:{community_server_id}" requires: community_server_id
    - "import:candidates:{community_server_id}" requires: community_server_id
    - "task:{job_type}:{community_id}" requires: job_type, community_id

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

import asyncio
import logging
import random
from typing import Any

from limiters import AsyncSemaphore, MaxSleepExceededError
from redis.asyncio import Redis
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from src.monitoring.metrics import (
    semaphore_leak_prevented_total,
    semaphore_release_failures_total,
    semaphore_release_retries_total,
)

logger = logging.getLogger(__name__)


class RateLimitExceededError(Exception):
    """Raised when a task cannot acquire a rate limit permit within max_sleep time."""

    def __init__(self, rate_limit_name: str, max_sleep: int) -> None:
        self.rate_limit_name = rate_limit_name
        self.max_sleep = max_sleep
        super().__init__(
            f"Rate limit '{rate_limit_name}' exceeded: could not acquire permit within {max_sleep}s"
        )


class RateLimitConfigurationError(Exception):
    """Raised when rate limit configuration is invalid (e.g., missing template variables).

    This is a configuration error, not a timeout. The task should not be retried
    without fixing the configuration.
    """

    def __init__(
        self, rate_limit_name: str, missing_vars: list[str], available_kwargs: list[str]
    ) -> None:
        self.rate_limit_name = rate_limit_name
        self.missing_vars = missing_vars
        self.available_kwargs = available_kwargs
        super().__init__(
            f"Rate limit template '{rate_limit_name}' has undefined variables: {missing_vars}. "
            f"Available kwargs: {available_kwargs}"
        )


RATE_LIMIT_NAME = "rate_limit_name"
RATE_LIMIT_CAPACITY = "rate_limit_capacity"
RATE_LIMIT_MAX_SLEEP = "rate_limit_max_sleep"
RATE_LIMIT_EXPIRY = "rate_limit_expiry"

DEFAULT_CAPACITY = 1
DEFAULT_MAX_SLEEP = 30
DEFAULT_EXPIRY = 1800

RELEASE_MAX_ATTEMPTS = 3
RELEASE_BASE_DELAY = 0.1
RELEASE_MAX_DELAY = 2.0
RELEASE_JITTER = 0.1
CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3


class DistributedRateLimitMiddleware(TaskiqMiddleware):
    """TaskIQ middleware for distributed rate limiting using redis-rate-limiters.

    Semaphore Lifecycle (_active_semaphores):
        This dict tracks in-flight semaphores for proper cleanup. Entries are:
        - Added in pre_execute() after successful semaphore.__aenter__()
        - Removed in _release_semaphore() via pop() during post_execute/on_error

        Leak Prevention:
        - If the same task_id appears twice (e.g., retry before cleanup), we preserve
          the original semaphore reference to avoid orphaning it. The duplicate
          detection at lines 173-182 prevents this edge case.
        - If a catastrophic failure prevents _release_semaphore() from running,
          dict entries remain but the Redis key TTL (default 1800s) ensures the
          actual lock eventually expires. This is acceptable because:
          a) Task IDs are unique UUIDs - no key reuse conflicts
          b) Dict size is bounded by max concurrent tasks (typically hundreds)
          c) Process restart naturally clears in-memory dict

    Failure Tracking (_consecutive_release_failures):
        This counter is intentionally per-worker-instance, not cross-worker:
        - Cross-worker tracking via Redis would add latency to every release
        - Per-worker alerts (threshold=3) still effectively detect Redis issues
        - Each worker independently monitors its own connectivity health
        - The metric semaphore_release_failures_total provides aggregate visibility

    Attributes:
        _redis: Async Redis client instance (shared with result backend).
        _owns_redis: Whether this middleware owns the Redis client lifecycle.
        _active_semaphores: Maps task_id -> AsyncSemaphore for cleanup.
        _instance_id: Worker instance identifier for metrics.
        _consecutive_release_failures: Per-instance failure counter for alerting.
    """

    def __init__(
        self,
        redis_client: Redis,
        instance_id: str = "default",
    ) -> None:
        super().__init__()
        self._redis: Redis = redis_client
        self._active_semaphores: dict[str, AsyncSemaphore] = {}
        self._instance_id = instance_id
        self._consecutive_release_failures: int = 0

    async def startup(self) -> None:
        logger.info("DistributedRateLimitMiddleware started (using shared Redis client)")

    async def shutdown(self) -> None:
        logger.info("DistributedRateLimitMiddleware stopped")

    def _get_semaphore(
        self,
        name: str,
        capacity: int = DEFAULT_CAPACITY,
        max_sleep: int = DEFAULT_MAX_SLEEP,
        expiry: int = DEFAULT_EXPIRY,
    ) -> AsyncSemaphore:
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
                missing_var = str(e).strip("'\"")
                available = list(message.kwargs.keys())
                logger.error(
                    f"Rate limit configuration error: template '{rate_limit_name}' "
                    f"requires variable '{missing_var}' but available kwargs are: {available}"
                )
                raise RateLimitConfigurationError(
                    rate_limit_name, missing_vars=[missing_var], available_kwargs=available
                )

        capacity = int(labels.get(RATE_LIMIT_CAPACITY, DEFAULT_CAPACITY))
        max_sleep = int(labels.get(RATE_LIMIT_MAX_SLEEP, DEFAULT_MAX_SLEEP))
        expiry = int(labels.get(RATE_LIMIT_EXPIRY, DEFAULT_EXPIRY))

        logger.debug(f"Acquiring rate limit: name={rate_limit_name}, capacity={capacity}")

        if message.task_id in self._active_semaphores:
            logger.warning(
                f"Semaphore leak prevented: task_id={message.task_id} already has active semaphore "
                f"for task={message.task_name}. Preserving original semaphore reference."
            )
            semaphore_leak_prevented_total.add(1, {"task_name": message.task_name})
            return message

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

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Args:
            attempt: Zero-based attempt number.

        Returns:
            Delay in seconds, guaranteed to be non-negative.
        """
        base_delay = max(0.0, RELEASE_BASE_DELAY)
        delay = min(base_delay * (2**attempt), RELEASE_MAX_DELAY)
        if RELEASE_JITTER > 0 and delay > 0:
            jitter = delay * random.uniform(-RELEASE_JITTER, RELEASE_JITTER)
            delay = max(0.0, delay + jitter)
        return delay

    async def _release_with_retry(self, semaphore: AsyncSemaphore, task_name: str) -> bool:
        """Release semaphore with retry logic and exponential backoff.

        Args:
            semaphore: The AsyncSemaphore to release.
            task_name: The task name for metric labels.

        Returns:
            True if release succeeded, False if all retries exhausted.
        """
        for attempt in range(RELEASE_MAX_ATTEMPTS):
            try:
                await semaphore.__aexit__(None, None, None)
                logger.debug(f"Released rate limit for task {task_name}")
                return True
            except Exception as e:
                if attempt < RELEASE_MAX_ATTEMPTS - 1:
                    wait_time = self._calculate_backoff_delay(attempt)
                    logger.debug(
                        f"Semaphore release attempt {attempt + 1}/{RELEASE_MAX_ATTEMPTS} "
                        f"failed for {task_name}: {e}. Retrying in {wait_time:.3f}s"
                    )
                    semaphore_release_retries_total.add(1, {"task_name": task_name})
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Semaphore release failed after {RELEASE_MAX_ATTEMPTS} attempts "
                        f"for task {task_name}: {e}"
                    )
        return False

    async def _release_semaphore(self, message: TaskiqMessage) -> None:
        semaphore = self._active_semaphores.pop(message.task_id, None)
        if semaphore:
            success = await self._release_with_retry(semaphore, message.task_name)
            if success:
                self._consecutive_release_failures = 0
            else:
                self._consecutive_release_failures += 1
                semaphore_release_failures_total.add(1, {"task_name": message.task_name})
                if self._consecutive_release_failures >= CONSECUTIVE_FAILURES_ALERT_THRESHOLD:
                    logger.error(
                        f"ALERT: {self._consecutive_release_failures} consecutive semaphore release "
                        f"failures detected. Most recent failure for task {message.task_name}. "
                        f"Redis connectivity may be degraded.",
                        extra={
                            "alert_type": "semaphore_release_failures",
                            "consecutive_failures": self._consecutive_release_failures,
                            "task_name": message.task_name,
                            "instance_id": self._instance_id,
                        },
                    )
