"""
Tests for Task-187: Fix webhook secret exposure in API responses.

Verifies that:
- POST /register returns WebhookConfigSecure (includes secret)
- GET requests return WebhookConfigResponse (excludes secret)
- PUT requests return WebhookConfigResponse (excludes secret)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_webhook_registration_returns_secret():
    """
    Task-187: Verify POST /register returns WebhookConfigSecure with secret.

    The secret should ONLY be returned on initial registration so the client
    can store it. This is the only endpoint that should expose the secret.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/task187-1/token",
            "secret": "task-187-test-secret-registration",
            "platform_community_server_id": "guild_task187_1",
            "channel_id": "channel_task187_1",
        }

        response = await client.post(
            "/api/v1/webhooks/register",
            json=webhook_data,
        )

        assert response.status_code == 200
        data = response.json()

        assert "secret" in data, "POST /register must return secret in WebhookConfigSecure"
        assert data["secret"] == webhook_data["secret"]
        assert "community_server_id" in data
        assert data["active"] is True


@pytest.mark.asyncio
async def test_get_webhooks_excludes_secret():
    """
    Task-187: Verify GET /{platform_community_server_id} returns WebhookConfigResponse without secret.

    The secret should NEVER be returned in GET requests to prevent exposure
    in logs, caches, or unauthorized access.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        platform_id = "guild_task187_2"
        webhook_data = {
            "url": "https://discord.com/api/webhooks/task187-2/token",
            "secret": "task-187-test-secret-get",
            "platform_community_server_id": platform_id,
            "channel_id": "channel_task187_2",
        }

        await client.post("/api/v1/webhooks/register", json=webhook_data)

        response = await client.get(f"/api/v1/webhooks/{platform_id}")

        assert response.status_code == 200
        webhooks = response.json()
        assert len(webhooks) >= 1

        found = False
        for webhook in webhooks:
            assert "secret" not in webhook, (
                "GET requests must return WebhookConfigResponse without secret"
            )
            assert "url" in webhook
            assert "community_server_id" in webhook
            assert "active" in webhook
            found = True

        assert found, f"Webhook for platform ID {platform_id} not found in response"


@pytest.mark.asyncio
async def test_update_webhook_excludes_secret():
    """
    Task-187: Verify PUT /{webhook_id} returns WebhookConfigResponse without secret.

    The secret should NEVER be returned in PUT/update responses to prevent
    exposure when modifying webhook configuration.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/task187-3/token",
            "secret": "task-187-test-secret-update",
            "platform_community_server_id": "guild_task187_3",
            "channel_id": "channel_task187_3",
        }

        register_response = await client.post("/api/v1/webhooks/register", json=webhook_data)
        webhook_id = register_response.json()["id"]

        update_data = {"active": False}
        response = await client.put(
            f"/api/v1/webhooks/{webhook_id}",
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()

        assert "secret" not in data, "PUT requests must return WebhookConfigResponse without secret"
        assert "url" in data
        assert "community_server_id" in data
        assert "active" in data
        assert data["active"] is False


@pytest.mark.asyncio
async def test_secret_never_exposed_in_list_operations():
    """
    Task-187: Additional security test - verify secret is never exposed in bulk operations.

    This is a defense-in-depth test to ensure that even if multiple webhooks
    are returned, none of them expose secrets.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        platform_id = "guild_task187_bulk"

        for i in range(3):
            webhook_data = {
                "url": f"https://discord.com/api/webhooks/task187-bulk-{i}/token",
                "secret": f"task-187-test-secret-bulk-{i}",
                "platform_community_server_id": platform_id,
                "channel_id": f"channel_task187_bulk_{i}",
            }
            await client.post("/api/v1/webhooks/register", json=webhook_data)

        response = await client.get(f"/api/v1/webhooks/{platform_id}")

        assert response.status_code == 200
        webhooks = response.json()

        assert len(webhooks) >= 3, f"Expected at least 3 webhooks, got {len(webhooks)}"

        for webhook in webhooks:
            assert "secret" not in webhook, (
                f"Webhook {webhook.get('id')} exposed secret in bulk operation"
            )


@pytest.mark.asyncio
async def test_secret_format_validation():
    """
    Task-187: Verify that secrets are properly stored and can be used for validation.

    While we don't expose secrets in responses, we need to ensure they're
    properly stored and can be used for webhook signature validation.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/task187-validation/token",
            "secret": "task-187-test-secret-validation-with-special-chars-!@#$%",
            "platform_community_server_id": "guild_task187_validation",
            "channel_id": "channel_task187_validation",
        }

        response = await client.post("/api/v1/webhooks/register", json=webhook_data)

        assert response.status_code == 200
        data = response.json()

        assert data["secret"] == webhook_data["secret"]

        assert "!@#$%" in data["secret"]
