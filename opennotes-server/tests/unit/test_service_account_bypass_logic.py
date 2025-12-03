"""Unit tests for service account admin access bypass logic."""

# Import all models to ensure SQLAlchemy relationships are properly configured
from src.auth.permissions import is_service_account as _is_service_account
from src.llm_config.models import CommunityServer  # noqa: F401
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile  # noqa: F401


class TestServiceAccountDetection:
    """Test service account detection logic."""

    def test_detects_opennotes_local_email(self) -> None:
        """Test that service accounts with @opennotes.local email are detected."""
        user = User(
            email="discord-bot@opennotes.local",
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            role="user",
        )
        assert _is_service_account(user) is True

    def test_detects_service_suffix_username(self) -> None:
        """Test that service accounts with -service username suffix are detected."""
        user = User(
            email="regular@example.com",
            username="discord-bot-service",
            hashed_password="hash",
            is_active=True,
            role="user",
        )
        assert _is_service_account(user) is True

    def test_detects_both_markers(self) -> None:
        """Test that service accounts with both markers are detected."""
        user = User(
            email="discord-bot@opennotes.local",
            username="discord-bot-service",
            hashed_password="hash",
            is_active=True,
            role="user",
        )
        assert _is_service_account(user) is True

    def test_regular_user_not_detected(self) -> None:
        """Test that regular users are not detected as service accounts."""
        user = User(
            email="human@example.com",
            username="human_user",
            hashed_password="hash",
            is_active=True,
            role="user",
        )
        assert _is_service_account(user) is False

    def test_none_email_not_detected(self) -> None:
        """Test that users with None email but non-service username are not detected."""
        user = User(
            email=None,
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            role="user",
        )
        assert _is_service_account(user) is False

    def test_none_username_not_detected(self) -> None:
        """Test that users with None username but non-service email are not detected."""
        user = User(
            email="regular@example.com",
            username=None,
            hashed_password="hash",
            is_active=True,
            role="user",
        )
        assert _is_service_account(user) is False

    def test_detects_is_service_account_flag(self) -> None:
        """Test that users with is_service_account=True flag are detected."""
        user = User(
            email="regular@example.com",
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            role="user",
            is_service_account=True,
        )
        assert _is_service_account(user) is True

    def test_is_service_account_flag_false_not_detected(self) -> None:
        """Test that users with is_service_account=False are not detected without other markers."""
        user = User(
            email="regular@example.com",
            username="regular_user",
            hashed_password="hash",
            is_active=True,
            role="user",
            is_service_account=False,
        )
        assert _is_service_account(user) is False
