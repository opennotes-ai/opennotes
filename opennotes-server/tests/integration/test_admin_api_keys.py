import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.auth.password import get_password_hash
from src.database import get_session_maker
from src.main import app
from src.users.models import APIKey, User


async def _create_service_account_with_api_key(scopes: list[str]) -> tuple[User, str]:
    raw_key, key_prefix = APIKey.generate_key()
    key_hash = get_password_hash(raw_key)

    async with get_session_maker()() as session:
        user = User(
            username="admin-service-account",
            email="admin-svc@opennotes.local",
            hashed_password=get_password_hash("unused"),
            is_active=True,
            is_service_account=True,
            role="user",
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)

        api_key = APIKey(
            user_id=user.id,
            name="Admin API Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_active=True,
            scopes=scopes,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(user)

    return user, raw_key


async def _create_regular_user_with_api_key(scopes: list[str]) -> tuple[User, str]:
    raw_key, key_prefix = APIKey.generate_key()
    key_hash = get_password_hash(raw_key)

    async with get_session_maker()() as session:
        user = User(
            username="regular-user",
            email="regular@example.com",
            hashed_password=get_password_hash("unused"),
            is_active=True,
            is_service_account=False,
            role="user",
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)

        api_key = APIKey(
            user_id=user.id,
            name="Regular API Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_active=True,
            scopes=scopes,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(user)

    return user, raw_key


@pytest.mark.asyncio
class TestAdminAPIKeyCreate:
    async def test_post_creates_user_and_key(self):
        _, admin_key = await _create_service_account_with_api_key(["api-keys:create"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "newuser@example.com",
                    "user_display_name": "New User",
                    "key_name": "My Integration Key",
                    "scopes": ["notes:read", "notes:write"],
                },
                headers={"X-API-Key": admin_key},
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["user_email"] == "newuser@example.com"
        assert data["user_display_name"] == "New User"
        assert data["name"] == "My Integration Key"
        assert data["scopes"] == ["notes:read", "notes:write"]
        assert data["key"].startswith("opk_")
        assert "id" in data

    async def test_post_reuses_existing_user_by_email(self):
        _, admin_key = await _create_service_account_with_api_key(["api-keys:create"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "existing@example.com",
                    "user_display_name": "Existing User",
                    "key_name": "Key 1",
                    "scopes": ["notes:read"],
                },
                headers={"X-API-Key": admin_key},
            )
            assert resp1.status_code == status.HTTP_201_CREATED

            resp2 = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "existing@example.com",
                    "user_display_name": "Existing User",
                    "key_name": "Key 2",
                    "scopes": ["notes:write"],
                },
                headers={"X-API-Key": admin_key},
            )
            assert resp2.status_code == status.HTTP_201_CREATED

        from sqlalchemy import func, select

        async with get_session_maker()() as session:
            count = await session.scalar(
                select(func.count()).select_from(User).where(User.email == "existing@example.com")
            )
            assert count == 1

    async def test_post_strips_restricted_scopes_from_issued_key(self):
        _, admin_key = await _create_service_account_with_api_key(["api-keys:create"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "stripped@example.com",
                    "user_display_name": "Stripped Scopes User",
                    "key_name": "Should Strip Restricted",
                    "scopes": ["notes:read", "api-keys:create"],
                },
                headers={"X-API-Key": admin_key},
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "api-keys:create" not in data["scopes"]
        assert "notes:read" in data["scopes"]


@pytest.mark.asyncio
class TestAdminAPIKeyList:
    async def test_get_returns_list_with_user_info(self):
        _, admin_key = await _create_service_account_with_api_key(["api-keys:create"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "listed@example.com",
                    "user_display_name": "Listed User",
                    "key_name": "Listed Key",
                    "scopes": ["notes:read"],
                },
                headers={"X-API-Key": admin_key},
            )

            response = await client.get(
                "/api/v2/admin/api-keys",
                headers={"X-API-Key": admin_key},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        listed_items = [item for item in data if item["user_email"] == "listed@example.com"]
        assert len(listed_items) == 1
        item = listed_items[0]
        assert item["user_display_name"] == "Listed User"
        assert item["name"] == "Listed Key"
        assert item["is_active"] is True
        assert "key" not in item
        assert item.get("key_prefix") is not None


@pytest.mark.asyncio
class TestAdminAPIKeyDelete:
    async def test_delete_revokes_key(self):
        _, admin_key = await _create_service_account_with_api_key(["api-keys:create"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "revoked@example.com",
                    "user_display_name": "Revoked User",
                    "key_name": "To Be Revoked",
                    "scopes": ["notes:read"],
                },
                headers={"X-API-Key": admin_key},
            )
            assert create_resp.status_code == status.HTTP_201_CREATED
            key_id = create_resp.json()["id"]

            delete_resp = await client.delete(
                f"/api/v2/admin/api-keys/{key_id}",
                headers={"X-API-Key": admin_key},
            )
            assert delete_resp.status_code == status.HTTP_204_NO_CONTENT

        from sqlalchemy import select

        async with get_session_maker()() as session:
            result = await session.execute(select(APIKey).where(APIKey.id == key_id))
            api_key = result.scalar_one()
            assert api_key.is_active is False


@pytest.mark.asyncio
class TestAdminAPIKeyAuth:
    async def test_403_without_api_keys_create_scope(self):
        _, regular_key = await _create_regular_user_with_api_key(["notes:read"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "nope@example.com",
                    "user_display_name": "Nope",
                    "key_name": "Should Fail",
                    "scopes": ["notes:read"],
                },
                headers={"X-API-Key": regular_key},
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_401_without_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "nope@example.com",
                    "user_display_name": "Nope",
                    "key_name": "Should Fail",
                    "scopes": ["notes:read"],
                },
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
