import asyncio

import pytest

from src.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState

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
