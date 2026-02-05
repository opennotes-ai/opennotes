"""Tests for PATCH /community-servers/{id}/flashpoint-detection endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.llm_config.models import CommunityServer
from src.users.models import User


@pytest.fixture
async def fp_service_account():
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="fp-test-service@opennotes.local",
            username="fp-test-service",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
            is_service_account=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    yield user

    async with get_session_maker()() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.fixture
async def fp_service_account_headers(fp_service_account: User):
    """Generate valid JWT token for service account."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(fp_service_account.id),
        "username": fp_service_account.username,
        "role": fp_service_account.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def fp_regular_user():
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="fp-regular@opennotes.local",
            username="fp-regular-user",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
            is_service_account=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    yield user

    async with get_session_maker()() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.fixture
async def fp_regular_user_headers(fp_regular_user: User):
    """Generate valid JWT token for regular user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(fp_regular_user.id),
        "username": fp_regular_user.username,
        "role": fp_regular_user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def fp_test_community_server():
    from uuid import uuid4

    from src.database import get_session_maker

    unique_suffix = uuid4().hex[:8]
    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        server = CommunityServer(
            platform="discord",
            platform_community_server_id=f"fp_test_{unique_suffix}",
            name=f"Flashpoint Test Server {unique_suffix}",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        server_id = server.id

    yield server

    async with get_session_maker()() as db:
        await db.execute(delete(CommunityServer).where(CommunityServer.id == server_id))
        await db.commit()


class TestFlashpointDetectionEndpoint:
    """Tests for PATCH /api/v1/community-servers/{platform_id}/flashpoint-detection."""

    @pytest.mark.asyncio
    async def test_enable_flashpoint_detection_success(
        self,
        fp_service_account_headers: dict,
        fp_test_community_server: CommunityServer,
    ):
        """Service account can enable flashpoint detection."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                headers=fp_service_account_headers,
                json={"enabled": True},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["flashpoint_detection_enabled"] is True
        assert (
            data["platform_community_server_id"]
            == fp_test_community_server.platform_community_server_id
        )

    @pytest.mark.asyncio
    async def test_disable_flashpoint_detection_success(
        self,
        fp_service_account_headers: dict,
        fp_test_community_server: CommunityServer,
    ):
        """Service account can disable flashpoint detection."""
        from src.database import get_session_maker
        from src.main import app

        async_session_maker = get_session_maker()
        async with async_session_maker() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(CommunityServer).where(CommunityServer.id == fp_test_community_server.id)
            )
            server = result.scalar_one()
            server.flashpoint_detection_enabled = True
            await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                headers=fp_service_account_headers,
                json={"enabled": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["flashpoint_detection_enabled"] is False

    @pytest.mark.asyncio
    async def test_flashpoint_detection_persisted(
        self,
        fp_service_account_headers: dict,
        fp_test_community_server: CommunityServer,
    ):
        """Flashpoint detection setting is persisted in the database."""
        from src.database import get_session_maker
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                headers=fp_service_account_headers,
                json={"enabled": True},
            )

        assert response.status_code == 200

        async_session_maker = get_session_maker()
        async with async_session_maker() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(CommunityServer).where(CommunityServer.id == fp_test_community_server.id)
            )
            server = result.scalar_one()
            assert server.flashpoint_detection_enabled is True

    @pytest.mark.asyncio
    async def test_flashpoint_detection_not_found(
        self,
        fp_service_account_headers: dict,
    ):
        """Returns 404 for non-existent community server."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/community-servers/nonexistent_platform_id/flashpoint-detection",
                headers=fp_service_account_headers,
                json={"enabled": True},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_flashpoint_detection_unauthenticated(
        self,
        fp_test_community_server: CommunityServer,
    ):
        """Returns 401 for unauthenticated requests."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                json={"enabled": True},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_flashpoint_detection_regular_user_forbidden(
        self,
        fp_regular_user_headers: dict,
        fp_test_community_server: CommunityServer,
    ):
        """Regular (non-service-account) user gets 403."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                headers=fp_regular_user_headers,
                json={"enabled": True},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_flashpoint_detection_response_contains_id(
        self,
        fp_service_account_headers: dict,
        fp_test_community_server: CommunityServer,
    ):
        """Response includes the community server UUID."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                headers=fp_service_account_headers,
                json={"enabled": True},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(fp_test_community_server.id)

    @pytest.mark.asyncio
    async def test_flashpoint_detection_invalid_request_body(
        self,
        fp_service_account_headers: dict,
        fp_test_community_server: CommunityServer,
    ):
        """Returns 422 for invalid request body (missing required 'enabled' field)."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{fp_test_community_server.platform_community_server_id}/flashpoint-detection",
                headers=fp_service_account_headers,
                json={"invalid_field": "not_a_bool"},
            )

        assert response.status_code == 422
