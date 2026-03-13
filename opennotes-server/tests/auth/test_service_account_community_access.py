"""
Tests for service account auto-creation and community membership verification.

This module tests the automatic creation of UserProfile, UserIdentity, and
CommunityMember records for service accounts (bots) when they access
protected community endpoints.
"""

import asyncio
from contextlib import AsyncExitStack
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import community_dependencies
from src.auth.community_dependencies import get_profile_id_from_user, verify_community_membership
from src.auth.permissions import is_service_account as _is_service_account
from src.users.models import User
from src.users.profile_crud import (
    get_identity_by_provider,
    get_profile_by_id,
)
from src.users.profile_models import UserIdentity, UserProfile
from src.users.profile_schemas import AuthProvider


class TestServiceAccountDetection:
    """Test service account detection logic."""

    def test_detect_service_account_by_email(self):
        """Service accounts with @opennotes.local email should be detected."""
        user = User(
            id=1,
            username="discord-bot-service",
            email="discord-bot@opennotes.local",
            hashed_password="unused",
            role="admin",
        )
        assert _is_service_account(user) is True

    def test_detect_service_account_by_username(self):
        """Service accounts with -service suffix should be detected."""
        user = User(
            id=1,
            username="test-service",
            email="test@example.com",
            hashed_password="unused",
            role="user",
        )
        assert _is_service_account(user) is True

    def test_regular_user_not_detected_as_service_account(self):
        """Regular users should not be detected as service accounts."""
        user = User(
            id=1,
            username="regularuser",
            email="user@example.com",
            hashed_password="unused",
            role="user",
        )
        assert _is_service_account(user) is False


@pytest.mark.asyncio
class TestServiceAccountProfileCreation:
    """Test automatic profile and identity creation for service accounts."""

    async def test_create_profile_for_service_account(self, setup_database):
        """Service accounts should have profile and identity auto-created."""
        from src.database import get_engine

        async with AsyncSession(get_engine()) as db:
            user = User(
                id=1,
                username="discord-bot-service",
                email="discord-bot@opennotes.local",
                hashed_password="unused",
                role="admin",
            )

            # First call should create profile and identity
            profile_id = await get_profile_id_from_user(db, user)
            assert profile_id is not None

            # Verify profile was created with is_human=False
            profile = await get_profile_by_id(db, profile_id)
            assert profile is not None
            assert profile.is_human is False
            assert profile.display_name == "discord-bot-service"
            assert "Service account" in profile.bio

            # Verify identity was created
            identity = await get_identity_by_provider(
                db, AuthProvider.EMAIL, "discord-bot@opennotes.local"
            )
            assert identity is not None
            assert identity.profile_id == profile_id

            # Second call should return same profile_id
            profile_id_2 = await get_profile_id_from_user(db, user)
            assert profile_id_2 == profile_id

    async def test_regular_user_not_auto_created(self, setup_database):
        """Regular users should NOT have profile auto-created."""
        from src.database import get_engine

        async with AsyncSession(get_engine()) as db:
            user = User(
                id=1,
                username="regularuser",
                email="user@example.com",
                hashed_password="unused",
                role="user",
            )

            # Should return None since no identity exists and not a service account
            profile_id = await get_profile_id_from_user(db, user)
            assert profile_id is None

    async def test_concurrent_service_account_profile_create_recovers_duplicate(
        self, setup_database
    ):
        """Concurrent service-account bootstrap should converge on one profile and identity."""
        from unittest.mock import AsyncMock, patch

        from src.database import get_session_maker

        user = User(
            id=1,
            username="discord-bot-service",
            email="discord-bot@opennotes.local",
            hashed_password="unused",
            role="admin",
        )

        ready_count = 0
        ready_lock = asyncio.Lock()
        release_create = asyncio.Event()
        initial_lookup_count = 0
        initial_lookup_lock = asyncio.Lock()
        real_get_identity_by_provider = community_dependencies.get_identity_by_provider

        async def coordinated_create(*args, **kwargs):
            nonlocal ready_count
            async with ready_lock:
                ready_count += 1
                if ready_count == 2:
                    release_create.set()

            await asyncio.wait_for(release_create.wait(), timeout=5)

            db = kwargs["db"]
            profile_create = kwargs["profile_create"]
            provider = kwargs["provider"]
            provider_user_id = kwargs["provider_user_id"]
            credentials = kwargs["credentials"]

            profile = UserProfile(
                display_name=profile_create.display_name,
                avatar_url=profile_create.avatar_url,
                bio=profile_create.bio,
                is_human=profile_create.is_human,
                reputation=0,
            )
            db.add(profile)
            await db.flush()

            identity = UserIdentity(
                profile_id=profile.id,
                provider=provider.value if hasattr(provider, "value") else provider,
                provider_user_id=provider_user_id,
                credentials=credentials,
            )
            db.add(identity)
            await db.flush()
            return profile, identity

        async def coordinated_get_identity(*args, **kwargs):
            nonlocal initial_lookup_count
            async with initial_lookup_lock:
                if initial_lookup_count < 2:
                    initial_lookup_count += 1
                    return None

            return await real_get_identity_by_provider(*args, **kwargs)

        async with AsyncExitStack() as stack:
            session_one = await stack.enter_async_context(get_session_maker()())
            session_two = await stack.enter_async_context(get_session_maker()())

            await session_one.execute(text("SELECT 1"))
            await session_two.execute(text("SELECT 1"))

            async def fetch_profile_id(session: AsyncSession):
                profile_id = await get_profile_id_from_user(session, user)
                await session.commit()
                return profile_id

            patched_create = AsyncMock(side_effect=coordinated_create)
            patched_get_identity = AsyncMock(side_effect=coordinated_get_identity)
            with (
                patch(
                    "src.auth.community_dependencies.create_profile_with_identity",
                    new=patched_create,
                ),
                patch(
                    "src.auth.community_dependencies.get_identity_by_provider",
                    new=patched_get_identity,
                ),
            ):
                results = await asyncio.gather(
                    fetch_profile_id(session_one),
                    fetch_profile_id(session_two),
                    return_exceptions=True,
                )

        assert not [result for result in results if isinstance(result, Exception)], results
        profile_ids = results
        assert profile_ids[0] == profile_ids[1]

        async with get_session_maker()() as session:
            identity_count_result = await session.execute(
                select(func.count(UserIdentity.id)).where(
                    UserIdentity.provider == AuthProvider.EMAIL.value,
                    UserIdentity.provider_user_id == "discord-bot@opennotes.local",
                )
            )
            profile_count_result = await session.execute(
                select(func.count(UserProfile.id)).where(UserProfile.id == profile_ids[0])
            )

        assert identity_count_result.scalar_one() == 1
        assert profile_count_result.scalar_one() == 1


@pytest.mark.asyncio
class TestServiceAccountCommunityMembership:
    """Test automatic community membership creation for service accounts."""

    async def test_auto_create_community_membership_for_bot(self, setup_database):
        """Bot users should have community membership auto-created."""
        from unittest.mock import MagicMock

        from src.database import get_engine
        from src.llm_config.models import CommunityServer

        async with AsyncSession(get_engine()) as db:
            # Create a test community server
            community = CommunityServer(
                platform="discord",
                platform_community_server_id="123456789",
                name="Test Server",
                is_active=True,
                is_public=True,
            )
            db.add(community)
            await db.flush()

            # Create service account user
            user = User(
                id=1,
                username="discord-bot-service",
                email="discord-bot@opennotes.local",
                hashed_password="unused",
                role="admin",
            )

            # Mock request object
            mock_request = MagicMock()
            mock_request.headers.get.return_value = "false"

            # Call verify_community_membership - should auto-create everything
            membership = await verify_community_membership("123456789", user, db, mock_request)

            # Verify membership was created
            assert membership is not None
            assert membership.is_active is True
            assert membership.role == "member"
            assert membership.invitation_reason == "Auto-created for service account"

            # Verify profile is not human
            profile = await get_profile_by_id(db, membership.profile_id)
            assert profile is not None
            assert profile.is_human is False

    async def test_concurrent_verify_membership_bootstrap_recovers_without_orphans(
        self, setup_database
    ):
        """Concurrent verify_community_membership calls should not leak extra profiles."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.database import get_session_maker

        service_suffix = uuid4().hex[:8]
        guild_id = f"guild-{service_suffix}"
        service_username = f"verify-bot-{service_suffix}-service"
        service_email = f"verify-bot-{service_suffix}@opennotes.local"

        user = User(
            id=1,
            username=service_username,
            email=service_email,
            hashed_password="unused",
            role="admin",
        )
        community = MagicMock()
        community.id = uuid4()
        community.platform = "discord"
        community.platform_community_server_id = guild_id
        mock_request = MagicMock()
        mock_request.headers = {}

        ready_count = 0
        ready_lock = asyncio.Lock()
        release_create = asyncio.Event()
        initial_lookup_count = 0
        initial_lookup_lock = asyncio.Lock()
        real_get_identity_by_provider = community_dependencies.get_identity_by_provider

        async def coordinated_create(*args, **kwargs):
            nonlocal ready_count
            async with ready_lock:
                ready_count += 1
                if ready_count == 2:
                    release_create.set()

            await asyncio.wait_for(release_create.wait(), timeout=5)

            db = kwargs["db"]
            profile_create = kwargs["profile_create"]
            provider = kwargs["provider"]
            provider_user_id = kwargs["provider_user_id"]
            credentials = kwargs["credentials"]

            profile = UserProfile(
                display_name=profile_create.display_name,
                avatar_url=profile_create.avatar_url,
                bio=profile_create.bio,
                is_human=profile_create.is_human,
                reputation=0,
            )
            db.add(profile)
            await db.flush()

            identity = UserIdentity(
                profile_id=profile.id,
                provider=provider.value if hasattr(provider, "value") else provider,
                provider_user_id=provider_user_id,
                credentials=credentials,
            )
            db.add(identity)
            await db.flush()
            return profile, identity

        async def coordinated_get_identity(*args, **kwargs):
            nonlocal initial_lookup_count
            async with initial_lookup_lock:
                if initial_lookup_count < 2:
                    initial_lookup_count += 1
                    return None

            return await real_get_identity_by_provider(*args, **kwargs)

        recovered_membership_id = uuid4()

        async def fake_ensure_membership_with_permissions(*, profile, **_kwargs):
            membership = MagicMock()
            membership.profile_id = profile.id
            membership.id = recovered_membership_id
            return membership

        async with AsyncExitStack() as stack:
            session_one = await stack.enter_async_context(get_session_maker()())
            session_two = await stack.enter_async_context(get_session_maker()())

            await session_one.execute(text("SELECT 1"))
            await session_two.execute(text("SELECT 1"))

            async def verify_membership(session: AsyncSession):
                membership = await verify_community_membership(
                    guild_id, user, session, mock_request
                )
                await session.commit()
                return membership.profile_id, membership.id

            patched_create = AsyncMock(side_effect=coordinated_create)
            patched_get_identity = AsyncMock(side_effect=coordinated_get_identity)
            with (
                patch(
                    "src.auth.community_dependencies.get_community_server_by_platform_id",
                    new=AsyncMock(return_value=community),
                ),
                patch(
                    "src.auth.community_dependencies._ensure_membership_with_permissions",
                    new=AsyncMock(side_effect=fake_ensure_membership_with_permissions),
                ),
                patch(
                    "src.auth.community_dependencies.create_profile_with_identity",
                    new=patched_create,
                ),
                patch(
                    "src.auth.community_dependencies.get_identity_by_provider",
                    new=patched_get_identity,
                ),
            ):
                results = await asyncio.gather(
                    verify_membership(session_one),
                    verify_membership(session_two),
                    return_exceptions=True,
                )

        assert not [result for result in results if isinstance(result, Exception)], results
        profile_ids = [profile_id for profile_id, _membership_id in results]
        membership_ids = [membership_id for _profile_id, membership_id in results]
        assert profile_ids[0] == profile_ids[1]
        assert membership_ids[0] == membership_ids[1]
        assert patched_create.await_count == 2

        expected_bio = f"Service account: {service_username}"
        async with get_session_maker()() as session:
            identity_count_result = await session.execute(
                select(func.count(UserIdentity.id)).where(
                    UserIdentity.provider == AuthProvider.EMAIL.value,
                    UserIdentity.provider_user_id == service_email,
                )
            )
            profile_count_result = await session.execute(
                select(func.count(UserProfile.id)).where(
                    UserProfile.display_name == service_username,
                    UserProfile.bio == expected_bio,
                )
            )

        assert identity_count_result.scalar_one() == 1
        assert profile_count_result.scalar_one() == 1

    async def test_service_account_bypasses_ban_check(self, setup_database):
        """Service accounts should bypass banned_at checks."""
        from unittest.mock import MagicMock

        import pendulum

        from src.database import get_engine
        from src.llm_config.models import CommunityServer
        from src.users.profile_crud import (
            create_community_member,
            create_profile_with_identity,
        )
        from src.users.profile_schemas import (
            CommunityMemberCreate,
            CommunityRole,
            UserProfileCreate,
        )

        async with AsyncSession(get_engine()) as db:
            # Create community
            community = CommunityServer(
                platform="discord",
                platform_community_server_id="987654321",
                name="Test Server 2",
                is_active=True,
                is_public=True,
            )
            db.add(community)
            await db.flush()

            # Create service account profile manually
            profile_create = UserProfileCreate(
                display_name="test-bot",
                avatar_url=None,
                bio="Test service account",
                is_human=False,
            )
            profile, _identity = await create_profile_with_identity(
                db=db,
                profile_create=profile_create,
                provider=AuthProvider.EMAIL,
                provider_user_id="test-bot@opennotes.local",
                credentials=None,
            )
            await db.flush()

            # Create membership with banned_at set
            member_create = CommunityMemberCreate(
                community_id=community.id,
                profile_id=profile.id,
                is_external=False,
                role=CommunityRole.MEMBER,
                permissions=None,
                joined_at=pendulum.now("UTC"),
                invited_by=None,
                invitation_reason="Test",
            )
            membership = await create_community_member(db, member_create)
            membership.banned_at = pendulum.now("UTC")
            membership.banned_reason = "Test ban"
            await db.flush()

            # Create user
            user = User(
                id=1,
                username="test-bot-service",
                email="test-bot@opennotes.local",
                hashed_password="unused",
                role="user",
            )

            # Mock request object
            mock_request = MagicMock()
            mock_request.headers.get.return_value = "false"

            # Should NOT raise 403 for banned service account
            result_membership = await verify_community_membership(
                "987654321", user, db, mock_request
            )
            assert result_membership is not None
            assert result_membership.banned_at is not None  # Still banned in DB
            # But verification passed because is_human=False

    async def test_human_user_ban_check_enforced(self, setup_database):
        """Human users should still be blocked by banned_at."""
        from unittest.mock import MagicMock

        import pendulum
        from fastapi import HTTPException

        from src.database import get_engine
        from src.llm_config.models import CommunityServer
        from src.users.profile_crud import (
            create_community_member,
            create_profile_with_identity,
        )
        from src.users.profile_schemas import (
            CommunityMemberCreate,
            CommunityRole,
            UserProfileCreate,
        )

        async with AsyncSession(get_engine()) as db:
            # Create community
            community = CommunityServer(
                platform="discord",
                platform_community_server_id="111222333",
                name="Test Server 3",
                is_active=True,
                is_public=True,
            )
            db.add(community)
            await db.flush()

            # Create human profile
            profile_create = UserProfileCreate(
                display_name="humanuser",
                avatar_url=None,
                bio="Human user",
                is_human=True,
            )
            profile, _identity = await create_profile_with_identity(
                db=db,
                profile_create=profile_create,
                provider=AuthProvider.EMAIL,
                provider_user_id="human@example.com",
                credentials=None,
            )
            await db.flush()

            # Create membership with banned_at set
            member_create = CommunityMemberCreate(
                community_id=community.id,
                profile_id=profile.id,
                is_external=False,
                role=CommunityRole.MEMBER,
                permissions=None,
                joined_at=pendulum.now("UTC"),
                invited_by=None,
                invitation_reason="Test",
            )
            membership = await create_community_member(db, member_create)
            membership.banned_at = pendulum.now("UTC")
            membership.banned_reason = "Test ban"
            await db.flush()

            # Create user
            user = User(
                id=1,
                username="humanuser",
                email="human@example.com",
                hashed_password="unused",
                role="user",
            )

            # Mock request object
            mock_request = MagicMock()
            mock_request.headers.get.return_value = "false"

            # Should raise 403 for banned human user
            with pytest.raises(HTTPException) as exc_info:
                await verify_community_membership("111222333", user, db, mock_request)

            assert exc_info.value.status_code == 403
            assert "banned" in exc_info.value.detail.lower()
