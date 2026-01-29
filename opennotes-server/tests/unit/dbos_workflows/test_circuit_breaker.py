"""Tests for DBOS workflow circuit breaker.

This circuit breaker is synchronous (for use in DBOS steps) and implements
the standard three-state pattern: CLOSED -> OPEN -> HALF_OPEN.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src.dbos_workflows.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreakerInitialization:
    """Tests for circuit breaker initialization."""

    def test_default_initialization(self) -> None:
        """Circuit breaker starts in CLOSED state with zero failures."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=60.0)

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failures == 0
        assert breaker.threshold == 5
        assert breaker.reset_timeout == 60.0
        assert breaker.last_failure_time is None

    def test_custom_threshold_and_timeout(self) -> None:
        """Circuit breaker accepts custom configuration."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=30.0)

        assert breaker.threshold == 3
        assert breaker.reset_timeout == 30.0


class TestCircuitBreakerClosedState:
    """Tests for circuit breaker in CLOSED state (normal operation)."""

    def test_check_allows_request_when_closed(self) -> None:
        """Check passes when circuit is closed."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=60.0)

        breaker.check()

    def test_record_success_resets_failures(self) -> None:
        """Recording success resets failure count."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=60.0)
        breaker.failures = 3
        breaker.last_failure_time = time.time()

        breaker.record_success()

        assert breaker.failures == 0
        assert breaker.last_failure_time is None
        assert breaker.state == CircuitState.CLOSED

    def test_record_failure_increments_count(self) -> None:
        """Recording failure increments failure count."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=60.0)

        breaker.record_failure()

        assert breaker.failures == 1
        assert breaker.last_failure_time is not None
        assert breaker.state == CircuitState.CLOSED

    def test_circuit_opens_at_threshold(self) -> None:
        """Circuit opens when failures reach threshold."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=60.0)

        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.failures == 3


class TestCircuitBreakerOpenState:
    """Tests for circuit breaker in OPEN state (failing fast)."""

    def test_check_raises_when_open(self) -> None:
        """Check raises CircuitOpenError when circuit is open."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=60.0)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check()

        assert "2 consecutive failures" in str(exc_info.value)
        assert "Reset in" in str(exc_info.value)

    def test_transitions_to_half_open_after_timeout(self) -> None:
        """Circuit transitions to HALF_OPEN after reset timeout."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=1.0)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        with patch("time.time") as mock_time:
            mock_time.return_value = breaker.last_failure_time + 2.0

            breaker.check()

        assert breaker.state == CircuitState.HALF_OPEN

    def test_is_open_property(self) -> None:
        """is_open property reflects OPEN state."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=60.0)
        assert breaker.is_open is False

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.is_open is True


class TestCircuitBreakerHalfOpenState:
    """Tests for circuit breaker in HALF_OPEN state (testing recovery)."""

    def test_success_in_half_open_closes_circuit(self) -> None:
        """Success in HALF_OPEN state closes the circuit."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=0.0)
        breaker.record_failure()
        breaker.record_failure()

        breaker.check()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failures == 0

    def test_failure_in_half_open_reopens_circuit(self) -> None:
        """Failure in HALF_OPEN state reopens the circuit."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=0.0)
        breaker.record_failure()
        breaker.record_failure()

        breaker.check()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerTimeCalculations:
    """Tests for time-related calculations."""

    def test_time_until_reset_when_open(self) -> None:
        """Calculate time remaining until reset attempt."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=60.0)
        breaker.record_failure()
        breaker.record_failure()

        with patch("time.time") as mock_time:
            mock_time.return_value = breaker.last_failure_time + 10.0
            remaining = breaker._time_until_reset()

        assert 49.0 <= remaining <= 51.0

    def test_time_until_reset_returns_zero_when_no_failure(self) -> None:
        """Time until reset is zero when no failures recorded."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=60.0)

        remaining = breaker._time_until_reset()

        assert remaining == 0.0

    def test_time_until_reset_returns_zero_when_timeout_exceeded(self) -> None:
        """Time until reset is zero when timeout has passed."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=60.0)
        breaker.record_failure()

        with patch("time.time") as mock_time:
            mock_time.return_value = breaker.last_failure_time + 120.0
            remaining = breaker._time_until_reset()

        assert remaining == 0.0


class TestCircuitOpenError:
    """Tests for CircuitOpenError exception."""

    def test_error_message_format(self) -> None:
        """CircuitOpenError message includes failure count and reset time."""
        error = CircuitOpenError(
            "Circuit open after 5 consecutive failures. Reset in 30.0s"
        )

        assert "5 consecutive failures" in str(error)
        assert "30.0s" in str(error)
