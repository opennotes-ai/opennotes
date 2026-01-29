import asyncio
import time
from unittest.mock import patch

import pytest

from src.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_circuit_breaker_closed_state():
    breaker = CircuitBreaker(name="test", failure_threshold=3, timeout=5)
    assert breaker.state == CircuitState.CLOSED

    async def working_function() -> str:
        return "success"

    result = await breaker.call(working_function)
    assert result == "success"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    breaker = CircuitBreaker(name="test", failure_threshold=3, timeout=5)

    async def failing_function() -> None:
        raise Exception("Service unavailable")

    for _ in range(3):
        with pytest.raises(Exception, match="Service unavailable"):
            await breaker.call(failing_function)

    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count >= 3


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_when_open():
    breaker = CircuitBreaker(name="test", failure_threshold=2, timeout=60)

    async def failing_function() -> None:
        raise Exception("Error")

    for _ in range(2):
        with pytest.raises(Exception, match="Error"):
            await breaker.call(failing_function)

    assert breaker.state == CircuitState.OPEN

    async def working_function() -> str:
        return "success"

    with pytest.raises(CircuitBreakerError):
        await breaker.call(working_function)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    breaker = CircuitBreaker(name="test", failure_threshold=2, timeout=1)

    async def failing_function() -> None:
        raise Exception("Error")

    for _ in range(2):
        with pytest.raises(Exception, match="Error"):
            await breaker.call(failing_function)

    assert breaker.state == CircuitState.OPEN

    await asyncio.sleep(1.1)

    async def working_function() -> str:
        return "success"

    result = await breaker.call(working_function)
    assert result == "success"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_decorator():
    breaker = CircuitBreaker(name="test_decorator", failure_threshold=2, timeout=5)

    @breaker
    async def decorated_function(x: int) -> int:
        if x < 0:
            raise ValueError("Negative value")
        return x * 2

    result = await decorated_function(5)
    assert result == 10

    for _ in range(2):
        with pytest.raises(ValueError, match="Negative value"):
            await decorated_function(-1)

    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets_count():
    breaker = CircuitBreaker(name="test", failure_threshold=3, timeout=5)

    async def sometimes_failing(should_fail: bool) -> str:
        if should_fail:
            raise Exception("Failed")
        return "success"

    with pytest.raises(Exception, match="Failed"):
        await breaker.call(sometimes_failing, True)
    assert breaker.failure_count == 1

    result = await breaker.call(sometimes_failing, False)
    assert result == "success"
    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_concurrent_failures():
    breaker = CircuitBreaker(name="test_concurrent", failure_threshold=10, timeout=5)

    async def failing_function() -> None:
        raise Exception("Concurrent failure")

    tasks = [breaker.call(failing_function) for _ in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(isinstance(r, Exception) for r in results)
    assert breaker.failure_count == 10
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_concurrent_mixed_results():
    breaker = CircuitBreaker(name="test_mixed", failure_threshold=5, timeout=5)

    async def sometimes_failing(should_fail: bool) -> str:
        if should_fail:
            raise Exception("Failed")
        return "success"

    tasks = [breaker.call(sometimes_failing, i % 2 == 0) for i in range(4)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if r == "success"]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 2
    assert len(failures) == 2
    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_concurrent_race_to_open():
    breaker = CircuitBreaker(name="test_race", failure_threshold=5, timeout=5)

    async def failing_function() -> None:
        raise Exception("Race failure")

    tasks = [breaker.call(failing_function) for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    circuit_breaker_errors = sum(1 for r in results if isinstance(r, CircuitBreakerError))
    regular_errors = sum(
        1 for r in results if isinstance(r, Exception) and not isinstance(r, CircuitBreakerError)
    )

    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count >= 5
    assert regular_errors >= 5
    assert circuit_breaker_errors > 0


@pytest.mark.asyncio
async def test_circuit_breaker_concurrent_half_open_transitions():
    breaker = CircuitBreaker(name="test_half_open", failure_threshold=2, timeout=1)

    async def failing_function() -> None:
        raise Exception("Initial failure")

    for _ in range(2):
        with pytest.raises(Exception, match="Initial failure"):
            await breaker.call(failing_function)

    assert breaker.state == CircuitState.OPEN

    await asyncio.sleep(1.1)

    async def working_function() -> str:
        return "recovered"

    tasks = [breaker.call(working_function) for _ in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if r == "recovered"]
    assert len(successes) > 0
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry (T031)."""

    def test_registry_creates_new_breaker(self) -> None:
        """Test that registry creates new breakers on first request."""
        registry = CircuitBreakerRegistry()

        breaker = registry.get_breaker(
            name="test_breaker",
            failure_threshold=5,
            timeout=30,
        )

        assert breaker.name == "test_breaker"
        assert breaker.failure_threshold == 5
        assert breaker.timeout == 30

    def test_registry_returns_same_breaker(self) -> None:
        """Test that registry returns existing breaker for same name."""
        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_breaker(name="shared", failure_threshold=5, timeout=30)
        breaker2 = registry.get_breaker(name="shared", failure_threshold=5, timeout=30)

        assert breaker1 is breaker2

    def test_registry_warns_on_config_mismatch(self) -> None:
        """Test that registry warns when config differs for existing breaker."""
        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_breaker(name="config_test", failure_threshold=5, timeout=30)

        with patch("src.circuit_breaker.logger") as mock_logger:
            breaker2 = registry.get_breaker(name="config_test", failure_threshold=10, timeout=60)

            mock_logger.warning.assert_called_once()
            assert breaker1 is breaker2
            assert breaker2.failure_threshold == 5

    def test_registry_get_status(self) -> None:
        """Test that registry returns correct breaker status."""
        registry = CircuitBreakerRegistry()
        registry.get_breaker(name="status_test", failure_threshold=3, timeout=10)

        status = registry.get_status("status_test")

        assert status["name"] == "status_test"
        assert status["state"] == CircuitState.CLOSED.value
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 3
        assert status["timeout"] == 10

    def test_registry_get_status_not_found(self) -> None:
        """Test that registry returns error for unknown breaker."""
        registry = CircuitBreakerRegistry()

        status = registry.get_status("nonexistent")

        assert "error" in status
        assert "not found" in status["error"]

    def test_registry_get_all_status(self) -> None:
        """Test that registry returns status for all breakers."""
        registry = CircuitBreakerRegistry()
        registry.get_breaker(name="breaker_a", failure_threshold=3, timeout=10)
        registry.get_breaker(name="breaker_b", failure_threshold=5, timeout=20)

        all_status = registry.get_all_status()

        assert len(all_status) == 2
        assert "breaker_a" in all_status
        assert "breaker_b" in all_status
        assert all_status["breaker_a"]["failure_threshold"] == 3
        assert all_status["breaker_b"]["failure_threshold"] == 5

    @pytest.mark.asyncio
    async def test_registry_reset_breaker(self) -> None:
        """Test that registry can reset a specific breaker."""
        registry = CircuitBreakerRegistry()
        breaker = registry.get_breaker(name="reset_test", failure_threshold=3, timeout=10)

        breaker.failure_count = 5
        breaker.state = CircuitState.OPEN
        breaker.last_failure_time = time.time()

        await registry.reset("reset_test")

        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED
        assert breaker.last_failure_time is None

    @pytest.mark.asyncio
    async def test_registry_reset_all(self) -> None:
        """Test that registry can reset all breakers."""
        registry = CircuitBreakerRegistry()
        breaker1 = registry.get_breaker(name="reset_all_1", failure_threshold=3, timeout=10)
        breaker2 = registry.get_breaker(name="reset_all_2", failure_threshold=3, timeout=10)

        breaker1.state = CircuitState.OPEN
        breaker1.failure_count = 3
        breaker2.state = CircuitState.OPEN
        breaker2.failure_count = 3

        await registry.reset_all()

        assert breaker1.state == CircuitState.CLOSED
        assert breaker1.failure_count == 0
        assert breaker2.state == CircuitState.CLOSED
        assert breaker2.failure_count == 0


class TestCircuitBreakerCustomException:
    """Tests for circuit breaker with custom expected exception (T031)."""

    @pytest.mark.asyncio
    async def test_custom_exception_triggers_failure(self) -> None:
        """Test that custom exception type triggers failure count."""

        class CustomError(Exception):
            pass

        breaker = CircuitBreaker(
            name="custom_exc",
            failure_threshold=2,
            timeout=1,
            expected_exception=CustomError,
        )

        async def raising_custom() -> str:
            raise CustomError("Custom error")

        for _ in range(2):
            with pytest.raises(CustomError):
                await breaker.call(raising_custom)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_non_expected_exception_passes_through(self) -> None:
        """Test that non-expected exceptions don't trigger failure count."""

        class CustomError(Exception):
            pass

        breaker = CircuitBreaker(
            name="non_custom",
            failure_threshold=2,
            timeout=1,
            expected_exception=CustomError,
        )

        async def raising_other() -> str:
            raise ValueError("Other error")

        with pytest.raises(ValueError, match="Other error"):
            await breaker.call(raising_other)

        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerHalfOpenFailure:
    """Tests for half-open state failure handling (T031)."""

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens_circuit(self) -> None:
        """Test that failure in HALF_OPEN state reopens the circuit."""
        breaker = CircuitBreaker(name="half_open_fail", failure_threshold=2, timeout=1)

        async def failing_func() -> str:
            raise ValueError("Test error")

        for _ in range(2):
            with pytest.raises(ValueError, match="Test error"):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        await asyncio.sleep(1.1)

        with pytest.raises(ValueError, match="Test error"):
            await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count >= 1
