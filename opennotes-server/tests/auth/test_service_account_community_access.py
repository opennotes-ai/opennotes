"""
Tests for service account auto-creation and community membership verification.

This module tests the automatic creation of UserProfile, UserIdentity, and
CommunityMember records for service accounts (bots) when they access
protected community endpoints.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    _get_profile_id_from_user,
    verify_community_membership,
)
from src.auth.permissions import is_service_account as _is_service_account
from src.users.models import User
from src.users.profile_crud import (
    get_identity_by_provider,
    get_profile_by_id,
)
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
            profile_id = await _get_profile_id_from_user(db, user)
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
            profile_id_2 = await _get_profile_id_from_user(db, user)
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
            profile_id = await _get_profile_id_from_user(db, user)
            assert profile_id is None


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

    async def test_service_account_bypasses_ban_check(self, setup_database):
        """Service accounts should bypass banned_at checks."""
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

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
                joined_at=datetime.now(UTC),
                invited_by=None,
                invitation_reason="Test",
            )
            membership = await create_community_member(db, member_create)
            membership.banned_at = datetime.now(UTC)
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
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

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
                joined_at=datetime.now(UTC),
                invited_by=None,
                invitation_reason="Test",
            )
            membership = await create_community_member(db, member_create)
            membership.banned_at = datetime.now(UTC)
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
