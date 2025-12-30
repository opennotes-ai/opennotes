"""
Unit tests for database retry utilities.

Tests the deadlock detection and retry logic for database operations.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from asyncpg.exceptions import DeadlockDetectedError
from sqlalchemy.exc import OperationalError

from src.common.db_retry import is_deadlock_error, with_deadlock_retry


class TestIsDeadlockError:
    """Tests for is_deadlock_error function."""

    def test_detects_asyncpg_deadlock_directly(self):
        """Detects DeadlockDetectedError directly."""
        exc = DeadlockDetectedError("")
        assert is_deadlock_error(exc) is True

    def test_detects_wrapped_asyncpg_deadlock(self):
        """Detects DeadlockDetectedError wrapped in OperationalError."""
        original = DeadlockDetectedError("")
        exc = OperationalError(statement="SELECT 1", params={}, orig=original)
        assert is_deadlock_error(exc) is True

    def test_detects_deadlock_by_pgcode(self):
        """Detects deadlock by PostgreSQL error code 40P01."""
        original = MagicMock()
        original.pgcode = "40P01"
        exc = OperationalError(statement="SELECT 1", params={}, orig=original)
        assert is_deadlock_error(exc) is True

    def test_returns_false_for_other_operational_errors(self):
        """Returns False for non-deadlock OperationalError."""
        original = MagicMock()
        original.pgcode = "23505"
        exc = OperationalError(statement="SELECT 1", params={}, orig=original)
        assert is_deadlock_error(exc) is False

    def test_returns_false_for_other_exceptions(self):
        """Returns False for unrelated exceptions."""
        assert is_deadlock_error(ValueError("test")) is False
        assert is_deadlock_error(RuntimeError("test")) is False


class TestWithDeadlockRetry:
    """Tests for with_deadlock_retry decorator."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Function succeeds without retry when no deadlock occurs."""
        call_count = 0

        @with_deadlock_retry(max_attempts=3)
        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_operation()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_deadlock_and_succeeds(self):
        """Retries on deadlock and eventually succeeds."""
        call_count = 0

        @with_deadlock_retry(max_attempts=3, base_delay=0.01)
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise DeadlockDetectedError("")
            return "success"

        result = await flaky_operation()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        """Raises exception after max retries are exhausted."""
        call_count = 0

        @with_deadlock_retry(max_attempts=3, base_delay=0.01)
        async def always_deadlocks():
            nonlocal call_count
            call_count += 1
            raise DeadlockDetectedError("")

        with pytest.raises(DeadlockDetectedError):
            await always_deadlocks()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_non_deadlock_errors(self):
        """Does not retry on non-deadlock exceptions."""
        call_count = 0

        @with_deadlock_retry(max_attempts=3)
        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not a deadlock")

        with pytest.raises(ValueError, match="not a deadlock"):
            await raises_value_error()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_uses_exponential_backoff(self):
        """Uses exponential backoff between retries."""
        call_count = 0
        call_times = []

        @with_deadlock_retry(max_attempts=3, base_delay=0.05, max_delay=1.0, jitter=0)
        async def track_timing():
            nonlocal call_count
            call_count += 1
            call_times.append(asyncio.get_event_loop().time())
            if call_count < 3:
                raise DeadlockDetectedError("")
            return "success"

        await track_timing()

        assert len(call_times) == 3

        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert delay1 >= 0.04
        assert delay2 >= 0.08
        assert delay2 > delay1

    @pytest.mark.asyncio
    async def test_respects_max_delay(self):
        """Respects max_delay cap on backoff."""
        call_count = 0
        call_times = []

        @with_deadlock_retry(max_attempts=5, base_delay=0.1, max_delay=0.15, jitter=0)
        async def track_timing():
            nonlocal call_count
            call_count += 1
            call_times.append(asyncio.get_event_loop().time())
            if call_count < 5:
                raise DeadlockDetectedError("")
            return "success"

        await track_timing()

        for i in range(1, len(call_times)):
            delay = call_times[i] - call_times[i - 1]
            assert delay <= 0.20

    @pytest.mark.asyncio
    async def test_preserves_function_return_value(self):
        """Preserves the return value of the wrapped function."""

        @with_deadlock_retry(max_attempts=3)
        async def return_dict():
            return {"key": "value", "count": 42}

        result = await return_dict()

        assert result == {"key": "value", "count": 42}

    @pytest.mark.asyncio
    async def test_preserves_function_arguments(self):
        """Preserves arguments passed to the wrapped function."""
        received_args = []

        @with_deadlock_retry(max_attempts=3, base_delay=0.01)
        async def capture_args(a, b, *, c=None):
            received_args.append((a, b, c))
            if len(received_args) < 2:
                raise DeadlockDetectedError("")
            return (a, b, c)

        result = await capture_args(1, "two", c="three")

        assert result == (1, "two", "three")
        assert all(args == (1, "two", "three") for args in received_args)

    @pytest.mark.asyncio
    async def test_logs_retry_attempts(self):
        """Logs retry attempts with appropriate details."""
        call_count = 0

        @with_deadlock_retry(max_attempts=3, base_delay=0.01)
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise DeadlockDetectedError("")
            return "success"

        with patch("src.common.db_retry.logger") as mock_logger:
            await flaky_operation()

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert "Deadlock detected, retrying" in call_args[0][0]
            assert call_args[1]["extra"]["function"] == "flaky_operation"
            assert call_args[1]["extra"]["attempt"] == 1
