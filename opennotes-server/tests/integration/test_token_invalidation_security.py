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
