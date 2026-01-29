from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_webhook_registration() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/123/token",
            "secret": "test_secret",
            "platform_community_server_id": "guild_123",
            "channel_id": "channel_456",
        }

        response = await client.post(
            "/api/v1/webhooks/register",
            json=webhook_data,
        )

        assert response.status_code == 200
        data = response.json()
        # community_server_id in response is a UUID (internal ID), not the platform string
        UUID(data["community_server_id"])  # Validates it's a valid UUID
        assert data["active"] is True


@pytest.mark.asyncio
async def test_get_webhooks_by_guild() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/123/token",
            "secret": "test_secret",
            "platform_community_server_id": "guild_456",
            "channel_id": "channel_789",
        }

        await client.post("/api/v1/webhooks/register", json=webhook_data)

        response = await client.get("/api/v1/webhooks/guild_456")

        assert response.status_code == 200
        webhooks = response.json()
        assert len(webhooks) >= 1
        # community_server_id in response is a UUID (internal ID), not the platform string
        UUID(webhooks[0]["community_server_id"])  # Validates it's a valid UUID
