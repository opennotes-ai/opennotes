"""
Tests for community admin management endpoints.

Tests community-level admin management functionality including adding admins,
removing admins, and listing admins with proper authorization checks.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.llm_config.models import CommunityServer
from src.users.models import User
from src.users.profile_crud import (
    create_community_member,
    create_profile_with_identity,
    get_community_member,
)
from src.users.profile_schemas import (
    AuthProvider,
    CommunityMemberCreate,
    CommunityRole,
    UserProfileCreate,
)


@pytest.fixture
async def service_account() -> User:
    """Create a test service account."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="service-account@opennotes.local",
            username="service-account",
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
async def service_account_headers(service_account: User):
    """Generate valid JWT token for service account authenticated requests."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(service_account.id),
        "username": service_account.username,
        "role": service_account.role,
    }
    access_token = create_access_token(token_data)  # type: ignore[arg-type]
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def community_server() -> CommunityServer:
    """Create a test community server."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        server = CommunityServer(
            platform="discord",
            platform_id="123456789",
            name="Test Server",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


@pytest.fixture
async def admin_user(community_server: CommunityServer):
    """Create a test admin user with membership."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile_create = UserProfileCreate(
            display_name="Admin User",
            avatar_url=None,
            bio="Test admin",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id="admin_discord_id",
            credentials=None,
        )

        member_create = CommunityMemberCreate(
            community_id=community_server.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test admin",
        )
        await create_community_member(db, member_create)
        await db.commit()

        return {"profile": profile, "identity": identity}


@pytest.fixture
async def regular_user(community_server: CommunityServer):
    """Create a test regular user with membership."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile_create = UserProfileCreate(
            display_name="Regular User",
            avatar_url=None,
            bio="Test user",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id="regular_discord_id",
            credentials=None,
        )

        member_create = CommunityMemberCreate(
            community_id=community_server.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test member",
        )
        await create_community_member(db, member_create)
        await db.commit()

        return {"profile": profile, "identity": identity}


@pytest.fixture
async def non_member_user():
    """Create a test user who is not a member of the community."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        profile_create = UserProfileCreate(
            display_name="Non-Member User",
            avatar_url=None,
            bio="Test non-member",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id="nonmember_discord_id",
            credentials=None,
        )
        await db.commit()

        return {"profile": profile, "identity": identity}


@pytest.mark.asyncio
async def test_add_community_admin_success(
    service_account_headers: dict,
    community_server: CommunityServer,
    regular_user: dict,
):
    """Test successfully adding a community admin."""
    from src.database import get_session_maker
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/community-servers/{community_server.platform_id}/admins",
            json={"user_discord_id": regular_user["identity"].provider_user_id},
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["profile_id"] == str(regular_user["profile"].id)
        assert data["discord_id"] == regular_user["identity"].provider_user_id
        assert data["community_role"] == "admin"
        assert "community_role" in data["admin_sources"]

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        membership = await get_community_member(db, community_server.id, regular_user["profile"].id)
        assert membership is not None
        assert membership.role == "admin"


@pytest.mark.asyncio
async def test_add_community_admin_non_member(
    service_account_headers: dict,
    community_server: CommunityServer,
    non_member_user: dict,
):
    """Test adding a non-member as admin creates membership."""
    from src.database import get_session_maker
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.post(
            f"/api/v1/community-servers/{community_server.platform_id}/admins",
            json={"user_discord_id": non_member_user["identity"].provider_user_id},
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["profile_id"] == str(non_member_user["profile"].id)
        assert data["community_role"] == "admin"

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        membership = await get_community_member(
            db, community_server.id, non_member_user["profile"].id
        )
        assert membership is not None
        assert membership.role == "admin"


@pytest.mark.asyncio
async def test_add_community_admin_user_not_found(
    service_account_headers: dict,
    community_server: CommunityServer,
):
    """Test adding admin for non-existent user auto-creates the user."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.post(
            f"/api/v1/community-servers/{community_server.platform_id}/admins",
            json={"user_discord_id": "nonexistent_user"},
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["discord_id"] == "nonexistent_user"
        assert data["community_role"] == "admin"


@pytest.mark.asyncio
async def test_add_community_admin_community_not_found(
    service_account_headers: dict,
    regular_user: dict,
):
    """Test adding admin for non-existent community auto-creates it."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.post(
            "/api/v1/community-servers/999999999/admins",
            json={"user_discord_id": regular_user["identity"].provider_user_id},
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["discord_id"] == regular_user["identity"].provider_user_id
        assert data["community_role"] == "admin"


@pytest.mark.asyncio
async def test_remove_community_admin_success(
    service_account_headers: dict,
    community_server: CommunityServer,
    admin_user: dict,
    regular_user: dict,
):
    """Test successfully removing a community admin."""
    from src.database import get_session_maker
    from src.main import app

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        member_membership = await get_community_member(
            db, community_server.id, regular_user["profile"].id
        )
        member_membership.role = "admin"  # type: ignore[union-attr]
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.delete(
            f"/api/v1/community-servers/{community_server.platform_id}/admins/{admin_user['identity'].provider_user_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["profile_id"] == str(admin_user["profile"].id)
        assert data["previous_role"] == "admin"
        assert data["new_role"] == "member"

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        membership = await get_community_member(db, community_server.id, admin_user["profile"].id)
        assert membership is not None
        assert membership.role == "member"


@pytest.mark.asyncio
async def test_remove_last_admin_fails(
    service_account_headers: dict,
    community_server: CommunityServer,
    admin_user: dict,
):
    """Test that removing the last admin is prevented."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.delete(
            f"/api/v1/community-servers/{community_server.platform_id}/admins/{admin_user['identity'].provider_user_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 409
        assert "last admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_non_admin_fails(
    service_account_headers: dict,
    community_server: CommunityServer,
    regular_user: dict,
):
    """Test that removing a non-admin user fails."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.delete(
            f"/api/v1/community-servers/{community_server.platform_id}/admins/{regular_user['identity'].provider_user_id}",
            headers=service_account_headers,
        )

        assert response.status_code == 400
        assert "not an admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_community_admins(
    service_account_headers: dict,
    community_server: CommunityServer,
    admin_user: dict,
):
    """Test listing community admins."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.get(
            f"/api/v1/community-servers/{community_server.platform_id}/admins",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Find the admin user in the list
        admin_data = next(
            (item for item in data if item["profile_id"] == str(admin_user["profile"].id)),
            None,
        )
        assert admin_data is not None
        assert admin_data["discord_id"] == admin_user["identity"].provider_user_id
        assert admin_data["community_role"] == "admin"
        assert "community_role" in admin_data["admin_sources"]


@pytest.mark.asyncio
async def test_list_community_admins_includes_opennotes_admins(
    service_account_headers: dict,
    community_server: CommunityServer,
    regular_user: dict,
):
    """Test that listing admins includes Open Notes platform admins."""
    from src.database import get_session_maker
    from src.main import app

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        from sqlalchemy import select

        from src.users.profile_models import UserProfile

        stmt = select(UserProfile).where(UserProfile.id == regular_user["profile"].id)
        result = await db.execute(stmt)
        profile = result.scalar_one()
        profile.is_opennotes_admin = True
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.get(
            f"/api/v1/community-servers/{community_server.platform_id}/admins",
            headers=service_account_headers,
        )

        assert response.status_code == 200
        data = response.json()

        opennotes_admin = next(
            (item for item in data if item["profile_id"] == str(regular_user["profile"].id)),
            None,
        )
        assert opennotes_admin is not None
        assert opennotes_admin["is_opennotes_admin"] is True
        assert "opennotes_platform" in opennotes_admin["admin_sources"]
