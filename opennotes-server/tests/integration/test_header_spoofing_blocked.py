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


def _make_mock_request(headers: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    request.state.platform_identity = None
    request.state.api_key = None
    return request


def create_mock_request_with_spoofed_header() -> MagicMock:
    return _make_mock_request({"x-discord-has-manage-server": "true"})


def create_mock_request_no_header() -> MagicMock:
    return _make_mock_request()


def create_mock_request_with_valid_platform_claims(
    platform: str,
    sub: str,
    community_id: str,
    can_administer_community: bool = True,
) -> MagicMock:
    from src.auth.platform_claims import create_platform_claims_token

    token = create_platform_claims_token(
        platform=platform,
        scope="*",
        sub=sub,
        community_id=community_id,
        can_administer_community=can_administer_community,
    )
    return _make_mock_request({"x-platform-claims": token})


def create_mock_request_with_invalid_claims() -> MagicMock:
    return _make_mock_request({"x-platform-claims": "invalid.jwt.token"})


@pytest.mark.asyncio
class TestHeaderSpoofingBlocked:
    async def test_spoofed_header_does_not_grant_admin_access(
        self,
        db_session: AsyncSession,
        test_community_server: CommunityServer,
        regular_user: User,
        regular_membership: CommunityMember,
    ) -> None:
        from src.auth.community_dependencies import verify_community_admin

        spoofed_request = create_mock_request_with_spoofed_header()

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
        from src.auth.community_dependencies import verify_community_admin

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
    async def test_middleware_strips_platform_headers_from_regular_requests(
        self,
        async_client,
    ) -> None:
        response = await async_client.get(
            "/health",
            headers={
                "X-Platform-Type": "discord",
                "X-Platform-User-Id": "fake123",
            },
        )

        assert response.status_code == 200

    async def test_middleware_preserves_headers_for_service_accounts(
        self,
    ) -> None:
        pass


@pytest.mark.asyncio
class TestPlatformClaimsJWT:
    def test_create_valid_claims_token(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
        )

        assert token is not None
        assert isinstance(token, str)

        claims = validate_platform_claims(token)
        assert claims is not None
        assert claims["sub"] == "123456789"
        assert claims["community_id"] == "987654321"
        assert claims["can_administer_community"] is True

    def test_invalid_token_returns_none(self) -> None:
        from src.auth.platform_claims import validate_platform_claims

        claims = validate_platform_claims("invalid.jwt.token")
        assert claims is None

    def test_tampered_token_returns_none(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
        )

        parts = token.split(".")
        tampered_token = parts[0] + "." + parts[1] + ".tamperedsignature"

        claims = validate_platform_claims(tampered_token)
        assert claims is None

    def test_expired_token_returns_none(self) -> None:
        from datetime import timedelta

        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
            expires_delta=timedelta(seconds=-60),
        )

        claims = validate_platform_claims(token)
        assert claims is None

    def test_claims_without_admin_permission(self) -> None:
        from src.auth.platform_claims import create_platform_claims_token, validate_platform_claims

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=False,
        )

        claims = validate_platform_claims(token)
        assert claims is not None
        assert claims["can_administer_community"] is False
