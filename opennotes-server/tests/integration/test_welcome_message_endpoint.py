"""
Tests for welcome message ID endpoint.

TDD: RED phase - these tests should fail until the endpoint is implemented.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.llm_config.models import CommunityServer
from src.users.models import User


@pytest.fixture
async def service_account() -> User:
    """Create a test service account."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="welcome-test-service@opennotes.local",
            username="welcome-test-service",
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
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def welcome_test_community_server() -> CommunityServer:
    """Create a test community server for welcome message tests."""
    from uuid import uuid4

    from src.database import get_session_maker

    unique_suffix = uuid4().hex[:8]
    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        server = CommunityServer(
            platform="discord",
            platform_community_server_id=f"welcome_test_{unique_suffix}",
            name=f"Welcome Test Server {unique_suffix}",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


class TestWelcomeMessageEndpoint:
    """Tests for PATCH /api/v1/community-servers/{platform_id}/welcome-message endpoint."""

    @pytest.mark.asyncio
    async def test_update_welcome_message_id_success(
        self,
        service_account_headers: dict,
        welcome_test_community_server: CommunityServer,
    ):
        """Service account can update welcome_message_id for a community server."""
        from src.main import app

        message_id = "1234567890123456789"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{welcome_test_community_server.platform_community_server_id}/welcome-message",
                headers=service_account_headers,
                json={"welcome_message_id": message_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["welcome_message_id"] == message_id

    @pytest.mark.asyncio
    async def test_update_welcome_message_id_persisted(
        self,
        service_account_headers: dict,
        welcome_test_community_server: CommunityServer,
    ):
        """welcome_message_id is persisted in the database."""
        from src.database import get_session_maker
        from src.main import app

        message_id = "9876543210987654321"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{welcome_test_community_server.platform_community_server_id}/welcome-message",
                headers=service_account_headers,
                json={"welcome_message_id": message_id},
            )

        assert response.status_code == 200

        async_session_maker = get_session_maker()
        async with async_session_maker() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(CommunityServer).where(
                    CommunityServer.id == welcome_test_community_server.id
                )
            )
            server = result.scalar_one()
            assert server.welcome_message_id == message_id

    @pytest.mark.asyncio
    async def test_clear_welcome_message_id(
        self,
        service_account_headers: dict,
        welcome_test_community_server: CommunityServer,
    ):
        """welcome_message_id can be cleared by setting to null."""
        from src.database import get_session_maker
        from src.main import app

        async_session_maker = get_session_maker()
        async with async_session_maker() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(CommunityServer).where(
                    CommunityServer.id == welcome_test_community_server.id
                )
            )
            server = result.scalar_one()
            server.welcome_message_id = "existing_message_id"
            await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{welcome_test_community_server.platform_community_server_id}/welcome-message",
                headers=service_account_headers,
                json={"welcome_message_id": None},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["welcome_message_id"] is None

    @pytest.mark.asyncio
    async def test_update_welcome_message_id_not_found(
        self,
        service_account_headers: dict,
    ):
        """Returns 404 for non-existent community server."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/community-servers/nonexistent_platform_id/welcome-message",
                headers=service_account_headers,
                json={"welcome_message_id": "1234567890123456789"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_welcome_message_id_unauthorized(
        self,
        welcome_test_community_server: CommunityServer,
    ):
        """Returns 401 for unauthenticated requests."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{welcome_test_community_server.platform_community_server_id}/welcome-message",
                json={"welcome_message_id": "1234567890123456789"},
            )

        assert response.status_code == 401
