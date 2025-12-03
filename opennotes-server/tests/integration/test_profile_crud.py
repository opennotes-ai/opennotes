"""
Integration tests for profile CRUD operations.

Tests database operations for UserProfile, UserIdentity, and CommunityMember models.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Import CommunityServer to ensure it's registered before profile_models relationships are resolved
from src.llm_config.models import CommunityServer  # noqa: F401
from src.users.profile_crud import (
    authenticate_with_provider,
    create_community_member,
    create_identity,
    create_profile,
    create_profile_with_identity,
    get_community_member,
    get_identities_by_profile,
    get_identity_by_provider,
    get_profile_by_display_name,
    get_profile_by_id,
    update_community_member,
    update_profile,
)
from src.users.profile_schemas import (
    AuthProvider,
    CommunityMemberCreate,
    CommunityMemberUpdate,
    CommunityRole,
    UserIdentityCreate,
    UserProfileCreate,
    UserProfileUpdate,
)


@pytest.mark.asyncio
class TestProfileCRUD:
    async def test_create_profile(self, db: AsyncSession):
        profile_create = UserProfileCreate(
            display_name="test_user",
            avatar_url="https://example.com/avatar.png",
            bio="Test user bio",
            is_human=True,
        )

        profile = await create_profile(db, profile_create)
        await db.commit()

        assert profile.id is not None
        assert profile.display_name == "test_user"
        assert profile.avatar_url == "https://example.com/avatar.png"
        assert profile.bio == "Test user bio"
        assert profile.is_human is True
        assert profile.reputation == 0

    async def test_get_profile_by_id(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="test_user_2", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        fetched_profile = await get_profile_by_id(db, profile.id)

        assert fetched_profile is not None
        assert fetched_profile.id == profile.id
        assert fetched_profile.display_name == "test_user_2"

    async def test_get_profile_by_display_name(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="unique_name", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        fetched_profile = await get_profile_by_display_name(db, "unique_name")

        assert fetched_profile is not None
        assert fetched_profile.id == profile.id
        assert fetched_profile.display_name == "unique_name"

    async def test_update_profile(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="old_name", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        profile_update = UserProfileUpdate(
            display_name="new_name",
            bio="Updated bio",
            avatar_url="https://example.com/new_avatar.png",
        )

        updated_profile = await update_profile(db, profile, profile_update)
        await db.commit()

        assert updated_profile.display_name == "new_name"
        assert updated_profile.bio == "Updated bio"
        assert updated_profile.avatar_url == "https://example.com/new_avatar.png"


@pytest.mark.asyncio
class TestIdentityCRUD:
    async def test_create_identity(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="identity_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.DISCORD,
            provider_user_id="discord123",
            credentials={"discord_id": "discord123"},
        )

        identity = await create_identity(db, identity_create)
        await db.commit()

        assert identity.id is not None
        assert identity.profile_id == profile.id
        assert identity.provider == AuthProvider.DISCORD.value
        assert identity.provider_user_id == "discord123"

    async def test_get_identity_by_provider(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="provider_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id="user@example.com",
            credentials={"email": "user@example.com", "hashed_password": "hashed"},
        )

        await create_identity(db, identity_create)
        await db.commit()

        fetched_identity = await get_identity_by_provider(
            db, AuthProvider.EMAIL, "user@example.com"
        )

        assert fetched_identity is not None
        assert fetched_identity.provider == AuthProvider.EMAIL.value
        assert fetched_identity.provider_user_id == "user@example.com"
        assert fetched_identity.profile.id == profile.id

    async def test_get_identities_by_profile(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="multi_identity", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        discord_identity = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.DISCORD,
            provider_user_id="discord456",
        )

        email_identity = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id="multi@example.com",
        )

        await create_identity(db, discord_identity)
        await create_identity(db, email_identity)
        await db.commit()

        identities = await get_identities_by_profile(db, profile.id)

        assert len(identities) == 2
        providers = {identity.provider for identity in identities}
        assert AuthProvider.DISCORD.value in providers
        assert AuthProvider.EMAIL.value in providers


@pytest.mark.asyncio
class TestProfileWithIdentity:
    async def test_create_profile_with_identity(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="combined_test", is_human=True)

        profile, identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.DISCORD,
            "discord789",
            credentials={"discord_id": "discord789"},
        )

        await db.commit()

        assert profile.id is not None
        assert identity.id is not None
        assert identity.profile_id == profile.id
        assert identity.provider == AuthProvider.DISCORD.value
        assert identity.provider_user_id == "discord789"

    async def test_authenticate_with_provider(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="auth_test", is_human=True)

        profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.GITHUB,
            "github123",
        )

        await db.commit()

        authenticated_profile = await authenticate_with_provider(
            db, AuthProvider.GITHUB, "github123"
        )

        assert authenticated_profile is not None
        assert authenticated_profile.id == profile.id
        assert authenticated_profile.display_name == "auth_test"

    async def test_authenticate_with_nonexistent_provider(self, db: AsyncSession):
        authenticated_profile = await authenticate_with_provider(
            db, AuthProvider.DISCORD, "nonexistent123"
        )

        assert authenticated_profile is None


@pytest.mark.asyncio
class TestCommunityMemberCRUD:
    async def test_create_community_member(self, db: AsyncSession, community_server: UUID):
        profile_create = UserProfileCreate(display_name="community_member", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        member_create = CommunityMemberCreate(
            community_id=community_server,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.MEMBER,
            joined_at=datetime.now(UTC),
        )

        member = await create_community_member(db, member_create)
        await db.commit()

        assert member.id is not None
        assert member.community_id == community_server
        assert member.profile_id == profile.id
        assert member.role == CommunityRole.MEMBER.value
        assert member.is_active is True

    async def test_get_community_member(self, db: AsyncSession, community_server: UUID):
        profile_create = UserProfileCreate(display_name="get_member_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        member_create = CommunityMemberCreate(
            community_id=community_server,
            profile_id=profile.id,
            role=CommunityRole.MODERATOR,
            joined_at=datetime.now(UTC),
        )

        await create_community_member(db, member_create)
        await db.commit()

        fetched_member = await get_community_member(db, community_server, profile.id)

        assert fetched_member is not None
        assert fetched_member.profile_id == profile.id
        assert fetched_member.community_id == community_server
        assert fetched_member.role == CommunityRole.MODERATOR.value

    async def test_update_community_member(self, db: AsyncSession, community_server: UUID):
        profile_create = UserProfileCreate(display_name="update_member_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        member_create = CommunityMemberCreate(
            community_id=community_server,
            profile_id=profile.id,
            role=CommunityRole.MEMBER,
            joined_at=datetime.now(UTC),
        )

        member = await create_community_member(db, member_create)
        await db.commit()

        member_update = CommunityMemberUpdate(
            role=CommunityRole.ADMIN,
            reputation_in_community=100,
        )

        updated_member = await update_community_member(db, member, member_update)
        await db.commit()

        assert updated_member.role == CommunityRole.ADMIN.value
        assert updated_member.reputation_in_community == 100
