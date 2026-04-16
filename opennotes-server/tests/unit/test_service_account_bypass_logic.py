"""Unit tests for service account admin access bypass logic."""

from src.auth.permissions import is_service_account as _is_service_account
from src.llm_config.models import CommunityServer  # noqa: F401
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile  # noqa: F401


class TestServiceAccountDetection:
    def test_human_with_spoofed_email_returns_false(self) -> None:
        user = User(
            email="discord-bot@opennotes.local",
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            principal_type="human",
        )
        assert _is_service_account(user) is False

    def test_human_with_service_suffix_username_returns_false(self) -> None:
        user = User(
            email="regular@example.com",
            username="discord-bot-service",
            hashed_password="hash",
            is_active=True,
            principal_type="human",
        )
        assert _is_service_account(user) is False

    def test_human_with_both_spoofed_markers_returns_false(self) -> None:
        user = User(
            email="discord-bot@opennotes.local",
            username="discord-bot-service",
            hashed_password="hash",
            is_active=True,
            principal_type="human",
        )
        assert _is_service_account(user) is False

    def test_regular_user_not_detected(self) -> None:
        user = User(
            email="human@example.com",
            username="human_user",
            hashed_password="hash",
            is_active=True,
            principal_type="human",
        )
        assert _is_service_account(user) is False

    def test_none_principal_type_returns_false(self) -> None:
        user = User(
            email=None,
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            principal_type=None,
        )
        assert _is_service_account(user) is False

    def test_agent_principal_type_returns_true(self) -> None:
        user = User(
            email="agent@opennotes.local",
            username="my-agent",
            hashed_password="hash",
            is_active=True,
            principal_type="agent",
        )
        assert _is_service_account(user) is True

    def test_system_principal_type_returns_true(self) -> None:
        user = User(
            email="platform-service@opennotes.local",
            username="platform-service",
            hashed_password="hash",
            is_active=True,
            principal_type="system",
            platform_roles=["platform_admin"],
        )
        assert _is_service_account(user) is True

    def test_is_service_account_flag_alone_not_sufficient(self) -> None:
        user = User(
            email="regular@example.com",
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            principal_type="human",
        )
        assert _is_service_account(user) is False
