"""
Unit tests for Discord claims JWT creation and validation.

Security fix for task-682: Authentication bypass via X-Discord-Has-Manage-Server header
"""

import pendulum
import pytest


@pytest.mark.unit
class TestDiscordClaims:
    """Unit tests for discord_claims module."""

    def test_create_valid_claims_token(self) -> None:
        """Test creating a valid Discord claims JWT."""
        from src.auth.discord_claims import create_discord_claims_token, validate_discord_claims

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=True,
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

        claims = validate_discord_claims(token)
        assert claims is not None
        assert claims["user_id"] == "123456789"
        assert claims["guild_id"] == "987654321"
        assert claims["has_manage_server"] is True

    def test_create_token_without_manage_server(self) -> None:
        """Test creating a token with has_manage_server=False."""
        from src.auth.discord_claims import create_discord_claims_token, validate_discord_claims

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=False,
        )

        claims = validate_discord_claims(token)
        assert claims is not None
        assert claims["has_manage_server"] is False

    def test_invalid_token_returns_none(self) -> None:
        """Test that invalid tokens return None."""
        from src.auth.discord_claims import validate_discord_claims

        claims = validate_discord_claims("invalid.jwt.token")
        assert claims is None

    def test_empty_token_returns_none(self) -> None:
        """Test that empty token returns None."""
        from src.auth.discord_claims import validate_discord_claims

        assert validate_discord_claims("") is None
        assert validate_discord_claims(None) is None  # type: ignore

    def test_tampered_token_returns_none(self) -> None:
        """Test that tampered tokens return None."""
        from src.auth.discord_claims import create_discord_claims_token, validate_discord_claims

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=True,
        )

        parts = token.split(".")
        tampered_token = parts[0] + "." + parts[1] + ".tamperedsignature"

        claims = validate_discord_claims(tampered_token)
        assert claims is None

    def test_expired_token_returns_none(self) -> None:
        """Test that expired tokens return None."""
        from src.auth.discord_claims import (
            create_discord_claims_token,
            validate_discord_claims,
        )

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=True,
            expires_delta=pendulum.duration(seconds=-60),
        )

        claims = validate_discord_claims(token)
        assert claims is None

    def test_invalid_user_id_type_returns_none(self) -> None:
        """Test that token with non-string user_id returns None."""
        import jwt

        from src.auth.discord_claims import validate_discord_claims
        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "discord_claims",
            "user_id": 123456789,
            "guild_id": "987654321",
            "has_manage_server": True,
            "iat": now,
            "exp": now,
        }

        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        claims = validate_discord_claims(token)
        assert claims is None

    def test_invalid_guild_id_type_returns_none(self) -> None:
        """Test that token with non-string guild_id returns None."""
        import jwt

        from src.auth.discord_claims import validate_discord_claims
        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "discord_claims",
            "user_id": "123456789",
            "guild_id": 987654321,
            "has_manage_server": True,
            "iat": now,
            "exp": now,
        }

        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        claims = validate_discord_claims(token)
        assert claims is None

    def test_invalid_has_manage_server_type_returns_none(self) -> None:
        """Test that token with non-boolean has_manage_server returns None."""
        import jwt

        from src.auth.discord_claims import validate_discord_claims
        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "discord_claims",
            "user_id": "123456789",
            "guild_id": "987654321",
            "has_manage_server": "true",
            "iat": now,
            "exp": now,
        }

        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        claims = validate_discord_claims(token)
        assert claims is None


@pytest.mark.unit
class TestGetDiscordManageServerFromRequest:
    """Unit tests for get_discord_manage_server_from_request."""

    def test_with_valid_claims_header(self) -> None:
        """Test extraction from valid X-Discord-Claims header."""
        from src.auth.discord_claims import (
            create_discord_claims_token,
            get_discord_manage_server_from_request,
        )

        token = create_discord_claims_token(
            user_id="123",
            guild_id="456",
            has_manage_server=True,
        )

        headers = {"x-discord-claims": token}
        result = get_discord_manage_server_from_request(headers)
        assert result is True

    def test_with_valid_claims_header_no_permission(self) -> None:
        """Test extraction when has_manage_server is False."""
        from src.auth.discord_claims import (
            create_discord_claims_token,
            get_discord_manage_server_from_request,
        )

        token = create_discord_claims_token(
            user_id="123",
            guild_id="456",
            has_manage_server=False,
        )

        headers = {"x-discord-claims": token}
        result = get_discord_manage_server_from_request(headers)
        assert result is False

    def test_without_claims_header(self) -> None:
        """Test that missing header returns False."""
        from src.auth.discord_claims import get_discord_manage_server_from_request

        headers: dict[str, str] = {}
        result = get_discord_manage_server_from_request(headers)
        assert result is False

    def test_with_invalid_claims_header(self) -> None:
        """Test that invalid JWT returns False."""
        from src.auth.discord_claims import get_discord_manage_server_from_request

        headers = {"x-discord-claims": "invalid.jwt.token"}
        result = get_discord_manage_server_from_request(headers)
        assert result is False

    def test_raw_has_manage_server_header_ignored(self) -> None:
        """
        Test that raw X-Discord-Has-Manage-Server header is IGNORED.

        This is the key security fix for task-682. The function should
        only trust signed JWT claims, not raw headers.
        """
        from src.auth.discord_claims import get_discord_manage_server_from_request

        headers = {"x-discord-has-manage-server": "true"}
        result = get_discord_manage_server_from_request(headers)
        assert result is False


@pytest.mark.unit
class TestHeaderProtection:
    """Unit tests for header protection logic."""

    def test_protected_header_is_stripped(self) -> None:
        """Test that X-Discord-Has-Manage-Server is a protected header."""
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"x-discord-has-manage-server") is True
        assert _is_protected_header(b"X-Discord-Has-Manage-Server") is True
        assert _is_protected_header(b"x-discord-user-id") is True
        assert _is_protected_header(b"x-guild-id") is True

    def test_discord_claims_header_is_allowed(self) -> None:
        """Test that X-Discord-Claims is NOT protected (allowed through)."""
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"x-discord-claims") is False
        assert _is_protected_header(b"X-Discord-Claims") is False

    def test_regular_headers_are_not_protected(self) -> None:
        """Test that regular headers are not protected."""
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"content-type") is False
        assert _is_protected_header(b"authorization") is False
        assert _is_protected_header(b"x-request-id") is False
