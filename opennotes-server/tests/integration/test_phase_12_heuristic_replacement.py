"""Phase 1.2 regression tests — is_service_account() heuristic replacement.

Verifies that the old 3-way heuristic (is_service_account flag, @opennotes.local
email, -service username) is no longer used, and that principal_type is the sole
authority for service-account classification.

These tests exercise the pure is_service_account() function and are marked as
unit tests so that no external services (DB, Redis, NATS) are needed.
"""

import pytest

from src.auth.permissions import is_service_account
from src.users.models import User


def _make_user(**kwargs) -> User:
    defaults = {
        "username": "test-user",
        "email": "test@test.example",
        "hashed_password": "fakehash",
        "is_active": True,
        "principal_type": "human",
        "platform_roles": [],
        "banned_at": None,
    }
    defaults.update(kwargs)
    # Strip any dropped User columns that tests may pass defensively
    for dropped in ("is_service_account", "is_superuser", "role"):
        defaults.pop(dropped, None)
    return User(**defaults)


@pytest.mark.unit
class TestIsServiceAccountHeuristicReplacement:
    def test_spoofed_sa_helper_returns_false(self) -> None:
        user = _make_user(
            username="evil-service",
            email="evil@opennotes.local",
            principal_type="human",
        )
        assert is_service_account(user) is False

    def test_legitimate_agent_still_works(self) -> None:
        user = _make_user(
            username="my-agent",
            email="agent@opennotes.local",
            principal_type="agent",
        )
        assert is_service_account(user) is True

    def test_system_principal_is_sa(self) -> None:
        user = _make_user(
            username="platform-service",
            email="platform-service@opennotes.local",
            principal_type="system",
            platform_roles=["platform_admin"],
        )
        assert is_service_account(user) is True
