"""Test to reproduce the request creation bug with large tweet IDs."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_create_request_with_large_tweet_id(db_session, registered_user, auth_headers):
    """Test that creating a request with a large platform_message_id returns string in response."""
    from uuid import uuid4

    from src.database import async_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    async with async_session_maker() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id="test_guild_large_tweet",
            name="Test Guild for Large Tweet ID",
        )
        db.add(community_server)
        await db.commit()

    request_payload = {
        "request_id": "test-discord-123456789",
        "original_message_content": "I heard that hitler invented the inflatable sex doll",
        "requested_by": "system-factcheck",
        "platform_message_id": "1436038555091865653",
        "platform_channel_id": "1423068966670176410",
        "platform_author_id": "696877497287049258",
        "platform_timestamp": "2025-11-06T17:04:31.840Z",
        "community_server_id": str(community_server_id),
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        jsonapi_payload = {
            "data": {
                "type": "requests",
                "attributes": {
                    "request_id": request_payload["request_id"],
                    "original_message_content": request_payload["original_message_content"],
                    "requested_by": request_payload["requested_by"],
                    "platform_message_id": request_payload["platform_message_id"],
                    "platform_channel_id": request_payload["platform_channel_id"],
                    "platform_author_id": request_payload["platform_author_id"],
                    "platform_timestamp": request_payload["platform_timestamp"],
                    "community_server_id": request_payload["community_server_id"],
                },
            }
        }
        response = await client.post("/api/v2/requests", json=jsonapi_payload, headers=auth_headers)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    assert response.status_code in [
        200,
        201,
    ], f"Expected 200/201, got {response.status_code}: {response.text}"

    response_data = response.json()

    attrs = response_data["data"]["attributes"]

    assert isinstance(attrs["platform_message_id"], str), (
        f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
    )
    assert attrs["platform_message_id"] == "1436038555091865653"

    if attrs.get("note_id") is not None:
        assert isinstance(attrs["note_id"], str), (
            f"note_id should be string, got {type(attrs['note_id'])}"
        )

    print("Test passed!")
