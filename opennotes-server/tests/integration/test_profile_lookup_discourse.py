"""
Integration tests for multi-platform profile lookup and identity CRUD.

Tests the generic get_or_create_profile_from_platform() function and
the lookup endpoint with platform=discourse and provider_scope.
"""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.models import CommunityServer
from src.users.profile_crud import (
    get_identity_by_provider,
    get_or_create_profile_from_platform,
)
from src.users.profile_schemas import (
    AuthProvider,
    PlatformIdentityInput,
)


@pytest.mark.asyncio
class TestGetOrCreateProfileFromPlatform:
    async def test_creates_new_discourse_profile(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="42",
            provider_scope="community.example.com",
            username="discourse_user",
            display_name="Discourse User",
            avatar_url="https://community.example.com/user_avatar/42.png",
            metadata={"trust_level": 2},
        )

        profile = await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        assert profile is not None
        assert profile.id is not None
        assert isinstance(profile.id, UUID)
        assert profile.display_name == "Discourse User"
        assert profile.avatar_url == "https://community.example.com/user_avatar/42.png"

    async def test_finds_existing_discourse_profile(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="100",
            provider_scope="forum.test.org",
            username="existing_user",
            display_name="Existing User",
        )

        profile1 = await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        profile2 = await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        assert profile1.id == profile2.id

    async def test_discourse_different_scopes_create_separate_identities(self, db: AsyncSession):
        user_info_1 = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="55",
            provider_scope="site-a.example.com",
            username="user55",
            display_name="User 55 on Site A",
        )
        user_info_2 = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="55",
            provider_scope="site-b.example.com",
            username="user55",
            display_name="User 55 on Site B",
        )

        profile_a = await get_or_create_profile_from_platform(db, user_info_1)
        await db.commit()
        profile_b = await get_or_create_profile_from_platform(db, user_info_2)
        await db.commit()

        assert profile_a.id != profile_b.id

    async def test_creates_discord_profile_via_generic(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="999888777",
            username="discord_generic",
            display_name="Discord Generic",
        )

        profile = await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        assert profile is not None
        assert profile.display_name == "Discord Generic"

    async def test_updates_metadata_on_existing_profile(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="200",
            provider_scope="meta.example.com",
            username="evolving_user",
            display_name="Old Name",
            avatar_url="https://old.avatar.png",
        )

        profile = await get_or_create_profile_from_platform(db, user_info)
        await db.commit()
        original_id = profile.id

        updated_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="200",
            provider_scope="meta.example.com",
            username="evolving_user",
            display_name="New Name",
            avatar_url="https://new.avatar.png",
        )

        profile2 = await get_or_create_profile_from_platform(db, updated_info)
        await db.commit()

        assert profile2.id == original_id
        assert profile2.display_name == "New Name"
        assert profile2.avatar_url == "https://new.avatar.png"

    async def test_username_fallback_for_display_name(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="300",
            provider_scope="test.discourse.org",
            username="just_username",
        )

        profile = await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        assert profile.display_name == "just_username"

    async def test_community_membership_created(self, db: AsyncSession, community_server: UUID):
        from sqlalchemy import select

        result = await db.execute(
            select(CommunityServer).where(CommunityServer.id == community_server)
        )
        server = result.scalar_one()

        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="400",
            provider_scope="community.discourse.org",
            username="member_user",
            display_name="Member User",
        )

        profile = await get_or_create_profile_from_platform(
            db, user_info, platform_community_server_id=server.platform_community_server_id
        )
        await db.commit()

        assert profile is not None


@pytest.mark.asyncio
class TestGetIdentityByProviderWithScope:
    async def test_finds_identity_with_matching_scope(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="501",
            provider_scope="scoped.example.com",
            username="scoped_user",
            display_name="Scoped User",
        )
        await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        identity = await get_identity_by_provider(
            db, AuthProvider.DISCOURSE, "501", provider_scope="scoped.example.com"
        )
        assert identity is not None
        assert identity.provider_user_id == "501"
        assert identity.provider_scope == "scoped.example.com"

    async def test_no_match_with_different_scope(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="502",
            provider_scope="site-x.example.com",
            username="x_user",
            display_name="X User",
        )
        await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        identity = await get_identity_by_provider(
            db, AuthProvider.DISCOURSE, "502", provider_scope="site-y.example.com"
        )
        assert identity is None

    async def test_no_scope_returns_wildcard_identity(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="503",
            username="discord_no_scope",
            display_name="Discord No Scope",
        )
        await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        identity = await get_identity_by_provider(db, AuthProvider.DISCORD, "503")
        assert identity is not None
        assert identity.provider_scope == "*"
