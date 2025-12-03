"""
Unit tests for fail-closed token revocation behavior.

SECURITY: These tests verify that token revocation checks fail-closed,
meaning that when Redis is unavailable or the circuit breaker is open,
tokens are treated as revoked to prevent potentially compromised tokens
from being used during infrastructure failures.

This is a critical security feature - fail-open would allow revoked tokens
to be used when Redis is down.
"""

import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.auth.auth import is_token_revoked_check
from src.auth.profile_auth import (
    _is_token_revoked_check,
    create_profile_access_token,
    verify_profile_token,
)
from src.auth.revocation import (
    RevocationCheckFailedError,
    is_token_revoked,
    revocation_circuit_breaker,
)
from src.circuit_breaker import CircuitState
from src.users.profile_schemas import AuthProvider

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def reset_circuit_breaker():
    """Reset the circuit breaker to CLOSED state before each test."""
    async with revocation_circuit_breaker._lock:
        revocation_circuit_breaker.failure_count = 0
        revocation_circuit_breaker.state = CircuitState.CLOSED
        revocation_circuit_breaker.last_failure_time = None
    yield
    async with revocation_circuit_breaker._lock:
        revocation_circuit_breaker.failure_count = 0
        revocation_circuit_breaker.state = CircuitState.CLOSED
        revocation_circuit_breaker.last_failure_time = None


class TestRevocationCheckFailClosed:
    """Test that revocation checks fail-closed on errors."""

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_redis_error_raises_revocation_check_failed_error(self, mock_redis: AsyncMock):
        """When Redis fails, is_token_revoked should raise RevocationCheckFailedError."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        with pytest.raises(RevocationCheckFailedError) as exc_info:
            await is_token_revoked(token)

        assert "infrastructure error" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_is_token_revoked_check_returns_true_on_redis_error(self, mock_redis: AsyncMock):
        """is_token_revoked_check should return True (fail-closed) on Redis errors."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        result = await is_token_revoked_check(token)

        assert result is True

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_profile_is_token_revoked_check_returns_true_on_redis_error(
        self, mock_redis: AsyncMock
    ):
        """_is_token_revoked_check should return True (fail-closed) on Redis errors."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        result = await _is_token_revoked_check(token)

        assert result is True

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_verify_profile_token_returns_none_on_redis_error(self, mock_redis: AsyncMock):
        """Token verification should fail when revocation check fails."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        token_data = await verify_profile_token(token)

        assert token_data is None


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with revocation checks."""

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_circuit_breaker_opens_after_threshold_failures(self, mock_redis: AsyncMock):
        """Circuit breaker should open after reaching failure threshold."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        for _ in range(revocation_circuit_breaker.failure_threshold):
            try:
                await is_token_revoked(token)
            except RevocationCheckFailedError:
                pass

        assert revocation_circuit_breaker.state == CircuitState.OPEN
        assert (
            revocation_circuit_breaker.failure_count >= revocation_circuit_breaker.failure_threshold
        )

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_circuit_breaker_open_raises_error_immediately(self, mock_redis: AsyncMock):
        """When circuit is open, should raise error without calling Redis."""
        exists_mock = AsyncMock(side_effect=Exception("Redis connection refused"))
        mock_redis.exists = exists_mock

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        for _ in range(revocation_circuit_breaker.failure_threshold):
            try:
                await is_token_revoked(token)
            except RevocationCheckFailedError:
                pass

        assert revocation_circuit_breaker.state == CircuitState.OPEN

        initial_call_count = exists_mock.call_count

        with pytest.raises(RevocationCheckFailedError) as exc_info:
            await is_token_revoked(token)

        assert "circuit breaker open" in str(exc_info.value)
        assert exists_mock.call_count == initial_call_count

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_circuit_breaker_transitions_to_half_open_after_timeout(
        self, mock_redis: AsyncMock
    ):
        """Circuit should transition to half-open after timeout."""
        original_timeout = revocation_circuit_breaker.timeout
        revocation_circuit_breaker.timeout = 1

        try:
            mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

            profile_id = uuid4()
            token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

            for _ in range(revocation_circuit_breaker.failure_threshold):
                try:
                    await is_token_revoked(token)
                except RevocationCheckFailedError:
                    pass

            assert revocation_circuit_breaker.state == CircuitState.OPEN

            time.sleep(1.1)

            mock_redis.exists = AsyncMock(return_value=0)

            result = await is_token_revoked(token)

            assert result is False
            assert revocation_circuit_breaker.state == CircuitState.CLOSED

        finally:
            revocation_circuit_breaker.timeout = original_timeout

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_circuit_breaker_closes_after_successful_check(self, mock_redis: AsyncMock):
        """Circuit should close after successful check in half-open state."""
        original_timeout = revocation_circuit_breaker.timeout
        revocation_circuit_breaker.timeout = 1

        try:
            mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

            profile_id = uuid4()
            token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

            for _ in range(revocation_circuit_breaker.failure_threshold):
                try:
                    await is_token_revoked(token)
                except RevocationCheckFailedError:
                    pass

            assert revocation_circuit_breaker.state == CircuitState.OPEN

            time.sleep(1.1)

            mock_redis.exists = AsyncMock(return_value=0)

            await is_token_revoked(token)

            assert revocation_circuit_breaker.state == CircuitState.CLOSED
            assert revocation_circuit_breaker.failure_count == 0

        finally:
            revocation_circuit_breaker.timeout = original_timeout


class TestAlertingOnFailure:
    """Test that failures are logged at critical level for alerting."""

    @pytest.mark.asyncio
    @patch("src.auth.revocation.logger")
    @patch("src.auth.revocation.redis_client")
    async def test_redis_error_logs_critical_with_alert_tag(
        self, mock_redis: AsyncMock, mock_logger: AsyncMock
    ):
        """Redis errors should be logged at CRITICAL level with alert tag."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        try:
            await is_token_revoked(token)
        except RevocationCheckFailedError:
            pass

        mock_logger.critical.assert_called()
        call_kwargs = mock_logger.critical.call_args
        assert "extra" in call_kwargs.kwargs
        assert call_kwargs.kwargs["extra"]["alert"] == "revocation_check_failed"

    @pytest.mark.asyncio
    @patch("src.auth.revocation.logger")
    @patch("src.auth.revocation.redis_client")
    async def test_circuit_breaker_open_logs_critical_with_alert_tag(
        self, mock_redis: AsyncMock, mock_logger: AsyncMock
    ):
        """Circuit breaker open should be logged at CRITICAL level with alert tag."""
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis connection refused"))

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        for _ in range(revocation_circuit_breaker.failure_threshold):
            try:
                await is_token_revoked(token)
            except RevocationCheckFailedError:
                pass

        mock_logger.critical.reset_mock()

        try:
            await is_token_revoked(token)
        except RevocationCheckFailedError:
            pass

        mock_logger.critical.assert_called()
        call_kwargs = mock_logger.critical.call_args
        assert "circuit breaker OPEN" in call_kwargs.args[0]
        assert "extra" in call_kwargs.kwargs
        assert call_kwargs.kwargs["extra"]["alert"] == "revocation_check_failed"


class TestSuccessfulRevocationCheck:
    """Test that successful revocation checks work correctly."""

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_not_revoked_token_returns_false(self, mock_redis: AsyncMock):
        """Non-revoked token should return False."""
        mock_redis.exists = AsyncMock(return_value=0)

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        result = await is_token_revoked(token)

        assert result is False

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_revoked_token_returns_true(self, mock_redis: AsyncMock):
        """Revoked token should return True."""
        mock_redis.exists = AsyncMock(return_value=1)

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        result = await is_token_revoked(token)

        assert result is True

    @pytest.mark.asyncio
    @patch("src.auth.revocation.redis_client")
    async def test_success_resets_failure_count(self, mock_redis: AsyncMock):
        """Successful check should reset failure count."""
        mock_redis.exists = AsyncMock(return_value=0)

        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "test_user", AuthProvider.DISCORD.value)

        async with revocation_circuit_breaker._lock:
            revocation_circuit_breaker.failure_count = 2

        await is_token_revoked(token)

        assert revocation_circuit_breaker.failure_count == 0


class TestTokenWithoutJti:
    """Test handling of tokens without JTI claim."""

    @pytest.mark.asyncio
    @patch("src.auth.revocation.jwt.decode")
    async def test_token_without_jti_returns_false(self, mock_decode: AsyncMock):
        """Tokens without JTI should be considered not revoked."""
        mock_decode.return_value = {
            "sub": str(uuid4()),
            "display_name": "test_user",
            "provider": "discord",
        }

        result = await is_token_revoked("token_without_jti")

        assert result is False
