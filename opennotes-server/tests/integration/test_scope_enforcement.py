from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.main import app


class TestRestrictedScopeEnforcement:
    async def test_regular_user_cannot_create_key_with_restricted_scope(
        self, test_user_data, registered_user
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Restricted Key", "scopes": ["api-keys:create"]},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "restricted" in response.json()["detail"].lower()

    async def test_regular_user_can_create_key_with_unrestricted_scope(
        self, test_user_data, registered_user
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Normal Key", "scopes": ["notes:read"]},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["scopes"] == ["notes:read"]

    async def test_service_account_can_create_key_with_restricted_scope(
        self, test_user_data, registered_user
    ):
        from sqlalchemy import select

        from src.auth.auth import create_access_token
        from src.database import get_session_maker
        from src.users.models import User

        async with get_session_maker()() as session:
            result = await session.execute(
                select(User).where(User.username == test_user_data["username"])
            )
            user = result.scalar_one()
            user.principal_type = "agent"
            await session.commit()
            user_id = str(user.id)

        token = create_access_token(
            {
                "sub": user_id,
                "username": test_user_data["username"],
            }
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Service Key", "scopes": ["api-keys:create"]},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["scopes"] == ["api-keys:create"]

    async def test_regular_user_cannot_create_unrestricted_key(
        self, test_user_data, registered_user
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Unrestricted Key", "scopes": None},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "explicit scopes" in response.json()["detail"].lower()
