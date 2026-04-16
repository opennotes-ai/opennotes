"""Unit tests for Phase 1.1 permission helpers."""

from datetime import UTC, datetime
from unittest.mock import MagicMock


def _make_user(**kwargs):
    user = MagicMock()
    user.is_active = kwargs.get("is_active", True)
    user.banned_at = kwargs.get("banned_at")
    user.platform_roles = kwargs.get("platform_roles", [])
    user.principal_type = kwargs.get("principal_type", "human")
    return user


def test_is_account_active_true():
    from src.auth.permissions import is_account_active

    assert is_account_active(_make_user(is_active=True, banned_at=None)) is True


def test_is_account_active_banned():
    from src.auth.permissions import is_account_active

    assert is_account_active(_make_user(is_active=True, banned_at=datetime.now(UTC))) is False


def test_is_account_active_inactive():
    from src.auth.permissions import is_account_active

    assert is_account_active(_make_user(is_active=False)) is False


def test_is_platform_admin_true():
    from src.auth.permissions import is_platform_admin

    assert is_platform_admin(_make_user(platform_roles=["platform_admin"])) is True


def test_is_platform_admin_false():
    from src.auth.permissions import is_platform_admin

    assert is_platform_admin(_make_user(platform_roles=[])) is False


def test_is_platform_admin_none_roles():
    from src.auth.permissions import is_platform_admin

    assert is_platform_admin(_make_user(platform_roles=None)) is False


def test_is_system_principal():
    from src.auth.permissions import is_system_principal

    assert is_system_principal(_make_user(principal_type="system")) is True
    assert is_system_principal(_make_user(principal_type="agent")) is False


def test_has_platform_role():
    from src.auth.permissions import has_platform_role

    assert (
        has_platform_role(_make_user(platform_roles=["platform_admin"]), "platform_admin") is True
    )
    assert has_platform_role(_make_user(platform_roles=[]), "platform_admin") is False
