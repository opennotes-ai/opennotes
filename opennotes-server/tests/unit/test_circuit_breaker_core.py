from unittest.mock import patch

import pytest

from src.circuit_breaker_core import (
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
