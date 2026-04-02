import asyncio
from unittest.mock import patch

import pytest

from src.circuit_breaker_core import (
    AsyncCircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerCore,
    CircuitOpenError,
    CircuitState,
)


@pytest.mark.unit
class TestCircuitBreakerCoreStateTransitions:
    def test_initial_state_is_closed(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")
        assert core.state == CircuitState.CLOSED
        assert not core.is_open
        assert core.failures == 0

    def test_check_passes_when_closed(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")
        core.check()

    def test_failures_below_threshold_keep_circuit_closed(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")

        core.record_failure()
        assert core.failures == 1
        assert core.state == CircuitState.CLOSED

        core.record_failure()
        assert core.failures == 2
        assert core.state == CircuitState.CLOSED

    def test_threshold_failures_open_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")

        for _ in range(3):
            core.record_failure()

        assert core.state == CircuitState.OPEN
        assert core.is_open
        assert core.failures == 3

    def test_check_raises_when_open(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        for _ in range(3):
            core.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            core.check()

        assert "Circuit open after 3 consecutive failures" in str(exc_info.value)

    def test_circuit_enters_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(3):
                core.record_failure()
            assert core.state == CircuitState.OPEN

            mock_time.time.return_value = 1061.0
            core.check()
            assert core.state == CircuitState.HALF_OPEN

    def test_success_in_half_open_closes_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(3):
                core.record_failure()

            mock_time.time.return_value = 1061.0
            core.check()
            assert core.state == CircuitState.HALF_OPEN

            core.record_success()
            assert core.state == CircuitState.CLOSED
            assert core.failures == 0
            assert not core.is_open

    def test_failure_in_half_open_reopens_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(3):
                core.record_failure()

            mock_time.time.return_value = 1061.0
            core.check()
            assert core.state == CircuitState.HALF_OPEN

            mock_time.time.return_value = 1062.0
            core.record_failure()
            assert core.state == CircuitState.OPEN
            assert core.is_open

    def test_success_resets_failure_count(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")

        core.record_failure()
        core.record_failure()
        assert core.failures == 2

        core.record_success()
        assert core.failures == 0
        assert core.state == CircuitState.CLOSED


@pytest.mark.unit
class TestCircuitBreakerCoreConfiguration:
    def test_custom_threshold(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")

        for i in range(4):
            core.record_failure()
            assert core.state == CircuitState.CLOSED, f"Failed at failure {i + 1}"

        core.record_failure()
        assert core.state == CircuitState.OPEN

    def test_time_until_reset_calculation(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(3):
                core.record_failure()

            mock_time.time.return_value = 1000.5
            status = core.get_status()
            assert status["state"] == "open"

    def test_is_open_property(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=1)
        core = CircuitBreakerCore(config, name="test")

        assert not core.is_open

        core.record_failure()
        assert not core.is_open

        core.record_failure()
        assert core.is_open


@pytest.mark.unit
class TestCircuitBreakerCoreErrorMessages:
    def test_error_includes_failure_count(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        for _ in range(5):
            core.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            core.check()

        assert "5 consecutive failures" in str(exc_info.value)

    def test_error_includes_time_until_reset(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=30)
        core = CircuitBreakerCore(config, name="test")

        for _ in range(3):
            core.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            core.check()

        error_message = str(exc_info.value)
        assert "Reset in" in error_message


@pytest.mark.unit
class TestCircuitBreakerCoreExponentialBackoff:
    def test_no_backoff_by_default(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=10)
        core = CircuitBreakerCore(config, name="test")
        assert core.effective_reset_timeout == 10

    def test_no_backoff_with_rate_1(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=10, backoff_rate=1.0)
        core = CircuitBreakerCore(config, name="test")
        for _ in range(2):
            core.record_failure()
        status = core.get_status()
        assert status["open_count"] == 1
        assert core.effective_reset_timeout == 10

    def test_backoff_increases_after_reopen(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=10, backoff_rate=2.0)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(2):
                core.record_failure()
            assert core.get_status()["open_count"] == 1
            assert core.effective_reset_timeout == 10

            mock_time.time.return_value = 1011.0
            core.check()
            assert core.state == CircuitState.HALF_OPEN
            mock_time.time.return_value = 1012.0
            core.record_failure()
            assert core.get_status()["open_count"] == 2
            assert core.effective_reset_timeout == 20

            mock_time.time.return_value = 1033.0
            core.check()
            assert core.state == CircuitState.HALF_OPEN
            mock_time.time.return_value = 1034.0
            core.record_failure()
            assert core.get_status()["open_count"] == 3
            assert core.effective_reset_timeout == 40

    def test_backoff_capped_at_max(self):
        config = CircuitBreakerConfig(
            failure_threshold=2, reset_timeout=10, backoff_rate=2.0, max_reset_timeout=30
        )
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(2):
                core.record_failure()

            mock_time.time.return_value = 1011.0
            core.check()
            mock_time.time.return_value = 1012.0
            core.record_failure()

            mock_time.time.return_value = 1033.0
            core.check()
            mock_time.time.return_value = 1034.0
            core.record_failure()

            mock_time.time.return_value = 1065.0
            core.check()
            mock_time.time.return_value = 1066.0
            core.record_failure()

            assert core.effective_reset_timeout == 30

    def test_success_resets_open_count(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=10, backoff_rate=2.0)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(2):
                core.record_failure()
            assert core.get_status()["open_count"] == 1

            mock_time.time.return_value = 1011.0
            core.check()
            mock_time.time.return_value = 1012.0
            core.record_failure()
            assert core.get_status()["open_count"] == 2

            mock_time.time.return_value = 1033.0
            core.check()
            core.record_success()
            assert core.get_status()["open_count"] == 0
            assert core.effective_reset_timeout == 10

    def test_default_max_timeout_is_8x_base(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60, backoff_rate=2.0)
        core = CircuitBreakerCore(config, name="test")
        assert config.max_reset_timeout is None
        assert core._resolved_max_reset_timeout == 480


@pytest.mark.unit
class TestCircuitBreakerCoreGetStatus:
    def test_get_status_returns_expected_keys(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=30, backoff_rate=1.5)
        core = CircuitBreakerCore(config, name="my-breaker")

        status = core.get_status()
        assert status["name"] == "my-breaker"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 5
        assert status["timeout"] == 30
        assert status["last_failure_time"] is None
        assert status["open_count"] == 0
        assert status["backoff_rate"] == 1.5
        assert status["effective_reset_timeout"] == 30

    def test_get_status_after_failures(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            core.record_failure()
            core.record_failure()

            status = core.get_status()
            assert status["state"] == "open"
            assert status["failure_count"] == 2
            assert status["open_count"] == 1
            assert status["last_failure_time"] == 1000.0


@pytest.mark.unit
class TestCircuitBreakerCoreReset:
    def test_reset_returns_to_initial_state(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test")

        for _ in range(2):
            core.record_failure()
        assert core.state == CircuitState.OPEN

        core.reset()
        assert core.state == CircuitState.CLOSED
        assert core.failures == 0
        assert not core.is_open
        status = core.get_status()
        assert status["open_count"] == 0
        assert status["last_failure_time"] is None

    def test_reset_clears_backoff(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=10, backoff_rate=2.0)
        core = CircuitBreakerCore(config, name="test")

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0
            for _ in range(2):
                core.record_failure()

            mock_time.time.return_value = 1011.0
            core.check()
            mock_time.time.return_value = 1012.0
            core.record_failure()
            assert core.effective_reset_timeout == 20

            core.reset()
            assert core.effective_reset_timeout == 10


@pytest.mark.unit
class TestCircuitBreakerConfigDefaults:
    def test_default_values(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.reset_timeout == 60.0
        assert config.backoff_rate == 1.0
        assert config.max_reset_timeout is None

    def test_custom_values(self):
        config = CircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout=30.0,
            backoff_rate=2.0,
            max_reset_timeout=120.0,
        )
        assert config.failure_threshold == 10
        assert config.reset_timeout == 30.0
        assert config.backoff_rate == 2.0
        assert config.max_reset_timeout == 120.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncCircuitBreakerBasic:
    async def test_closed_state_passes_through(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-async")
        cb = AsyncCircuitBreaker(core)

        async def ok():
            return 42

        result = await cb.call(ok)
        assert result == 42

    async def test_opens_after_threshold_failures(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-async")
        cb = AsyncCircuitBreaker(core)

        async def fail():
            raise RuntimeError("boom")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(fail)

        assert core.state == CircuitState.OPEN

    async def test_rejects_when_open(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-async")
        cb = AsyncCircuitBreaker(core)

        async def fail():
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(fail)

        async def ok():
            return 1

        with pytest.raises(CircuitOpenError):
            await cb.call(ok)

    async def test_success_in_half_open_closes(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-async")
        cb = AsyncCircuitBreaker(core)

        with patch("src.circuit_breaker_core.time") as mock_time:
            mock_time.time.return_value = 1000.0

            async def fail():
                raise RuntimeError("boom")

            for _ in range(2):
                with pytest.raises(RuntimeError):
                    await cb.call(fail)
            assert core.state == CircuitState.OPEN

            mock_time.time.return_value = 1061.0

            async def ok():
                return "recovered"

            result = await cb.call(ok)
            assert result == "recovered"
            assert core.state == CircuitState.CLOSED
            assert core.failures == 0

    async def test_success_in_closed_resets_failure_count(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-async")
        cb = AsyncCircuitBreaker(core)

        async def fail():
            raise RuntimeError("boom")

        async def ok():
            return "ok"

        with pytest.raises(RuntimeError):
            await cb.call(fail)
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        assert core.failures == 2

        await cb.call(ok)
        assert core.failures == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncCircuitBreakerFailurePredicate:
    async def test_matching_exceptions_trip_breaker(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-pred")
        cb = AsyncCircuitBreaker(core, failure_predicate=lambda e: isinstance(e, ValueError))

        async def raise_value_error():
            raise ValueError("bad value")

        for _ in range(2):
            with pytest.raises(ValueError, match="bad value"):
                await cb.call(raise_value_error)

        assert core.state == CircuitState.OPEN

    async def test_non_matching_exceptions_do_not_trip(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-pred")
        cb = AsyncCircuitBreaker(core, failure_predicate=lambda e: isinstance(e, ValueError))

        async def raise_type_error():
            raise TypeError("wrong type")

        for _ in range(5):
            with pytest.raises(TypeError):
                await cb.call(raise_type_error)

        assert core.state == CircuitState.CLOSED
        assert core.failures == 0

    async def test_default_predicate_counts_all(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-pred-default")
        cb = AsyncCircuitBreaker(core)

        async def raise_key_error():
            raise KeyError("missing")

        for _ in range(2):
            with pytest.raises(KeyError):
                await cb.call(raise_key_error)

        assert core.state == CircuitState.OPEN


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncCircuitBreakerDecorator:
    async def test_call_decorator_wraps_function(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-decorator")
        cb = AsyncCircuitBreaker(core)

        @cb
        async def my_func(x: int, y: int) -> int:
            return x + y

        result = await my_func(3, 4)
        assert result == 7

    async def test_decorated_function_preserves_name(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-decorator")
        cb = AsyncCircuitBreaker(core)

        @cb
        async def my_named_func():
            return True

        assert my_named_func.__name__ == "my_named_func"

    async def test_decorated_function_records_failures(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-decorator")
        cb = AsyncCircuitBreaker(core)

        @cb
        async def failing_func():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await failing_func()

        assert core.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await failing_func()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncCircuitBreakerConcurrent:
    async def test_concurrent_calls_are_safe(self):
        config = CircuitBreakerConfig(failure_threshold=100, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-concurrent")
        cb = AsyncCircuitBreaker(core)

        call_count = 0

        async def increment():
            nonlocal call_count
            await asyncio.sleep(0.001)
            call_count += 1
            return call_count

        results = await asyncio.gather(*[cb.call(increment) for _ in range(50)])
        assert len(results) == 50
        assert call_count == 50

    async def test_concurrent_failures_respect_threshold(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-concurrent-fail")
        cb = AsyncCircuitBreaker(core)

        async def fail():
            await asyncio.sleep(0.001)
            raise RuntimeError("boom")

        tasks = [cb.call(fail) for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        runtime_errors = [r for r in results if isinstance(r, RuntimeError)]
        circuit_errors = [r for r in results if isinstance(r, CircuitOpenError)]
        assert len(runtime_errors) + len(circuit_errors) == 10
        assert core.state == CircuitState.OPEN


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncCircuitBreakerDelegation:
    async def test_name_delegates_to_core(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=60)
        core = CircuitBreakerCore(config, name="delegated-name")
        cb = AsyncCircuitBreaker(core)
        assert cb.name == "delegated-name"

    async def test_state_delegates_to_core(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-delegation")
        cb = AsyncCircuitBreaker(core)

        assert cb.state == CircuitState.CLOSED

        core.record_failure()
        core.record_failure()
        assert cb.state == CircuitState.OPEN

    async def test_failures_delegates_to_core(self):
        config = CircuitBreakerConfig(failure_threshold=5, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-delegation")
        cb = AsyncCircuitBreaker(core)

        assert cb.failures == 0
        core.record_failure()
        assert cb.failures == 1

    async def test_is_open_delegates_to_core(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-delegation")
        cb = AsyncCircuitBreaker(core)

        assert not cb.is_open
        core.record_failure()
        core.record_failure()
        assert cb.is_open

    async def test_get_status_delegates_to_core(self):
        config = CircuitBreakerConfig(failure_threshold=3, reset_timeout=30, backoff_rate=1.5)
        core = CircuitBreakerCore(config, name="status-test")
        cb = AsyncCircuitBreaker(core)

        status = cb.get_status()
        assert status["name"] == "status-test"
        assert status["state"] == "closed"
        assert status["failure_threshold"] == 3
        assert status["timeout"] == 30
        assert status["backoff_rate"] == 1.5


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncCircuitBreakerReset:
    async def test_reset_clears_state(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-reset")
        cb = AsyncCircuitBreaker(core)

        async def fail():
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(fail)

        assert cb.state == CircuitState.OPEN

        await cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failures == 0
        assert not cb.is_open

    async def test_reset_allows_calls_again(self):
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60)
        core = CircuitBreakerCore(config, name="test-reset")
        cb = AsyncCircuitBreaker(core)

        async def fail():
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(fail)

        with pytest.raises(CircuitOpenError):
            await cb.call(fail)

        await cb.reset()

        async def ok():
            return "back"

        result = await cb.call(ok)
        assert result == "back"
