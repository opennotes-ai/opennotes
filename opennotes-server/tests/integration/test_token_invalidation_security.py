import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


class TestGetCurrentUserOrApiKeyTokensValidAfter:
    @pytest.mark.asyncio
    async def test_revoked_token_rejected_on_flexible_auth_endpoint(
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
            assert login_response.status_code == 200
            old_token = login_response.json()["access_token"]

            notes_response = await client.get(
                "/api/v2/notes?page[number]=1&page[size]=10",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert notes_response.status_code == 200

            revoke_response = await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert revoke_response.status_code == 204

            await asyncio.sleep(1.1)

            notes_response_after = await client.get(
                "/api/v2/notes?page[number]=1&page[size]=10",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert notes_response_after.status_code == 401


class TestRefreshTokenAfterPasswordChange:
    @pytest.mark.asyncio
    async def test_old_refresh_token_rejected_after_password_change(
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
            assert login_response.status_code == 200
            old_access_token = login_response.json()["access_token"]
            old_refresh_token = login_response.json()["refresh_token"]

            refresh_before = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": old_refresh_token},
            )
            assert refresh_before.status_code == 200

            update_response = await client.patch(
                "/api/v1/users/me",
                json={"password": "NewSecure@Pass123!"},
                headers={"Authorization": f"Bearer {old_access_token}"},
            )
            assert update_response.status_code == 200

            await asyncio.sleep(1.1)

            refresh_after = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": old_refresh_token},
            )
            assert refresh_after.status_code == 401

            new_login = await client.post(
                "/api/v1/auth/login",
                data={"username": test_user_data["username"], "password": "NewSecure@Pass123!"},
            )
            assert new_login.status_code == 200
            new_refresh = new_login.json()["refresh_token"]

            new_refresh_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": new_refresh},
            )
            assert new_refresh_response.status_code == 200


class TestCrossPathTokenInvalidation:
    @pytest.mark.asyncio
    async def test_password_change_invalidates_across_all_paths(
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
            old_token = login_response.json()["access_token"]
            old_refresh = login_response.json()["refresh_token"]

            await client.patch(
                "/api/v1/users/me",
                json={"password": "NewSecure@Pass123!"},
                headers={"Authorization": f"Bearer {old_token}"},
            )
            await asyncio.sleep(1.1)

            assert (
                await client.get(
                    "/api/v1/users/me",
                    headers={"Authorization": f"Bearer {old_token}"},
                )
            ).status_code == 401

            assert (
                await client.get(
                    "/api/v2/notes?page[number]=1&page[size]=10",
                    headers={"Authorization": f"Bearer {old_token}"},
                )
            ).status_code == 401

            assert (
                await client.post(
                    "/api/v1/auth/refresh",
                    json={"refresh_token": old_refresh},
                )
            ).status_code == 401

            new_login = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": "NewSecure@Pass123!",
                },
            )
            assert new_login.status_code == 200
            new_token = new_login.json()["access_token"]

            assert (
                await client.get(
                    "/api/v1/users/me",
                    headers={"Authorization": f"Bearer {new_token}"},
                )
            ).status_code == 200
            assert (
                await client.get(
                    "/api/v2/notes?page[number]=1&page[size]=10",
                    headers={"Authorization": f"Bearer {new_token}"},
                )
            ).status_code == 200


class TestLogoutAllInvalidation:
    @pytest.mark.asyncio
    async def test_logout_all_invalidates_across_both_auth_deps(
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
            old_token = login_response.json()["access_token"]

            await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            await asyncio.sleep(1.1)

            assert (
                await client.get(
                    "/api/v1/users/me",
                    headers={"Authorization": f"Bearer {old_token}"},
                )
            ).status_code == 401

            assert (
                await client.get(
                    "/api/v2/notes?page[number]=1&page[size]=10",
                    headers={"Authorization": f"Bearer {old_token}"},
                )
            ).status_code == 401

            new_login = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            new_token = new_login.json()["access_token"]

            assert (
                await client.get(
                    "/api/v1/users/me",
                    headers={"Authorization": f"Bearer {new_token}"},
                )
            ).status_code == 200
            assert (
                await client.get(
                    "/api/v2/notes?page[number]=1&page[size]=10",
                    headers={"Authorization": f"Bearer {new_token}"},
                )
            ).status_code == 200
