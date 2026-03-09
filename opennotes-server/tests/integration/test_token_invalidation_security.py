import asyncio
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from src.config import settings
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

            patch_response = await client.patch(
                "/api/v1/users/me",
                json={"password": "NewSecure@Pass123!"},
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert patch_response.status_code == 200
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


class TestTokenWithoutIatRejectedAfterRevocation:
    @pytest.mark.asyncio
    async def test_crafted_token_without_iat_rejected_after_revoke_all(
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
            access_token = login_response.json()["access_token"]

            legitimate_payload = jwt.decode(
                access_token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            user_id = legitimate_payload["sub"]

            revoke_response = await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert revoke_response.status_code == 204

            await asyncio.sleep(1.1)

            payload_no_iat = {
                "sub": user_id,
                "username": test_user_data["username"],
                "role": "user",
                "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
                "jti": secrets.token_urlsafe(32),
            }
            crafted_token = jwt.encode(
                payload_no_iat, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
            )

            me_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {crafted_token}"},
            )
            assert me_response.status_code == 401, (
                f"Token without iat should be rejected when tokens_valid_after is set, "
                f"got {me_response.status_code}"
            )

            notes_response = await client.get(
                "/api/v2/notes?page[number]=1&page[size]=10",
                headers={"Authorization": f"Bearer {crafted_token}"},
            )
            assert notes_response.status_code == 401, (
                f"Token without iat should be rejected on flexible auth endpoint, "
                f"got {notes_response.status_code}"
            )


class TestProfileLegacyTokenInvalidation:
    @pytest.mark.asyncio
    async def test_revoked_legacy_token_rejected_on_profile_endpoint(
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

            revoke_response = await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert revoke_response.status_code == 204

            await asyncio.sleep(1.1)

            profile_response = await client.get(
                "/api/v1/profile/me",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert profile_response.status_code == 401, (
                f"Legacy token should be rejected on profile endpoint after revoke-all, "
                f"got {profile_response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_crafted_legacy_token_without_iat_rejected_on_profile_endpoint(
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
            access_token = login_response.json()["access_token"]

            legitimate_payload = jwt.decode(
                access_token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            user_id = legitimate_payload["sub"]

            revoke_response = await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert revoke_response.status_code == 204

            await asyncio.sleep(1.1)

            payload_no_iat = {
                "sub": user_id,
                "username": test_user_data["username"],
                "role": "user",
                "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
                "jti": secrets.token_urlsafe(32),
            }
            crafted_token = jwt.encode(
                payload_no_iat, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
            )

            profile_response = await client.get(
                "/api/v1/profile/me",
                headers={"Authorization": f"Bearer {crafted_token}"},
            )
            assert profile_response.status_code == 401, (
                f"Legacy token without iat should be rejected on profile endpoint "
                f"when tokens_valid_after is set, got {profile_response.status_code}"
            )


class TestLogoutAllEndpointInvalidation:
    @pytest.mark.asyncio
    async def test_logout_all_endpoint_invalidates_tokens(self, test_user_data, registered_user):
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

            logout_all_response = await client.post(
                "/api/v1/auth/logout-all",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert logout_all_response.status_code == 204

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


class TestSingleLogoutEndpoint:
    @pytest.mark.asyncio
    async def test_single_logout_revokes_refresh_token(self, test_user_data, registered_user):
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
            access_token = login_response.json()["access_token"]
            refresh_token = login_response.json()["refresh_token"]

            refresh_before = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
            assert refresh_before.status_code == 200

            logout_response = await client.post(
                "/api/v1/auth/logout",
                params={"refresh_token": refresh_token},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert logout_response.status_code == 204

            refresh_after = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
            assert refresh_after.status_code == 401
