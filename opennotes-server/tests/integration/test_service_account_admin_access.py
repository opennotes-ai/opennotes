"""Integration tests for service account admin access."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin, verify_community_admin_by_uuid
from src.llm_config.models import CommunityServer
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile
from src.users.profile_schemas import AuthProvider


@pytest.fixture
async def test_community_server() -> CommunityServer:
    """Create a test community server."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        community = CommunityServer(
            platform="discord",
            platform_community_server_id="999888777666",
            name="Test Bot Community",
            description="Community for testing bot access",
            is_active=True,
        )
        db.add(community)
        await db.commit()
        await db.refresh(community)
        return community


@pytest.fixture
async def service_account_user() -> User:
    """Create a service account (bot) user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="discord-bot@opennotes.local",
            username="discord-bot-service",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def regular_user() -> User:
    """Create a regular human user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="human@example.com",
            username="human_user",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def service_account_profile(service_account_user: User) -> tuple[UserProfile, UserIdentity]:
    """Create a profile and identity for the service account."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile = UserProfile(
            display_name="Discord Bot",
            bio="Service account for Discord bot",
            is_human=False,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        identity = UserIdentity(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id=service_account_user.email,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity)

        return profile, identity


@pytest.fixture
async def regular_profile(regular_user: User) -> tuple[UserProfile, UserIdentity]:
    """Create a profile and identity for the regular user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile = UserProfile(
            display_name="Human User",
            is_human=True,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        identity = UserIdentity(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id=regular_user.email,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity)

        return profile, identity


@pytest.fixture
async def service_account_membership(
    test_community_server: CommunityServer,
    service_account_profile: tuple[UserProfile, UserIdentity],
) -> CommunityMember:
    """Create membership for service account with role='member'."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile, _ = service_account_profile
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="member",
            joined_at=datetime.now(UTC),
            is_active=True,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(membership)
        return membership


@pytest.fixture
async def regular_membership(
    test_community_server: CommunityServer,
    regular_profile: tuple[UserProfile, UserIdentity],
) -> CommunityMember:
    """Create membership for regular user with role='member'."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile, _ = regular_profile
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="member",
            joined_at=datetime.now(UTC),
            is_active=True,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(membership)
        return membership


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request with no Discord permission headers."""
    request = MagicMock()
    request.headers = {}
    return request


@pytest.mark.asyncio
class TestServiceAccountAdminAccess:
    """Test that service accounts automatically have admin access."""

    async def test_service_account_bypasses_role_check(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        service_account_user: User,
        service_account_membership: CommunityMember,
        mock_request,
    ) -> None:
        """Test that service accounts with role='member' can access admin endpoints."""
        result = await verify_community_admin(
            test_community_server.platform_community_server_id,
            service_account_user,
            db_session,
            mock_request,
        )

        assert result is not None
        assert result.id == service_account_membership.id
        assert result.role == "member"
        assert result.profile.is_human is False

    async def test_service_account_bypasses_role_check_by_uuid(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        service_account_user: User,
        service_account_membership: CommunityMember,
        mock_request,
    ) -> None:
        """Test that service accounts bypass role check in UUID variant."""
        result = await verify_community_admin_by_uuid(
            test_community_server.id,
            service_account_user,
            db_session,
            mock_request,
        )

        assert result is not None
        assert result.id == service_account_membership.id
        assert result.role == "member"
        assert result.profile.is_human is False

    async def test_regular_user_blocked_with_member_role(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
        mock_request,
    ) -> None:
        """Test that regular users with role='member' are blocked from admin endpoints."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_community_admin(
                test_community_server.platform_community_server_id,
                regular_user,
                db_session,
                mock_request,
            )

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail
        assert "member" in exc_info.value.detail

    async def test_regular_user_blocked_with_member_role_by_uuid(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
        mock_request,
    ) -> None:
        """Test that regular users are blocked in UUID variant."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_community_admin_by_uuid(
                test_community_server.id,
                regular_user,
                db_session,
                mock_request,
            )

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail

    async def test_admin_human_user_still_has_access(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_profile: tuple[UserProfile, UserIdentity],
        mock_request,
    ) -> None:
        """Test that human users with admin role still have access."""
        profile, _ = regular_profile

        admin_membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="admin",
            joined_at=datetime.now(UTC),
            is_active=True,
        )
        db_session.add(admin_membership)
        await db_session.commit()
        await db_session.refresh(admin_membership)

        result = await verify_community_admin(
            test_community_server.platform_community_server_id,
            regular_user,
            db_session,
            mock_request,
        )

        assert result is not None
        assert result.role == "admin"
        assert result.profile.is_human is True

    async def test_moderator_human_user_still_has_access(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_profile: tuple[UserProfile, UserIdentity],
        mock_request,
    ) -> None:
        """Test that human users with moderator role still have access."""
        profile, _ = regular_profile

        mod_membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="moderator",
            joined_at=datetime.now(UTC),
            is_active=True,
        )
        db_session.add(mod_membership)
        await db_session.commit()
        await db_session.refresh(mod_membership)

        result = await verify_community_admin(
            test_community_server.platform_community_server_id,
            regular_user,
            db_session,
            mock_request,
        )

        assert result is not None
        assert result.role == "moderator"
        assert result.profile.is_human is True
