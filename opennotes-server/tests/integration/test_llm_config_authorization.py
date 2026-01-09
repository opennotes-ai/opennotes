"""Integration tests for LLM configuration authorization."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

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
            platform_community_server_id="123456789",
            name="Test Community",
            description="Test community for authorization tests",
            is_active=True,
        )
        db.add(community)
        await db.commit()
        await db.refresh(community)
        return community


@pytest.fixture
async def admin_user() -> User:
    """Create an admin user with authentication."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            username="admin_user",
            email="admin@example.com",
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
    """Create a regular user with authentication."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            username="regular_user",
            email="user@example.com",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def admin_profile(admin_user: User) -> tuple[UserProfile, UserIdentity]:
    """Create a profile and identity for the admin user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile = UserProfile(display_name="Admin User")
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        identity = UserIdentity(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id=admin_user.email,
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
        profile = UserProfile(display_name="Regular User")
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
async def admin_membership(
    test_community_server: CommunityServer,
    admin_profile: tuple[UserProfile, UserIdentity],
) -> CommunityMember:
    """Create admin membership for the admin user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile, _ = admin_profile
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="admin",
            is_active=True,
            joined_at=datetime.now(UTC),
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
    """Create regular member membership for the regular user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile, _ = regular_profile
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="member",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        db.add(membership)
        await db.commit()
        await db.refresh(membership)
        return membership


@pytest.mark.asyncio
class TestLLMConfigAuthorization:
    """Test authorization checks for LLM configuration endpoints."""

    async def test_create_config_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that creating LLM config requires admin access."""

    async def test_create_config_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot create LLM configs."""

    async def test_list_configs_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that listing LLM configs requires admin access."""

    async def test_list_configs_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot list LLM configs."""

    async def test_get_config_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that getting LLM config requires admin access."""

    async def test_get_config_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot get LLM configs."""

    async def test_update_config_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that updating LLM config requires admin access."""

    async def test_update_config_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot update LLM configs."""

    async def test_delete_config_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that deleting LLM config requires admin access."""

    async def test_delete_config_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot delete LLM configs."""

    async def test_test_config_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that testing LLM config requires admin access."""

    async def test_test_config_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot test LLM configs."""

    async def test_get_usage_stats_requires_admin(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_membership: CommunityMember,
    ) -> None:
        """Test that getting usage stats requires admin access."""

    async def test_get_usage_stats_denies_regular_user(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """Test that regular users cannot get usage stats."""

    async def test_nonexistent_community_returns_404(
        self,
        client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Test that accessing non-existent community returns 404."""

    async def test_not_member_of_community_returns_403(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
    ) -> None:
        """Test that non-members cannot access configs."""

    async def test_banned_user_returns_403(
        self,
        client: AsyncClient,
        test_community_server: CommunityServer,
        admin_user: User,
        admin_profile: tuple[UserProfile, UserIdentity],
    ) -> None:
        """Test that banned users cannot access configs."""
