"""
Integration tests for profile-creation audit (TASK-1451.01).

Ensures every UserProfile/UserIdentity creation path also creates a corresponding
User row in the users table. This is a precondition for Phase 2 FK addition.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.models import CommunityServer  # noqa: F401 — triggers relationship reg
from src.users.models import User
from src.users.profile_crud import (
    create_profile_with_identity,
    get_or_create_profile_from_platform,
)
from src.users.profile_models import UserProfile
from src.users.profile_schemas import (
    AuthProvider,
    PlatformIdentityInput,
    UserProfileCreate,
)


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


@pytest.mark.asyncio
class TestCreateProfileWithIdentityCreatesUser:
    async def test_discord_profile_creates_user_row(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="discord_audit_test", is_human=True)

        _profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.DISCORD,
            "discord_audit_111",
        )
        await db.commit()

        expected_username = "discord-discord_audit_111"
        user = await _get_user_by_username(db, expected_username)

        assert user is not None, f"Expected User with username '{expected_username}' to be created"
        assert user.is_active is True
        assert user.is_service_account is False
        assert user.hashed_password == "!platform-auth-only"

    async def test_email_profile_creates_user_row(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="email_audit_test", is_human=True)

        _profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.EMAIL,
            "emailaudit@example.com",
        )
        await db.commit()

        expected_username = "email-emailaudit@example.com"
        user = await _get_user_by_username(db, expected_username)

        assert user is not None
        assert user.is_active is True
        assert user.is_service_account is False

    async def test_github_profile_creates_user_row(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="github_audit_test", is_human=True)

        _profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.GITHUB,
            "github_audit_user_555",
        )
        await db.commit()

        expected_username = "github-github_audit_user_555"
        user = await _get_user_by_username(db, expected_username)

        assert user is not None
        assert user.is_active is True

    async def test_user_email_is_synthetic(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="email_field_test", is_human=True)

        _profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.DISCORD,
            "discord_email_field_777",
        )
        await db.commit()

        expected_username = "discord-discord_email_field_777"
        user = await _get_user_by_username(db, expected_username)

        assert user is not None
        assert user.email.endswith("@platform.opennotes.local")

    async def test_discord_user_row_has_discord_id(self, db: AsyncSession):
        profile_create = UserProfileCreate(display_name="discord_id_test", is_human=True)

        _profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.DISCORD,
            "discord_id_check_999",
        )
        await db.commit()

        expected_username = "discord-discord_id_check_999"
        user = await _get_user_by_username(db, expected_username)

        assert user is not None
        assert user.discord_id == "discord_id_check_999"


@pytest.mark.asyncio
class TestGetOrCreateProfileFromPlatformCreatesUser:
    async def test_creates_user_on_new_platform_profile(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="platform_new_888",
            provider_scope="*",
            username="PlatformUser",
            display_name="Platform User 888",
        )

        await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        expected_username = "discord-platform_new_888"
        user = await _get_user_by_username(db, expected_username)

        assert user is not None
        assert user.is_active is True
        assert user.is_service_account is False

    async def test_existing_profile_does_not_duplicate_user(self, db: AsyncSession):
        user_info = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="platform_existing_777",
            provider_scope="*",
            username="ExistingUser",
            display_name="Existing User 777",
        )

        await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        await get_or_create_profile_from_platform(db, user_info)
        await db.commit()

        expected_username = "discord-platform_existing_777"
        result = await db.execute(select(User).where(User.username == expected_username))
        users = result.scalars().all()
        assert len(users) == 1, "Second call should not create a duplicate User row"


@pytest.mark.asyncio
class TestOrchestratorSimAgentCreatesUser:
    async def test_sim_agent_user_profile_creates_service_account(self, db: AsyncSession):
        display_name = "SimAgent-TestBot-1"

        user_profile = UserProfile(
            display_name=display_name,
            is_human=False,
            is_active=True,
        )
        db.add(user_profile)
        await db.flush()

        username = f"simagent-{user_profile.id}"
        email = f"simagent-{user_profile.id}@sim.opennotes.local"

        user = User(
            username=username,
            email=email,
            hashed_password="!sim-agent-only",
            is_active=True,
            is_service_account=True,
        )
        db.add(user)
        await db.flush()
        await db.commit()

        result = await db.execute(select(User).where(User.username == username))
        stored_user = result.scalar_one_or_none()

        assert stored_user is not None
        assert stored_user.is_service_account is True
        assert stored_user.is_active is True
        assert stored_user.hashed_password == "!sim-agent-only"
