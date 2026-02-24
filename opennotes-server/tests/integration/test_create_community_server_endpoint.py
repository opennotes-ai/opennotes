"""Tests for POST /api/v1/community-servers endpoint."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.llm_config.models import CommunityServer
from src.users.models import User

ENDPOINT = "/api/v1/community-servers"


@pytest.fixture
async def create_service_account():
    from src.database import get_session_maker

    async with get_session_maker()() as db:
        user = User(
            email="create-cs-service@opennotes.local",
            username="create-cs-service",
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
async def create_service_account_headers(create_service_account: User):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(create_service_account.id),
        "username": create_service_account.username,
        "role": create_service_account.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def create_superuser():
    from src.database import get_session_maker

    async with get_session_maker()() as db:
        user = User(
            email="create-cs-superuser@opennotes.local",
            username="create-cs-superuser",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
            is_superuser=True,
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
async def create_superuser_headers(create_superuser: User):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(create_superuser.id),
        "username": create_superuser.username,
        "role": create_superuser.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def create_regular_user():
    from src.database import get_session_maker

    async with get_session_maker()() as db:
        user = User(
            email="create-cs-regular@opennotes.local",
            username="create-cs-regular",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
            is_service_account=False,
            is_superuser=False,
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
async def create_regular_user_headers(create_regular_user: User):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(create_regular_user.id),
        "username": create_regular_user.username,
        "role": create_regular_user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def cleanup_servers():
    created_ids: list = []

    yield created_ids

    from src.database import get_session_maker

    async with get_session_maker()() as db:
        for server_id in created_ids:
            await db.execute(delete(CommunityServer).where(CommunityServer.id == server_id))
        await db.commit()


def _make_payload(**overrides):
    base = {
        "platform": "playground",
        "platform_community_server_id": f"pg-{uuid4().hex[:8]}",
        "name": f"Test Server {uuid4().hex[:8]}",
    }
    base.update(overrides)
    return base


class TestCreateCommunityServerEndpoint:
    @pytest.mark.asyncio
    async def test_create_with_service_account(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        data = response.json()
        if "id" in data:
            cleanup_servers.append(data["id"])
        assert response.status_code == 201
        assert data["platform"] == payload["platform"]
        assert data["platform_community_server_id"] == payload["platform_community_server_id"]
        assert data["name"] == payload["name"]
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_with_superuser(
        self,
        create_superuser_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_superuser_headers,
                json=payload,
            )

        data = response.json()
        if "id" in data:
            cleanup_servers.append(data["id"])
        assert response.status_code == 201
        assert data["platform"] == payload["platform"]

    @pytest.mark.asyncio
    async def test_create_discord_platform(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload(platform="discord", platform_community_server_id="123456789")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        data = response.json()
        if "id" in data:
            cleanup_servers.append(data["id"])
        assert response.status_code == 201
        assert data["platform"] == "discord"

    @pytest.mark.asyncio
    async def test_create_with_optional_fields(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload(
            description="A test playground",
            settings={"max_notes": 100, "theme": "dark"},
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        data = response.json()
        if "id" in data:
            cleanup_servers.append(data["id"])
        assert response.status_code == 201
        assert data["description"] == "A test playground"
        assert data["settings"] == {"max_notes": 100, "theme": "dark"}

    @pytest.mark.asyncio
    async def test_create_with_defaults(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        data = response.json()
        if "id" in data:
            cleanup_servers.append(data["id"])
        assert response.status_code == 201
        assert data["is_active"] is True
        assert data["is_public"] is True
        assert data["flashpoint_detection_enabled"] is True

    @pytest.mark.asyncio
    async def test_create_with_non_default_booleans(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload(is_active=False, is_public=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        data = response.json()
        if "id" in data:
            cleanup_servers.append(data["id"])
        assert response.status_code == 201
        assert data["is_active"] is False
        assert data["is_public"] is False

    @pytest.mark.asyncio
    async def test_duplicate_conflict(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        payload = _make_payload()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        first_data = first.json()
        if "id" in first_data:
            cleanup_servers.append(first_data["id"])
        assert first.status_code == 201

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            second = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert second.status_code == 409
        second_data = second.json()
        assert "already exists" in second_data["detail"]
        assert payload["platform"] in second_data["detail"]

    @pytest.mark.asyncio
    async def test_same_slug_different_platform(
        self,
        create_service_account_headers: dict,
        cleanup_servers: list,
    ):
        from src.main import app

        shared_id = f"shared-{uuid4().hex[:8]}"
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=_make_payload(
                    platform="playground",
                    platform_community_server_id=shared_id,
                ),
            )

        data1 = resp1.json()
        if "id" in data1:
            cleanup_servers.append(data1["id"])
        assert resp1.status_code == 201

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp2 = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=_make_payload(
                    platform="discord",
                    platform_community_server_id=shared_id,
                ),
            )

        data2 = resp2.json()
        if "id" in data2:
            cleanup_servers.append(data2["id"])
        assert resp2.status_code == 201

    @pytest.mark.asyncio
    async def test_regular_user_forbidden(
        self,
        create_regular_user_headers: dict,
    ):
        from src.main import app

        payload = _make_payload()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_regular_user_headers,
                json=payload,
            )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "admin" in data["detail"].lower() or "privilege" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_unauthenticated(self):
        from src.main import app

        payload = _make_payload()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json=payload,
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_platform(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(platform="invalid")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_empty_name(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(name="")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_missing_required_fields(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json={},
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_extra_unknown_fields(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(bogus_field="should_be_rejected")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_empty_platform_community_server_id(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(platform_community_server_id="")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_overlength_platform_community_server_id(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(platform_community_server_id="x" * 256)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_overlength_name(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(name="x" * 256)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_overlength_description(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(description="x" * 10001)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_oversized_settings(
        self,
        create_service_account_headers: dict,
    ):
        from src.main import app

        payload = _make_payload(settings={"data": "x" * 70000})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                headers=create_service_account_headers,
                json=payload,
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
