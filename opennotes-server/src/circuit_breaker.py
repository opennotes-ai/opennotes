import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from src.config import settings

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int | None = None,
        timeout: int | None = None,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold or settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.timeout = timeout or settings.CIRCUIT_BREAKER_TIMEOUT
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED
        self._lock = asyncio.Lock()

    def _should_attempt_reset(self) -> bool:
        if self.state == CircuitState.OPEN and self.last_failure_time:
            return time.time() - self.last_failure_time >= self.timeout
        return False

    def _record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        logger.info(f"Circuit breaker '{self.name}' reset to CLOSED state")

    def _record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker '{self.name}' OPENED after {self.failure_count} failures"
            )

    async def call(
        self,
        func: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN. Service unavailable."
                    )

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self._record_success()
                elif self.state == CircuitState.CLOSED and self.failure_count > 0:
                    self.failure_count = 0
            return result
        except self.expected_exception as e:
            async with self._lock:
                self._record_failure()
            raise e

    def __call__(
        self,
        func: Callable[P, Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await self.call(func, *args, **kwargs)

        return wrapper


class CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(
        self,
        name: str,
        failure_threshold: int | None = None,
        timeout: int | None = None,
        expected_exception: type[Exception] = Exception,
    ) -> CircuitBreaker:
        if name in self._breakers:
            existing = self._breakers[name]

            # Check if parameters differ from existing configuration
            requested_failure_threshold = (
                failure_threshold or settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
            )
            requested_timeout = timeout or settings.CIRCUIT_BREAKER_TIMEOUT

            if (
                requested_failure_threshold != existing.failure_threshold
                or requested_timeout != existing.timeout
                or expected_exception != existing.expected_exception
            ):
                logger.warning(
                    f"Circuit breaker '{name}' already exists with different configuration. "
                    f"Existing: failure_threshold={existing.failure_threshold}, timeout={existing.timeout}, "
                    f"exception={existing.expected_exception.__name__}. "
                    f"Requested: failure_threshold={requested_failure_threshold}, timeout={requested_timeout}, "
                    f"exception={expected_exception.__name__}. "
                    f"Ignoring new parameters and returning existing breaker."
                )
            return existing

        self._breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            timeout=timeout,
            expected_exception=expected_exception,
        )
        return self._breakers[name]

    def get_status(self, name: str) -> dict[str, Any]:
        if name not in self._breakers:
            return {"error": f"Circuit breaker '{name}' not found"}

        breaker = self._breakers[name]
        return {
            "name": breaker.name,
            "state": breaker.state.value,
            "failure_count": breaker.failure_count,
            "failure_threshold": breaker.failure_threshold,
            "timeout": breaker.timeout,
            "last_failure_time": breaker.last_failure_time,
        }

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        return {name: self.get_status(name) for name in self._breakers}

    async def reset(self, name: str) -> None:
        if name in self._breakers:
            breaker = self._breakers[name]
            async with breaker._lock:
                breaker.failure_count = 0
                breaker.state = CircuitState.CLOSED
                breaker.last_failure_time = None
                logger.info(f"Circuit breaker '{name}' manually reset")

    async def reset_all(self) -> None:
        for name in self._breakers:
            await self.reset(name)


circuit_breaker_registry = CircuitBreakerRegistry()
