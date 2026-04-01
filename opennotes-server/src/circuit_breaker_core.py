from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    pass


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    reset_timeout: float = 60.0
    backoff_rate: float = 1.0
    max_reset_timeout: float | None = None


class CircuitBreakerCore:
    def __init__(self, config: CircuitBreakerConfig, name: str = "") -> None:
        self.config = config
        self.name = name
        self._failures = 0
        self._open_count = 0
        self._last_failure_time: float | None = None
        self._state = CircuitState.CLOSED
        self._resolved_max_reset_timeout = (
            config.max_reset_timeout
            if config.max_reset_timeout is not None
            else config.reset_timeout * 8
        )

    @property
    def effective_reset_timeout(self) -> float:
        if self.config.backoff_rate <= 1.0 or self._open_count <= 1:
            return self.config.reset_timeout
        timeout = self.config.reset_timeout * (self.config.backoff_rate ** (self._open_count - 1))
        return min(timeout, self._resolved_max_reset_timeout)

    @property
    def failures(self) -> int:
        return self._failures

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    def check(self) -> None:
        if self._state == CircuitState.CLOSED:
            return

        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit breaker entering half-open state",
                    extra={"circuit_breaker": self.name},
                )
                return
            raise CircuitOpenError(
                f"Circuit open after {self._failures} consecutive failures. "
                f"Reset in {self._time_until_reset():.1f}s"
            )

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                "Circuit breaker closing after successful test",
                extra={"circuit_breaker": self.name},
            )
        self._failures = 0
        self._open_count = 0
        self._last_failure_time = None
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._open_count += 1
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker reopening after failed test",
                extra={
                    "circuit_breaker": self.name,
                    "effective_reset_timeout": self.effective_reset_timeout,
                },
            )
            return

        if self._failures >= self.config.failure_threshold:
            self._open_count += 1
            self._state = CircuitState.OPEN
            logger.error(
                "Circuit breaker opened",
                extra={
                    "circuit_breaker": self.name,
                    "failures": self._failures,
                    "threshold": self.config.failure_threshold,
                },
            )

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failures,
            "failure_threshold": self.config.failure_threshold,
            "timeout": self.config.reset_timeout,
            "last_failure_time": self._last_failure_time,
            "open_count": self._open_count,
            "backoff_rate": self.config.backoff_rate,
            "effective_reset_timeout": self.effective_reset_timeout,
        }

    def reset(self) -> None:
        self._failures = 0
        self._open_count = 0
        self._last_failure_time = None
        self._state = CircuitState.CLOSED

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.effective_reset_timeout

    def _time_until_reset(self) -> float:
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.effective_reset_timeout - elapsed)


class AsyncCircuitBreaker:
    def __init__(
        self,
        core: CircuitBreakerCore,
        failure_predicate: Callable[[Exception], bool] | None = None,
    ) -> None:
        self._core = core
        self._failure_predicate = failure_predicate or (lambda e: True)
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._core.name

    @property
    def state(self) -> CircuitState:
        return self._core.state

    @property
    def failures(self) -> int:
        return self._core.failures

    @property
    def failure_count(self) -> int:
        return self._core.failures

    @property
    def is_open(self) -> bool:
        return self._core.is_open

    def get_status(self) -> dict[str, Any]:
        return self._core.get_status()

    async def call(self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs) -> T:
        async with self._lock:
            self._core.check()

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self._core.state == CircuitState.HALF_OPEN or (
                    self._core.state == CircuitState.CLOSED and self._core.failures > 0
                ):
                    self._core.record_success()
            return result
        except Exception as e:
            if self._failure_predicate(e):
                async with self._lock:
                    self._core.record_failure()
            raise

    async def reset(self) -> None:
        async with self._lock:
            self._core.reset()

    def __call__(self, func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await self.call(func, *args, **kwargs)

        return wrapper
