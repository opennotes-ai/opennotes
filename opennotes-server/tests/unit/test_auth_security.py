from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.auth.dependencies import require_scope_or_admin
from src.users.models import APIKey, User


def _make_user(
    is_platform_admin: bool = False,
    is_service_account: bool = False,
    is_active: bool = True,
) -> User:
    user = MagicMock(spec=User)
    user.platform_roles = ["platform_admin"] if is_platform_admin else []
    user.principal_type = "system" if is_service_account else "human"
    user.is_active = is_active
    user.banned_at = None
    return user


def _make_request(api_key: APIKey | None = None) -> MagicMock:
    request = MagicMock()
    if api_key is not None:
        request.state.api_key = api_key
    else:
        request.state = MagicMock(spec=[])
    return request


def _make_api_key(scopes: list[str] | None = None) -> APIKey:
    key = MagicMock(spec=APIKey)
    key.scopes = scopes

    def has_scope(scope: str) -> bool:
        if scopes is None or len(scopes) == 0:
            return False
        return scope in scopes

    def is_scoped() -> bool:
        return scopes is not None and len(scopes) > 0

    key.has_scope = has_scope
    key.is_scoped = is_scoped
    return key


@pytest.mark.unit
class TestRequireScopeOrAdmin:
    def test_superuser_without_api_key_gets_unrestricted(self):
        user = _make_user(is_platform_admin=True)
        request = _make_request(api_key=None)
        result = require_scope_or_admin(user, request, "simulations:read")
        assert result is False

    def test_service_account_without_api_key_gets_unrestricted(self):
        user = _make_user(is_service_account=True)
        request = _make_request(api_key=None)
        result = require_scope_or_admin(user, request, "simulations:read")
        assert result is False

    def test_regular_user_without_api_key_gets_403(self):
        user = _make_user()
        request = _make_request(api_key=None)
        with pytest.raises(HTTPException) as exc_info:
            require_scope_or_admin(user, request, "simulations:read")
        assert exc_info.value.status_code == 403

    def test_regular_user_with_scoped_key_having_scope_gets_restricted(self):
        user = _make_user()
        api_key = _make_api_key(scopes=["simulations:read"])
        request = _make_request(api_key=api_key)
        result = require_scope_or_admin(user, request, "simulations:read")
        assert result is True

    def test_regular_user_with_scoped_key_missing_scope_gets_403(self):
        user = _make_user()
        api_key = _make_api_key(scopes=["other:scope"])
        request = _make_request(api_key=api_key)
        with pytest.raises(HTTPException) as exc_info:
            require_scope_or_admin(user, request, "simulations:read")
        assert exc_info.value.status_code == 403

    def test_regular_user_with_unscoped_key_gets_403(self):
        user = _make_user()
        api_key = _make_api_key(scopes=None)
        request = _make_request(api_key=api_key)
        with pytest.raises(HTTPException) as exc_info:
            require_scope_or_admin(user, request, "simulations:read")
        assert exc_info.value.status_code == 403

    def test_service_account_with_scoped_key_gets_restricted(self):
        user = _make_user(is_service_account=True)
        api_key = _make_api_key(scopes=["simulations:read"])
        request = _make_request(api_key=api_key)
        result = require_scope_or_admin(user, request, "simulations:read")
        assert result is True

    def test_service_account_with_scoped_key_missing_scope_gets_403(self):
        user = _make_user(is_service_account=True)
        api_key = _make_api_key(scopes=["other:scope"])
        request = _make_request(api_key=api_key)
        with pytest.raises(HTTPException) as exc_info:
            require_scope_or_admin(user, request, "simulations:read")
        assert exc_info.value.status_code == 403

    def test_superuser_with_unscoped_key_gets_403(self):
        user = _make_user(is_platform_admin=True)
        api_key = _make_api_key(scopes=None)
        request = _make_request(api_key=api_key)
        with pytest.raises(HTTPException) as exc_info:
            require_scope_or_admin(user, request, "simulations:read")
        assert exc_info.value.status_code == 403

    def test_service_account_with_unscoped_key_gets_403(self):
        user = _make_user(is_service_account=True)
        api_key = _make_api_key(scopes=None)
        request = _make_request(api_key=api_key)
        with pytest.raises(HTTPException) as exc_info:
            require_scope_or_admin(user, request, "simulations:read")
        assert exc_info.value.status_code == 403


@pytest.mark.unit
@pytest.mark.asyncio
class TestServiceAccountPasswordLogin:
    async def test_service_account_cannot_login_with_correct_password(self):
        from src.auth.password import get_password_hash
        from src.users.crud import authenticate_user

        password = "test-password-123"
        mock_user = MagicMock(spec=User)
        mock_user.principal_type = "system"
        mock_user.is_active = True
        mock_user.banned_at = None
        mock_user.hashed_password = get_password_hash(password)
        mock_user.id = uuid4()
        mock_user.username = "test-service"

        mock_db = AsyncMock()

        with (
            patch("src.users.crud.get_user_by_username", return_value=mock_user),
            patch("src.users.crud.create_audit_log", new_callable=AsyncMock),
        ):
            result = await authenticate_user(
                mock_db,
                "test-service",
                password,
            )
            assert result is None

    async def test_regular_user_can_still_login(self):
        from src.users.crud import authenticate_user

        mock_user = MagicMock(spec=User)
        mock_user.principal_type = "human"
        mock_user.is_active = True
        mock_user.banned_at = None
        mock_user.id = uuid4()
        mock_user.username = "regular-user"
        mock_user.hashed_password = "$2b$12$dummyhashvalue"

        mock_db = AsyncMock()

        with (
            patch("src.users.crud.get_user_by_username", return_value=mock_user),
            patch("src.users.crud.verify_password", return_value=(True, False)),
            patch("src.users.crud.create_audit_log", new_callable=AsyncMock),
        ):
            result = await authenticate_user(
                mock_db,
                "regular-user",
                "correct-password",
            )
            assert result is mock_user


@pytest.mark.unit
class TestSeedApiKeysNoHardcodedPasswords:
    def test_seed_script_uses_random_passwords(self):
        from pathlib import Path

        seed_file = Path(__file__).parent.parent.parent / "scripts" / "seed_api_keys.py"
        source = seed_file.read_text()

        assert "unused-service-account-password" not in source, (
            "seed_api_keys.py must not contain hardcoded service account passwords"
        )
