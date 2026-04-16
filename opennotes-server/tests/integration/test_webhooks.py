from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import get_current_user_or_api_key
from src.main import app


@pytest.fixture(autouse=True)
def override_auth():
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.username = "webhook_test_user"
    mock_user.platform_roles = ["platform_admin"]
    mock_user.is_active = True
    app.dependency_overrides[get_current_user_or_api_key] = lambda: mock_user
    yield
    app.dependency_overrides.pop(get_current_user_or_api_key, None)


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

        response = await client.get("/api/v1/webhooks/by-community/guild_456")

        assert response.status_code == 200
        webhooks = response.json()
        assert len(webhooks) >= 1
        # community_server_id in response is a UUID (internal ID), not the platform string
        UUID(webhooks[0]["community_server_id"])  # Validates it's a valid UUID


@pytest.mark.asyncio
async def test_put_register_does_not_succeed() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/webhooks/register",
            json={"url": "https://example.com"},
        )
        assert response.status_code in (405, 422)


@pytest.mark.asyncio
async def test_get_webhook_by_uuid_does_not_return_data() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_uuid = str(uuid4())
        response = await client.get(f"/api/v1/webhooks/{fake_uuid}")
        assert response.status_code in (404, 405, 422)


@pytest.mark.asyncio
async def test_get_by_community_returns_expected_result() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        platform_id = "guild_routing_test"
        webhook_data = {
            "url": "https://discord.com/api/webhooks/routing/token",
            "secret": "routing_test_secret",
            "platform_community_server_id": platform_id,
            "channel_id": "channel_routing",
        }
        await client.post("/api/v1/webhooks/register", json=webhook_data)

        response = await client.get(f"/api/v1/webhooks/by-community/{platform_id}")
        assert response.status_code == 200
        webhooks = response.json()
        assert isinstance(webhooks, list)
        assert len(webhooks) >= 1
        assert all("url" in w for w in webhooks)
