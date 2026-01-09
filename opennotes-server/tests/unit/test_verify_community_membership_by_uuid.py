"""
Unit tests for verify_community_membership_by_uuid dependency.

These tests use mocked database operations to test the authorization logic
without requiring Docker or an actual database connection.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.users.models import User
from src.users.profile_models import CommunityMember, UserProfile


def create_mock_user(
    user_id: int = 1,
    username: str = "testuser",
    email: str = "test@example.com",
    is_service_account: bool = False,
) -> User:
    """Create a mock User object."""
    if is_service_account:
        email = f"{username}@opennotes.local"
        username = f"{username}-service"

    return User(
        id=user_id,
        username=username,
        email=email,
        hashed_password="unused",
        role="user",
    )


def create_mock_profile(
    profile_id=None,
    display_name: str = "Test User",
    is_human: bool = True,
) -> UserProfile:
    """Create a mock UserProfile object."""
    profile = MagicMock(spec=UserProfile)
    profile.id = profile_id or uuid4()
    profile.display_name = display_name
    profile.is_human = is_human
    profile.is_opennotes_admin = False
    return profile


def create_mock_membership(
    community_id=None,
    profile_id=None,
    role: str = "member",
    is_active: bool = True,
    banned_at=None,
) -> CommunityMember:
    """Create a mock CommunityMember object."""
    membership = MagicMock(spec=CommunityMember)
    membership.id = uuid4()
    membership.community_id = community_id or uuid4()
    membership.profile_id = profile_id or uuid4()
    membership.role = role
    membership.is_active = is_active
    membership.banned_at = banned_at
    membership.banned_reason = "Test ban" if banned_at else None
    return membership


def create_mock_community(community_id=None, platform_community_server_id: str = "123456789"):
    """Create a mock CommunityServer object."""
    from src.llm_config.models import CommunityServer

    community = MagicMock(spec=CommunityServer)
    community.id = community_id or uuid4()
    community.platform = "discord"
    community.platform_community_server_id = platform_community_server_id
    community.name = "Test Server"
    community.is_active = True
    community.is_public = True
    return community


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyCommunityMembershipByUUID:
    """Unit tests for verify_community_membership_by_uuid dependency."""

    async def test_valid_member_returns_membership(self):
        """Valid member should return their membership record."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()
        profile_id = uuid4()
        community = create_mock_community(community_id)
        profile = create_mock_profile(profile_id, is_human=True)
        membership = create_mock_membership(
            community_id=community_id, profile_id=profile_id, is_active=True
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with (
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
            patch(
                "src.auth.community_dependencies.get_profile_by_id",
                return_value=profile,
            ),
            patch(
                "src.auth.community_dependencies._ensure_membership_with_permissions",
                return_value=membership,
            ),
        ):
            result = await verify_community_membership_by_uuid(
                community_id, user, mock_db, mock_request
            )

            assert result == membership
            assert result.profile_id == profile_id
            assert result.community_id == community_id

    async def test_nonexistent_community_returns_404(self):
        """Non-existent community should return 404 Not Found."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await verify_community_membership_by_uuid(community_id, user, mock_db, mock_request)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    async def test_user_without_profile_gets_403(self):
        """User without profile should get 403 Forbidden."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()
        community = create_mock_community(community_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch(
            "src.auth.community_dependencies._get_profile_id_from_user",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_community_membership_by_uuid(community_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "profile not found" in exc_info.value.detail.lower()

    async def test_profile_not_found_after_lookup_gets_403(self):
        """User whose profile lookup fails should get 403 Forbidden."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()
        profile_id = uuid4()
        community = create_mock_community(community_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with (
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
            patch(
                "src.auth.community_dependencies.get_profile_by_id",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_community_membership_by_uuid(community_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "profile not found" in exc_info.value.detail.lower()

    async def test_non_member_gets_403(self):
        """Non-member should get 403 Forbidden via _ensure_membership_with_permissions."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()
        profile_id = uuid4()
        community = create_mock_community(community_id)
        profile = create_mock_profile(profile_id, is_human=True)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        async def raise_403(*args, **kwargs):
            raise HTTPException(
                status_code=403,
                detail=f"User is not a member of community server {community_id}",
            )

        with (
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
            patch(
                "src.auth.community_dependencies.get_profile_by_id",
                return_value=profile,
            ),
            patch(
                "src.auth.community_dependencies._ensure_membership_with_permissions",
                side_effect=raise_403,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_community_membership_by_uuid(community_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "not a member" in exc_info.value.detail.lower()

    async def test_banned_user_gets_403(self):
        """Banned user should get 403 Forbidden via _ensure_membership_with_permissions."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()
        profile_id = uuid4()
        community = create_mock_community(community_id)
        profile = create_mock_profile(profile_id, is_human=True)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        async def raise_banned(*args, **kwargs):
            raise HTTPException(
                status_code=403,
                detail="User is banned from this community server",
            )

        with (
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
            patch(
                "src.auth.community_dependencies.get_profile_by_id",
                return_value=profile,
            ),
            patch(
                "src.auth.community_dependencies._ensure_membership_with_permissions",
                side_effect=raise_banned,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_community_membership_by_uuid(community_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "banned" in exc_info.value.detail.lower()

    async def test_discord_claims_header_is_passed_to_ensure_membership(self):
        """Discord claims header should be passed to _ensure_membership_with_permissions."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid
        from src.auth.discord_claims import create_discord_claims_token

        community_id = uuid4()
        profile_id = uuid4()
        community = create_mock_community(community_id)
        profile = create_mock_profile(profile_id, is_human=True)
        membership = create_mock_membership(community_id=community_id, profile_id=profile_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()

        token = create_discord_claims_token(
            user_id="123",
            guild_id="456",
            has_manage_server=True,
        )
        mock_request = MagicMock()
        mock_request.headers = {"x-discord-claims": token}

        ensure_membership_mock = AsyncMock(return_value=membership)

        with (
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
            patch(
                "src.auth.community_dependencies.get_profile_by_id",
                return_value=profile,
            ),
            patch(
                "src.auth.community_dependencies._ensure_membership_with_permissions",
                ensure_membership_mock,
            ),
        ):
            await verify_community_membership_by_uuid(community_id, user, mock_db, mock_request)

            ensure_membership_mock.assert_called_once()
            call_kwargs = ensure_membership_mock.call_args.kwargs
            assert call_kwargs["has_discord_manage_server"] is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyCommunityMembershipByUUIDDoesNotCheckAdmin:
    """Verify that verify_community_membership_by_uuid does NOT check admin permissions."""

    async def test_member_role_is_sufficient(self):
        """Member role should be sufficient - no admin check required."""
        from src.auth.community_dependencies import verify_community_membership_by_uuid

        community_id = uuid4()
        profile_id = uuid4()
        community = create_mock_community(community_id)
        profile = create_mock_profile(profile_id, is_human=True)
        membership = create_mock_membership(
            community_id=community_id,
            profile_id=profile_id,
            role="member",
            is_active=True,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = community
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with (
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
            patch(
                "src.auth.community_dependencies.get_profile_by_id",
                return_value=profile,
            ),
            patch(
                "src.auth.community_dependencies._ensure_membership_with_permissions",
                return_value=membership,
            ),
            patch("src.auth.community_dependencies.has_community_admin_access") as mock_admin_check,
        ):
            result = await verify_community_membership_by_uuid(
                community_id, user, mock_db, mock_request
            )

            assert result == membership
            mock_admin_check.assert_not_called()
