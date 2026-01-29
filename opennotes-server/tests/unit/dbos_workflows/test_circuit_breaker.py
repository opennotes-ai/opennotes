"""Unit tests for circuit breaker pattern (T031).

Tests verify:
- Circuit breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Threshold-based circuit opening
- Reset timeout behavior
- CircuitOpenError raising when circuit is open
"""

import time

import pytest

from src.dbos_workflows.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


@pytest.mark.unit
class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state machine transitions."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=1)
        assert breaker.state == CircuitState.CLOSED
        assert not breaker.is_open
        assert breaker.failures == 0

    def test_check_passes_when_closed(self):
        """Check passes without exception when circuit is closed."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=1)
        breaker.check()

    def test_failures_below_threshold_keep_circuit_closed(self):
        """Circuit remains closed when failures are below threshold."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=1)

        breaker.record_failure()
        assert breaker.failures == 1
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()
        assert breaker.failures == 2
        assert breaker.state == CircuitState.CLOSED

    def test_threshold_failures_open_circuit(self):
        """Circuit opens after reaching failure threshold."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=1)

        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open
        assert breaker.failures == 3

    def test_check_raises_when_open(self):
        """Check raises CircuitOpenError when circuit is open."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=60)

        for _ in range(3):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check()

        assert "Circuit open after 3 consecutive failures" in str(exc_info.value)

    def test_circuit_enters_half_open_after_timeout(self):
        """Circuit enters HALF_OPEN state after reset timeout."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=0.1)

        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        time.sleep(0.15)

        breaker.check()
        assert breaker.state == CircuitState.HALF_OPEN

    def test_success_in_half_open_closes_circuit(self):
        """Success in HALF_OPEN state closes the circuit."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=0.1)

        for _ in range(3):
            breaker.record_failure()

        time.sleep(0.15)

        breaker.check()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failures == 0
        assert not breaker.is_open

    def test_failure_in_half_open_reopens_circuit(self):
        """Failure in HALF_OPEN state reopens the circuit."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=0.1)

        for _ in range(3):
            breaker.record_failure()

        time.sleep(0.15)

        breaker.check()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open

    def test_success_resets_failure_count(self):
        """Recording success resets the failure count."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=1)

        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failures == 2

        breaker.record_success()
        assert breaker.failures == 0
        assert breaker.state == CircuitState.CLOSED


@pytest.mark.unit
class TestCircuitBreakerConfiguration:
    """Test circuit breaker configuration options."""

    def test_custom_threshold(self):
        """Circuit breaker respects custom threshold."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=1)

        for i in range(4):
            breaker.record_failure()
            assert breaker.state == CircuitState.CLOSED, f"Failed at failure {i + 1}"

        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_time_until_reset_calculation(self):
        """Time until reset is calculated correctly."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=60)

        for _ in range(3):
            breaker.record_failure()

        time_until_reset = breaker._time_until_reset()
        assert 59 < time_until_reset <= 60

    def test_is_open_property(self):
        """is_open property reflects circuit state correctly."""
        breaker = CircuitBreaker(threshold=2, reset_timeout=1)

        assert not breaker.is_open

        breaker.record_failure()
        assert not breaker.is_open

        breaker.record_failure()
        assert breaker.is_open


@pytest.mark.unit
class TestCircuitBreakerErrorMessages:
    """Test circuit breaker error messaging."""

    def test_error_includes_failure_count(self):
        """CircuitOpenError message includes failure count."""
        breaker = CircuitBreaker(threshold=5, reset_timeout=60)

        for _ in range(5):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check()

        assert "5 consecutive failures" in str(exc_info.value)

    def test_error_includes_time_until_reset(self):
        """CircuitOpenError message includes time until reset."""
        breaker = CircuitBreaker(threshold=3, reset_timeout=30)

        for _ in range(3):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check()

        error_message = str(exc_info.value)
        assert "Reset in" in error_message
