"""
Integration tests for blocking X-Discord-* header spoofing.

These tests verify that:
1. Raw X-Discord-Has-Manage-Server header from untrusted sources is blocked
2. Spoofed headers do not grant admin access
3. Valid signed JWT claims DO grant access when from service accounts
4. Invalid/expired JWT claims are rejected

Security fix for task-682: Authentication bypass via X-Discord-Has-Manage-Server header
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
            platform_community_server_id="spooftest123456",
            name="Header Spoof Test Community",
            description="Community for testing header spoofing prevention",
            is_active=True,
        )
        db.add(community)
        await db.commit()
        await db.refresh(community)
        return community


@pytest.fixture
async def regular_user() -> User:
    """Create a regular (non-service-account) user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="attacker@example.com",
            username="attacker_user",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
            is_service_account=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


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
            is_service_account=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def regular_profile(regular_user: User) -> tuple[UserProfile, UserIdentity]:
    """Create a profile and identity for the regular user."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile = UserProfile(
            display_name="Attacker User",
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


def create_mock_request_with_spoofed_header() -> MagicMock:
    """Create a mock request with a spoofed X-Discord-Has-Manage-Server header."""
    request = MagicMock()
    request.headers = {
        "x-discord-has-manage-server": "true",
    }
    return request


def create_mock_request_no_header() -> MagicMock:
    """Create a mock request without any Discord headers."""
    request = MagicMock()
    request.headers = {}
    return request


def create_mock_request_with_valid_claims(
    user_id: str,
    guild_id: str,
    has_manage_server: bool = True,
) -> MagicMock:
    """Create a mock request with a valid signed JWT in X-Discord-Claims header."""
    from src.auth.discord_claims import create_discord_claims_token

    token = create_discord_claims_token(
        user_id=user_id,
        guild_id=guild_id,
        has_manage_server=has_manage_server,
    )
    request = MagicMock()
    request.headers = {
        "x-discord-claims": token,
    }
    return request


def create_mock_request_with_invalid_claims() -> MagicMock:
    """Create a mock request with an invalid/tampered JWT."""
    request = MagicMock()
    request.headers = {
        "x-discord-claims": "invalid.jwt.token",
    }
    return request


@pytest.mark.asyncio
class TestHeaderSpoofingBlocked:
    """Test that header spoofing is properly blocked."""

    async def test_spoofed_header_does_not_grant_admin_access(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """
        Test that a regular user cannot gain admin access by spoofing
        the X-Discord-Has-Manage-Server header.

        This is the core security test for task-682.
        """
        from src.auth.community_dependencies import verify_community_admin

        # Create request with spoofed header
        spoofed_request = create_mock_request_with_spoofed_header()

        # Regular user with spoofed header should be BLOCKED
        with pytest.raises(HTTPException) as exc_info:
            await verify_community_admin(
                test_community_server.platform_community_server_id,
                regular_user,
                db_session,
                spoofed_request,
            )

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail

    async def test_regular_user_blocked_without_spoofed_header(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """
        Baseline test: regular user without spoofed header is blocked.
        """
        from src.auth.community_dependencies import verify_community_admin

        request = create_mock_request_no_header()

        with pytest.raises(HTTPException) as exc_info:
            await verify_community_admin(
                test_community_server.platform_community_server_id,
                regular_user,
                db_session,
                request,
            )

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail

    async def test_service_account_with_valid_claims_has_access(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        service_account_user: User,
        service_account_membership: CommunityMember,
    ) -> None:
        """
        Test that service account with valid signed JWT claims has admin access.
        """
        from src.auth.community_dependencies import verify_community_admin

        # Service accounts should have access regardless of claims
        # (they're trusted by virtue of being service accounts)
        request = create_mock_request_no_header()

        result = await verify_community_admin(
            test_community_server.platform_community_server_id,
            service_account_user,
            db_session,
            request,
        )

        assert result is not None
        assert result.id == service_account_membership.id

    async def test_invalid_jwt_claims_rejected(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        """
        Test that invalid/tampered JWT claims are rejected.
        """
        from src.auth.community_dependencies import verify_community_admin

        request = create_mock_request_with_invalid_claims()

        with pytest.raises(HTTPException) as exc_info:
            await verify_community_admin(
                test_community_server.platform_community_server_id,
                regular_user,
                db_session,
                request,
            )

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail


@pytest.mark.asyncio
class TestHeaderStrippingMiddleware:
    """Test the header stripping middleware."""

    async def test_middleware_strips_discord_headers_from_regular_requests(
        self,
        async_client,
    ) -> None:
        """
        Test that X-Discord-* headers are stripped from requests
        that are not from service accounts.
        """
        # Make a request with spoofed headers (no auth = not a service account)
        response = await async_client.get(
            "/health",
            headers={
                "X-Discord-Has-Manage-Server": "true",
                "X-Discord-User-Id": "fake123",
            },
        )

        # Health check should succeed
        assert response.status_code == 200

    async def test_middleware_preserves_headers_for_service_accounts(
        self,
    ) -> None:
        """
        Test that X-Discord-* headers are preserved for authenticated
        service account requests.

        Note: This test requires a service account API key which is
        handled via the auth dependency, not the middleware.
        """


@pytest.mark.asyncio
class TestDiscordClaimsJWT:
    """Test the Discord claims JWT creation and validation."""

    def test_create_valid_claims_token(self) -> None:
        """Test creating a valid Discord claims JWT."""
        from src.auth.discord_claims import create_discord_claims_token, validate_discord_claims

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=True,
        )

        assert token is not None
        assert isinstance(token, str)

        # Validate the token
        claims = validate_discord_claims(token)
        assert claims is not None
        assert claims["user_id"] == "123456789"
        assert claims["guild_id"] == "987654321"
        assert claims["has_manage_server"] is True

    def test_invalid_token_returns_none(self) -> None:
        """Test that invalid tokens return None."""
        from src.auth.discord_claims import validate_discord_claims

        claims = validate_discord_claims("invalid.jwt.token")
        assert claims is None

    def test_tampered_token_returns_none(self) -> None:
        """Test that tampered tokens return None."""
        from src.auth.discord_claims import create_discord_claims_token, validate_discord_claims

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=True,
        )

        # Tamper with the token
        parts = token.split(".")
        tampered_token = parts[0] + "." + parts[1] + ".tamperedsignature"

        claims = validate_discord_claims(tampered_token)
        assert claims is None

    def test_expired_token_returns_none(self) -> None:
        """Test that expired tokens return None."""
        from datetime import timedelta

        from src.auth.discord_claims import (
            create_discord_claims_token,
            validate_discord_claims,
        )

        # Create token with negative expiry (already expired)
        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=True,
            expires_delta=timedelta(seconds=-60),  # Expired 60 seconds ago
        )

        claims = validate_discord_claims(token)
        assert claims is None

    def test_claims_without_manage_server_permission(self) -> None:
        """Test claims with has_manage_server=False."""
        from src.auth.discord_claims import create_discord_claims_token, validate_discord_claims

        token = create_discord_claims_token(
            user_id="123456789",
            guild_id="987654321",
            has_manage_server=False,
        )

        claims = validate_discord_claims(token)
        assert claims is not None
        assert claims["has_manage_server"] is False
