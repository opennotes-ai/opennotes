import pendulum
import pytest


@pytest.mark.unit
class TestPlatformClaims:
    def test_create_valid_claims_token(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

        claims = validate_platform_claims(token)
        assert claims is not None
        assert claims["platform"] == "discord"
        assert claims["scope"] == "*"
        assert claims["sub"] == "123456789"
        assert claims["community_id"] == "987654321"
        assert claims["can_administer_community"] is True

    def test_create_token_without_admin(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=False,
        )

        claims = validate_platform_claims(token)
        assert claims is not None
        assert claims["can_administer_community"] is False

    def test_discourse_platform_token(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discourse",
            scope="category:42",
            sub="user_77",
            community_id="forum.example.com",
            can_administer_community=True,
        )

        claims = validate_platform_claims(token)
        assert claims is not None
        assert claims["platform"] == "discourse"
        assert claims["scope"] == "category:42"

    def test_extra_kwargs_included_in_token(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123",
            community_id="456",
            can_administer_community=False,
            extra_claims={"username": "testuser"},
        )

        claims = validate_platform_claims(token)
        assert claims is not None
        assert claims["username"] == "testuser"

    def test_invalid_token_returns_none(self) -> None:
        from src.auth.platform_claims import validate_platform_claims

        claims = validate_platform_claims("invalid.jwt.token")
        assert claims is None

    def test_empty_token_returns_none(self) -> None:
        from src.auth.platform_claims import validate_platform_claims

        assert validate_platform_claims("") is None
        assert validate_platform_claims(None) is None  # type: ignore[arg-type]

    def test_tampered_token_returns_none(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
        )

        parts = token.split(".")
        tampered_token = parts[0] + "." + parts[1] + ".tamperedsignature"

        claims = validate_platform_claims(tampered_token)
        assert claims is None

    def test_expired_token_returns_none(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
            expires_delta=pendulum.duration(seconds=-60),
        )

        claims = validate_platform_claims(token)
        assert claims is None

    def test_wrong_token_type_returns_none(self) -> None:
        import jwt as pyjwt

        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "discord_claims",
            "platform": "discord",
            "scope": "*",
            "sub": "123",
            "community_id": "456",
            "can_administer_community": True,
            "iat": now,
            "exp": now + pendulum.duration(minutes=5),
        }

        token = pyjwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        from src.auth.platform_claims import validate_platform_claims

        claims = validate_platform_claims(token)
        assert claims is None

    def test_missing_required_field_returns_none(self) -> None:
        import jwt as pyjwt

        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "platform_claims",
            "platform": "discord",
            "sub": "123",
            "iat": now,
            "exp": now + pendulum.duration(minutes=5),
        }

        token = pyjwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        from src.auth.platform_claims import validate_platform_claims

        claims = validate_platform_claims(token)
        assert claims is None

    def test_non_string_sub_returns_none(self) -> None:
        import jwt as pyjwt

        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "platform_claims",
            "platform": "discord",
            "scope": "*",
            "sub": 123456789,
            "community_id": "987654321",
            "can_administer_community": True,
            "iat": now,
            "exp": now + pendulum.duration(minutes=5),
        }

        token = pyjwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        from src.auth.platform_claims import validate_platform_claims

        claims = validate_platform_claims(token)
        assert claims is None

    def test_non_bool_can_administer_returns_none(self) -> None:
        import jwt as pyjwt

        from src.config import settings

        now = pendulum.now("UTC")
        payload = {
            "type": "platform_claims",
            "platform": "discord",
            "scope": "*",
            "sub": "123",
            "community_id": "456",
            "can_administer_community": "true",
            "iat": now,
            "exp": now + pendulum.duration(minutes=5),
        }

        token = pyjwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        from src.auth.platform_claims import validate_platform_claims

        claims = validate_platform_claims(token)
        assert claims is None


@pytest.mark.unit
class TestGetPlatformAdminStatus:
    def test_with_valid_claims_header(self) -> None:
        from unittest.mock import MagicMock

        from src.auth.platform_claims import create_platform_claims_token, get_platform_admin_status

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123",
            community_id="456",
            can_administer_community=True,
        )

        request = MagicMock()
        request.headers = {"x-platform-claims": token}
        result = get_platform_admin_status(request)
        assert result is True

    def test_with_valid_claims_no_admin(self) -> None:
        from unittest.mock import MagicMock

        from src.auth.platform_claims import create_platform_claims_token, get_platform_admin_status

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123",
            community_id="456",
            can_administer_community=False,
        )

        request = MagicMock()
        request.headers = {"x-platform-claims": token}
        result = get_platform_admin_status(request)
        assert result is False

    def test_without_claims_header(self) -> None:
        from unittest.mock import MagicMock

        from src.auth.platform_claims import get_platform_admin_status

        request = MagicMock()
        request.headers = {}
        result = get_platform_admin_status(request)
        assert result is False

    def test_with_invalid_claims_header(self) -> None:
        from unittest.mock import MagicMock

        from src.auth.platform_claims import get_platform_admin_status

        request = MagicMock()
        request.headers = {"x-platform-claims": "invalid.jwt.token"}
        result = get_platform_admin_status(request)
        assert result is False

    def test_old_discord_claims_header_ignored(self) -> None:
        from unittest.mock import MagicMock

        from src.auth.platform_claims import get_platform_admin_status

        request = MagicMock()
        request.headers = {"x-discord-claims": "some-token", "x-discord-has-manage-server": "true"}
        result = get_platform_admin_status(request)
        assert result is False
