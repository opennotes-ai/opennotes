"""Tests for PATCH /community-servers/{id}/name endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.llm_config.models import CommunityServer
from src.users.models import User


@pytest.fixture
async def name_service_account():
    from src.database import get_session_maker

    async with get_session_maker()() as db:
        user = User(
            email="name-test-service@opennotes.local",
            username="name-test-service",
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
async def name_service_account_headers(name_service_account: User):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(name_service_account.id),
        "username": name_service_account.username,
        "role": name_service_account.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def name_regular_user():
    from src.database import get_session_maker

    async with get_session_maker()() as db:
        user = User(
            email="name-regular@opennotes.local",
            username="name-regular-user",
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
async def name_regular_user_headers(name_regular_user: User):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(name_regular_user.id),
        "username": name_regular_user.username,
        "role": name_regular_user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def name_test_community_server():
    from uuid import uuid4

    from src.database import get_session_maker

    unique_suffix = uuid4().hex[:8]
    async with get_session_maker()() as db:
        server = CommunityServer(
            platform="discord",
            platform_community_server_id=f"name_test_{unique_suffix}",
            name=f"Original Name {unique_suffix}",
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


class TestCommunityServerNameEndpoint:
    """Tests for PATCH /api/v1/community-servers/{platform_id}/name."""

    @pytest.mark.asyncio
    async def test_update_name_success(
        self,
        name_service_account_headers: dict,
        name_test_community_server: CommunityServer,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                headers=name_service_account_headers,
                json={"name": "New Server Name"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Server Name"
        assert (
            data["platform_community_server_id"]
            == name_test_community_server.platform_community_server_id
        )

    @pytest.mark.asyncio
    async def test_update_name_persisted(
        self,
        name_service_account_headers: dict,
        name_test_community_server: CommunityServer,
    ):
        from src.database import get_session_maker
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                headers=name_service_account_headers,
                json={"name": "Persisted Name"},
            )

        assert response.status_code == 200

        async with get_session_maker()() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(CommunityServer).where(CommunityServer.id == name_test_community_server.id)
            )
            server = result.scalar_one()
            assert server.name == "Persisted Name"

    @pytest.mark.asyncio
    async def test_update_name_not_found(
        self,
        name_service_account_headers: dict,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/community-servers/nonexistent_platform_id/name",
                headers=name_service_account_headers,
                json={"name": "Does Not Matter"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_name_unauthenticated(
        self,
        name_test_community_server: CommunityServer,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                json={"name": "Unauthorized"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_name_regular_user_forbidden(
        self,
        name_regular_user_headers: dict,
        name_test_community_server: CommunityServer,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                headers=name_regular_user_headers,
                json={"name": "Forbidden"},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_name_response_contains_id(
        self,
        name_service_account_headers: dict,
        name_test_community_server: CommunityServer,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                headers=name_service_account_headers,
                json={"name": "Check ID"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(name_test_community_server.id)

    @pytest.mark.asyncio
    async def test_update_name_empty_string_rejected(
        self,
        name_service_account_headers: dict,
        name_test_community_server: CommunityServer,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                headers=name_service_account_headers,
                json={"name": ""},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_name_missing_name_field(
        self,
        name_service_account_headers: dict,
        name_test_community_server: CommunityServer,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/community-servers/{name_test_community_server.platform_community_server_id}/name",
                headers=name_service_account_headers,
                json={"invalid_field": "not_a_name"},
            )

        assert response.status_code == 422
