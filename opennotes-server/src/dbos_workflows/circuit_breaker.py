"""Circuit breaker for external service calls.

Trips after consecutive failures to prevent resource exhaustion
during extended outages.
"""

from __future__ import annotations

import time
from enum import Enum

from src.monitoring import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service failing, requests immediately rejected
    - HALF_OPEN: Testing recovery, one request allowed through

    Usage:
        breaker = CircuitBreaker(threshold=5, reset_timeout=60)
        try:
            breaker.check()
            result = call_external_service()
            breaker.record_success()
        except ServiceError:
            breaker.record_failure()
    """

    def __init__(
        self,
        threshold: int = 5,
        reset_timeout: float = 60.0,
    ):
        """Initialize circuit breaker.

        Args:
            threshold: Consecutive failures before opening circuit
            reset_timeout: Seconds before attempting reset (half-open)
        """
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED

    def check(self) -> None:
        """Check if circuit allows request. Raises CircuitOpenError if open."""
        if self.state == CircuitState.CLOSED:
            return

        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker entering half-open state")
                return
            raise CircuitOpenError(
                f"Circuit open after {self.failures} consecutive failures. "
                f"Reset in {self._time_until_reset():.1f}s"
            )

    def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker closing after successful test")

        self.failures = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call. May trip the circuit breaker."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker reopening after failed test")
            return

        if self.failures >= self.threshold:
            self.state = CircuitState.OPEN
            logger.error(
                "Circuit breaker opened",
                extra={
                    "failures": self.failures,
                    "threshold": self.threshold,
                },
            )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.reset_timeout

    def _time_until_reset(self) -> float:
        """Calculate seconds until reset attempt."""
        if self.last_failure_time is None:
            return 0.0
        elapsed = time.time() - self.last_failure_time
        return max(0.0, self.reset_timeout - elapsed)

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting calls)."""
        return self.state == CircuitState.OPEN
