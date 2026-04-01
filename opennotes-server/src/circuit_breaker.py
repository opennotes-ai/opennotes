"""Circuit breaker -- thin facade over circuit_breaker_core.

All implementation lives in src.circuit_breaker_core. This module provides
backward-compatible imports and the registry singleton.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.circuit_breaker_core import (
    AsyncCircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerCore,
    CircuitOpenError,
    CircuitState,
)
from src.config import settings

logger = logging.getLogger(__name__)

CircuitBreakerError = CircuitOpenError

__all__ = [
    "AsyncCircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerCore",
    "CircuitBreakerError",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "CircuitState",
    "circuit_breaker_registry",
]


class CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._breakers: dict[str, AsyncCircuitBreaker] = {}

    def get_breaker(
        self,
        name: str,
        failure_threshold: int | None = None,
        timeout: int | None = None,
        expected_exception: type[Exception] = Exception,
        failure_predicate: Callable[[Exception], bool] | None = None,
        backoff_rate: float = 1.0,
        max_reset_timeout: float | None = None,
    ) -> AsyncCircuitBreaker:
        if name in self._breakers:
            existing = self._breakers[name]
            existing_status = existing.get_status()

            requested_failure_threshold = (
                failure_threshold or settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
            )
            requested_timeout = timeout or settings.CIRCUIT_BREAKER_TIMEOUT

            if (
                requested_failure_threshold != existing_status["failure_threshold"]
                or requested_timeout != existing_status["timeout"]
            ):
                logger.warning(
                    "Circuit breaker already exists with different configuration",
                    extra={
                        "circuit_breaker": name,
                        "existing_failure_threshold": existing_status["failure_threshold"],
                        "existing_timeout": existing_status["timeout"],
                        "requested_failure_threshold": requested_failure_threshold,
                        "requested_timeout": requested_timeout,
                    },
                )
            return existing

        if failure_predicate is None:
            exc_type = expected_exception

            def failure_predicate(e: Exception, _t: type[Exception] = exc_type) -> bool:
                return isinstance(e, _t)

        config = CircuitBreakerConfig(
            failure_threshold=failure_threshold or settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            reset_timeout=float(timeout or settings.CIRCUIT_BREAKER_TIMEOUT),
            backoff_rate=backoff_rate,
            max_reset_timeout=max_reset_timeout,
        )
        core = CircuitBreakerCore(config=config, name=name)
        breaker = AsyncCircuitBreaker(core=core, failure_predicate=failure_predicate)
        self._breakers[name] = breaker
        return breaker

    def get_status(self, name: str) -> dict[str, Any]:
        if name not in self._breakers:
            return {"error": f"Circuit breaker '{name}' not found"}
        return self._breakers[name].get_status()

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        return {name: self.get_status(name) for name in self._breakers}

    async def reset(self, name: str) -> None:
        if name in self._breakers:
            await self._breakers[name].reset()
            logger.info(
                "Circuit breaker manually reset",
                extra={"circuit_breaker": name},
            )

    async def reset_all(self) -> None:
        for name in self._breakers:
            await self.reset(name)


circuit_breaker_registry = CircuitBreakerRegistry()
