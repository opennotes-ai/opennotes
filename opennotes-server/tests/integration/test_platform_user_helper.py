"""Integration tests for _get_or_create_platform_user (Phase 1.0 helper).

Covers the synthetic-User creation path introduced in TASK-1451.01 to ensure
every UserProfile/UserIdentity creation also has a backing User row.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User
from src.users.profile_crud import (
    _get_or_create_platform_user,
    _synthetic_platform_email,
    _synthetic_platform_username,
)
from src.users.profile_schemas import AuthProvider


class TestSyntheticPlatformUsername:
    def test_username_format_discord(self) -> None:
        assert _synthetic_platform_username(AuthProvider.DISCORD, "12345") == "discord-12345"

    def test_username_format_email(self) -> None:
        assert (
            _synthetic_platform_username(AuthProvider.EMAIL, "u@example.com")
            == "email-u@example.com"
        )

    def test_username_accepts_string_provider(self) -> None:
        assert _synthetic_platform_username("discord", "99") == "discord-99"


class TestSyntheticPlatformEmail:
    def test_email_format_discord(self) -> None:
        assert (
            _synthetic_platform_email(AuthProvider.DISCORD, "12345")
            == "discord-12345@platform.opennotes.local"
        )

    def test_email_format_github(self) -> None:
        assert (
            _synthetic_platform_email(AuthProvider.GITHUB, "user-id")
            == "github-user-id@platform.opennotes.local"
        )


@pytest.mark.asyncio
class TestGetOrCreatePlatformUser:
    async def test_creates_new_user_for_discord_provider(self, db_session: AsyncSession) -> None:
        """New Discord provider → creates User with discord_id set and principal_type='human'."""
        user = await _get_or_create_platform_user(
            db_session, AuthProvider.DISCORD, "discord_new_12345"
        )

        assert user.username == "discord-discord_new_12345"
        assert user.email == "discord-discord_new_12345@platform.opennotes.local"
        assert user.discord_id == "discord_new_12345"
        assert user.is_active is True
        assert user.hashed_password == "!platform-auth-only"
        assert user.principal_type == "human"

    async def test_creates_new_user_for_email_provider(self, db_session: AsyncSession) -> None:
        """Non-Discord provider → creates User with discord_id=None."""
        user = await _get_or_create_platform_user(
            db_session, AuthProvider.EMAIL, "email_new@test.local"
        )

        assert user.username == "email-email_new@test.local"
        assert user.discord_id is None
        assert user.principal_type == "human"

    async def test_sets_agent_principal_type_for_service_account(
        self, db_session: AsyncSession
    ) -> None:
        """is_service_account=True → principal_type='agent'."""
        user = await _get_or_create_platform_user(
            db_session,
            AuthProvider.DISCORD,
            "discord_bot_111",
            is_service_account=True,
        )
        assert user.principal_type == "agent"

    async def test_idempotent_by_username(self, db_session: AsyncSession) -> None:
        """Second call with same provider/id returns existing row, doesn't create duplicate."""
        user1 = await _get_or_create_platform_user(
            db_session, AuthProvider.DISCORD, "discord_dup_222"
        )
        user2 = await _get_or_create_platform_user(
            db_session, AuthProvider.DISCORD, "discord_dup_222"
        )

        assert user1.id == user2.id

        result = await db_session.execute(
            select(User).where(User.username == "discord-discord_dup_222")
        )
        matches = result.scalars().all()
        assert len(matches) == 1

    async def test_finds_existing_user_by_discord_id(self, db_session: AsyncSession) -> None:
        """If a User with matching discord_id exists but different username, return it."""
        pre_existing = User(
            username="pre_existing_user",
            email="pre_existing@example.com",
            hashed_password="hashed",
            is_active=True,
            discord_id="discord_existing_333",
            principal_type="human",
        )
        db_session.add(pre_existing)
        await db_session.flush()

        user = await _get_or_create_platform_user(
            db_session, AuthProvider.DISCORD, "discord_existing_333"
        )

        assert user.id == pre_existing.id
        assert user.username == "pre_existing_user"

    async def test_accepts_string_provider(self, db_session: AsyncSession) -> None:
        """Provider can be a string, not just an AuthProvider enum value."""
        user = await _get_or_create_platform_user(db_session, "discord", "discord_str_444")
        assert user.discord_id == "discord_str_444"
        assert user.principal_type == "human"
