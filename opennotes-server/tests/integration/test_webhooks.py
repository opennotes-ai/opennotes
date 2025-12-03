import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app
from src.webhooks.types import InteractionType


@pytest.fixture
def test_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def test_public_key(test_private_key: Ed25519PrivateKey) -> str:
    public_key = test_private_key.public_key()
    return public_key.public_bytes_raw().hex()


def create_signature(
    private_key: Ed25519PrivateKey,
    body: bytes,
    timestamp: str,
) -> str:
    message = timestamp.encode() + body
    signature = private_key.sign(message)
    return signature.hex()


@pytest.mark.asyncio
async def test_ping_interaction(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DISCORD_PUBLIC_KEY", test_public_key)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interaction = {
            "id": "test_interaction_1",
            "application_id": "test_app",
            "type": InteractionType.PING,
            "token": "test_token",
            "version": 1,
        }

        body = json.dumps(interaction).encode()
        timestamp = str(int(time.time()))
        signature = create_signature(test_private_key, body, timestamp)

        response = await client.post(
            "/api/v1/webhooks/discord/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": signature,
                "X-Signature-Timestamp": timestamp,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"type": 1}


@pytest.mark.asyncio
async def test_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DISCORD_PUBLIC_KEY", "0" * 64)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interaction = {
            "id": "test_interaction_2",
            "application_id": "test_app",
            "type": InteractionType.PING,
            "token": "test_token",
            "version": 1,
        }

        body = json.dumps(interaction).encode()

        response = await client.post(
            "/api/v1/webhooks/discord/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": "invalid_signature",
                "X-Signature-Timestamp": str(int(time.time())),
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_application_command_deferred(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DISCORD_PUBLIC_KEY", test_public_key)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interaction = {
            "id": "test_interaction_3",
            "application_id": "test_app",
            "type": InteractionType.APPLICATION_COMMAND,
            "data": {
                "id": "cmd_1",
                "name": "test_command",
                "type": 1,
            },
            "community_server_id": "guild_123",
            "channel_id": "channel_456",
            "user": {
                "id": "user_789",
                "username": "testuser",
                "discriminator": "0001",
            },
            "token": "test_token",
            "version": 1,
        }

        body = json.dumps(interaction).encode()
        timestamp = str(int(time.time()))
        signature = create_signature(test_private_key, body, timestamp)

        response = await client.post(
            "/api/v1/webhooks/discord/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": signature,
                "X-Signature-Timestamp": timestamp,
                "Content-Type": "application/json",
            },
        )

        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response text: {response.text}")
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["type"] == 5


@pytest.mark.asyncio
async def test_webhook_registration() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/123/token",
            "secret": "test_secret",
            "community_server_id": "guild_123",
            "channel_id": "channel_456",
        }

        response = await client.post(
            "/api/v1/webhooks/register",
            json=webhook_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["community_server_id"] == "guild_123"
        assert data["active"] is True


@pytest.mark.asyncio
async def test_get_webhooks_by_guild() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_data = {
            "url": "https://discord.com/api/webhooks/123/token",
            "secret": "test_secret",
            "community_server_id": "guild_456",
            "channel_id": "channel_789",
        }

        await client.post("/api/v1/webhooks/register", json=webhook_data)

        response = await client.get("/api/v1/webhooks/guild_456")

        assert response.status_code == 200
        webhooks = response.json()
        assert len(webhooks) >= 1
        assert webhooks[0]["community_server_id"] == "guild_456"


@pytest.mark.asyncio
async def test_webhook_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/webhooks/health/webhooks")

        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
