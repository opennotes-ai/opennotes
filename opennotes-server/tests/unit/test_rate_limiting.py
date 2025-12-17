"""Unit tests for rate limiting middleware.

Tests focus on the get_user_identifier function which extracts user identity
from JWT tokens for rate limiting purposes.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from jose import jwt

from src.config import settings


class TestGetUserIdentifier:
    """Tests for the get_user_identifier function."""

    def _create_valid_token(self, user_id: str | None = None) -> str:
        """Create a valid JWT token for testing."""
        if user_id is None:
            user_id = str(uuid4())
        payload = {
            "sub": user_id,
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }
        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    def _create_mock_request(self, auth_header: str | None = None) -> MagicMock:
        """Create a mock request object with optional auth header."""
        request = MagicMock()
        headers = {}
        if auth_header:
            headers["authorization"] = auth_header
        request.headers.get = lambda key, default=None: headers.get(key, default)
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        return request

    def test_returns_ip_when_no_auth_header(self):
        """When no auth header is present, should return IP-based identifier."""
        from src.middleware.rate_limiting import get_user_identifier

        request = self._create_mock_request()
        result = get_user_identifier(request)
        assert result.startswith("ip:")

    def test_returns_ip_when_invalid_auth_header_format(self):
        """When auth header doesn't start with 'Bearer ', should return IP."""
        from src.middleware.rate_limiting import get_user_identifier

        request = self._create_mock_request(auth_header="Basic abc123")
        result = get_user_identifier(request)
        assert result.startswith("ip:")

    def test_returns_user_id_for_valid_token(self):
        """When valid token is provided, should return user-based identifier."""
        from src.middleware.rate_limiting import get_user_identifier

        user_id = str(uuid4())
        token = self._create_valid_token(user_id)
        request = self._create_mock_request(auth_header=f"Bearer {token}")

        result = get_user_identifier(request)

        assert result == f"user:{user_id}"

    def test_returns_ip_for_expired_token(self):
        """When token is expired, should fall back to IP-based identifier."""
        from src.middleware.rate_limiting import get_user_identifier

        payload = {
            "sub": str(uuid4()),
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
        }
        expired_token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        request = self._create_mock_request(auth_header=f"Bearer {expired_token}")

        result = get_user_identifier(request)

        assert result.startswith("ip:")

    def test_returns_ip_for_invalid_token(self):
        """When token is malformed, should fall back to IP-based identifier."""
        from src.middleware.rate_limiting import get_user_identifier

        request = self._create_mock_request(auth_header="Bearer invalid.token.here")
        result = get_user_identifier(request)
        assert result.startswith("ip:")

    def test_returns_ip_when_token_missing_sub_claim(self):
        """When token has no 'sub' claim, should fall back to IP."""
        from src.middleware.rate_limiting import get_user_identifier

        payload = {
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }
        token_without_sub = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        request = self._create_mock_request(auth_header=f"Bearer {token_without_sub}")

        result = get_user_identifier(request)

        assert result.startswith("ip:")

    def test_works_in_async_context_without_runtime_error(self):
        """
        CRITICAL TEST: The function must work when called from an async context
        where the event loop is already running (FastAPI middleware scenario).

        This test ensures we don't get "This event loop is already running" or
        "Task got Future attached to a different loop" errors.
        """
        from src.middleware.rate_limiting import get_user_identifier

        user_id = str(uuid4())
        token = self._create_valid_token(user_id)
        request = self._create_mock_request(auth_header=f"Bearer {token}")

        async def simulate_fastapi_middleware():
            """Simulate being called from FastAPI middleware (async context)."""
            return get_user_identifier(request)

        result = asyncio.run(simulate_fastapi_middleware())
        assert result == f"user:{user_id}"

    def test_no_async_imports_in_module(self):
        """
        Verify that rate_limiting module does NOT import asyncio.

        The function should use synchronous jwt.decode only, avoiding the
        problematic run_until_complete call which fails when loop is running.
        """
        import src.middleware.rate_limiting as rate_limiting_module

        assert not hasattr(rate_limiting_module, "asyncio"), (
            "rate_limiting module should not import asyncio - use synchronous jwt.decode only"
        )

    def test_no_verify_token_import_in_module(self):
        """
        Verify that rate_limiting module does NOT import verify_token.

        For rate limiting, we only need the user ID from the token - we don't
        need full token verification with revocation checks.
        """
        import src.middleware.rate_limiting as rate_limiting_module

        assert not hasattr(rate_limiting_module, "verify_token"), (
            "rate_limiting module should not import verify_token - "
            "use synchronous jwt.decode for rate limiting"
        )


class TestGetClientIp:
    """Tests for the get_client_ip function."""

    def test_uses_x_forwarded_for_header(self):
        """Should extract IP from X-Forwarded-For header."""
        from src.middleware.rate_limiting import get_client_ip

        request = MagicMock()
        request.headers.get = lambda key, default=None: {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}.get(
            key, default
        )
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        result = get_client_ip(request)

        assert result == "1.2.3.4"

    def test_uses_x_real_ip_header_as_fallback(self):
        """Should use X-Real-IP if X-Forwarded-For is not present."""
        from src.middleware.rate_limiting import get_client_ip

        request = MagicMock()
        request.headers.get = lambda key, default=None: {"x-real-ip": "10.20.30.40"}.get(
            key, default
        )
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        result = get_client_ip(request)

        assert result == "10.20.30.40"

    def test_falls_back_to_remote_address(self):
        """Should fall back to remote address if no proxy headers."""
        from src.middleware.rate_limiting import get_client_ip

        request = MagicMock()
        request.headers.get = lambda key, default=None: None
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        result = get_client_ip(request)

        assert result == "192.168.1.1"
