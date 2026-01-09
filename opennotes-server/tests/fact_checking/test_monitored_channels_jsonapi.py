"""Tests for JSON:API v2 monitored-channels endpoints.

This module contains integration tests for the /api/v2/monitored-channels endpoint
that follows the JSON:API 1.1 specification. These tests verify:
- GET /api/v2/monitored-channels returns paginated list
- GET /api/v2/monitored-channels/{id} returns single resource
- POST /api/v2/monitored-channels creates a channel
- PATCH /api/v2/monitored-channels/{id} updates a channel
- DELETE /api/v2/monitored-channels/{id} removes a channel
- Proper JSON:API response envelope structure

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def monitored_channels_jsonapi_community_server():
    """Create a test community server for monitored channels JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_monitored_channels_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Monitored Channels JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def monitored_channels_jsonapi_test_user():
    """Create a unique test user for monitored channels JSON:API tests."""
    return {
        "username": f"monitored_channels_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"monitored_channels_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Monitored Channels JSONAPI Test User",
    }


@pytest.fixture
async def monitored_channels_jsonapi_registered_user(
    monitored_channels_jsonapi_test_user, monitored_channels_jsonapi_community_server
):
    """Create a registered user with admin role for monitored channels JSON:API tests."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=monitored_channels_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(
                User.username == monitored_channels_jsonapi_test_user["username"]
            )
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"monitored_channels_jsonapi_discord_{uuid4().hex[:8]}"

            profile = UserProfile(
                display_name=user.full_name or user.username,
                is_human=True,
                is_active=True,
            )
            session.add(profile)
            await session.flush()

            identity = UserIdentity(
                profile_id=profile.id,
                provider="discord",
                provider_user_id=user.discord_id,
            )
            session.add(identity)

            member = CommunityMember(
                community_id=monitored_channels_jsonapi_community_server["uuid"],
                profile_id=profile.id,
                role="admin",
                is_active=True,
                joined_at=datetime.now(UTC),
            )
            session.add(member)

            await session.commit()
            await session.refresh(user)
            await session.refresh(profile)

            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "discord_id": user.discord_id,
                "profile_id": profile.id,
            }


@pytest.fixture
async def monitored_channels_jsonapi_auth_headers(monitored_channels_jsonapi_registered_user):
    """Generate auth headers for monitored channels JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(monitored_channels_jsonapi_registered_user["id"]),
        "username": monitored_channels_jsonapi_registered_user["username"],
        "role": monitored_channels_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def monitored_channels_jsonapi_auth_client(monitored_channels_jsonapi_auth_headers):
    """Auth client using monitored channels JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(monitored_channels_jsonapi_auth_headers)
        yield client


class TestMonitoredChannelsJSONAPIList:
    """Tests for GET /api/v2/monitored-channels."""

    @pytest.mark.asyncio
    async def test_list_monitored_channels_jsonapi(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test GET /api/v2/monitored-channels returns paginated list.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' array containing resource objects
        - Each resource has 'type', 'id', and 'attributes'
        - Pagination via page[number] and page[size]
        """
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]

        response = await monitored_channels_jsonapi_auth_client.get(
            f"/api/v2/monitored-channels?filter[community_server_id]={platform_id}"
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"
        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_list_monitored_channels_jsonapi_pagination(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test GET /api/v2/monitored-channels supports JSON:API pagination."""
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]

        response = await monitored_channels_jsonapi_auth_client.get(
            f"/api/v2/monitored-channels?filter[community_server_id]={platform_id}&page[number]=1&page[size]=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data, "Response must contain 'links' for pagination"
        assert "meta" in data, "Response must contain 'meta' for pagination info"

    @pytest.mark.asyncio
    async def test_list_monitored_channels_requires_community_server_id(
        self,
        monitored_channels_jsonapi_auth_client,
    ):
        """Test GET /api/v2/monitored-channels requires community_server_id filter."""
        response = await monitored_channels_jsonapi_auth_client.get("/api/v2/monitored-channels")

        assert response.status_code == 400
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestMonitoredChannelsJSONAPIGet:
    """Tests for GET /api/v2/monitored-channels/{id}."""

    @pytest.mark.asyncio
    async def test_get_monitored_channel_jsonapi(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test GET /api/v2/monitored-channels/{id} returns single resource.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' object containing single resource
        - Resource has 'type', 'id', and 'attributes'
        """
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "monitored-channels",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                    "similarity_threshold": 0.75,
                },
            }
        }
        create_response = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await monitored_channels_jsonapi_auth_client.get(
            f"/api/v2/monitored-channels/{created_id}"
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "monitored-channels"
        assert data["data"]["id"] == created_id
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["channel_id"] == channel_id

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_monitored_channel_jsonapi_not_found(
        self,
        monitored_channels_jsonapi_auth_client,
    ):
        """Test GET /api/v2/monitored-channels/{id} returns 404 for non-existent channel."""
        fake_id = str(uuid4())

        response = await monitored_channels_jsonapi_auth_client.get(
            f"/api/v2/monitored-channels/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestMonitoredChannelsJSONAPICreate:
    """Tests for POST /api/v2/monitored-channels."""

    @pytest.mark.asyncio
    async def test_create_monitored_channel_jsonapi(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test POST /api/v2/monitored-channels creates a channel.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status
        - Response body with 'data' object containing created resource
        """
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_create_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "monitored-channels",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                    "similarity_threshold": 0.8,
                    "dataset_tags": ["snopes", "politifact"],
                },
            }
        }

        response = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "monitored-channels"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["channel_id"] == channel_id
        assert data["data"]["attributes"]["enabled"] is True
        assert data["data"]["attributes"]["similarity_threshold"] == 0.8

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_monitored_channel_jsonapi_invalid_type(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test POST /api/v2/monitored-channels rejects invalid resource type."""
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": "test_channel",
                },
            }
        }

        response = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_monitored_channel_jsonapi_conflict(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test POST /api/v2/monitored-channels returns 409 for duplicate channel."""
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_conflict_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "monitored-channels",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                },
            }
        }

        response1 = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=request_body
        )
        assert response1.status_code == 201

        response2 = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=request_body
        )
        assert response2.status_code == 409

        data = response2.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestMonitoredChannelsJSONAPIUpdate:
    """Tests for PATCH /api/v2/monitored-channels/{id}."""

    @pytest.mark.asyncio
    async def test_update_monitored_channel_jsonapi(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test PATCH /api/v2/monitored-channels/{id} updates a channel.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type', 'id', and 'attributes'
        - Response with 200 OK status
        - Response body with 'data' object containing updated resource
        """
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_update_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "monitored-channels",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                    "similarity_threshold": 0.75,
                },
            }
        }
        create_response = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "monitored-channels",
                "id": created_id,
                "attributes": {
                    "enabled": False,
                    "similarity_threshold": 0.9,
                },
            }
        }

        response = await monitored_channels_jsonapi_auth_client.patch(
            f"/api/v2/monitored-channels/{created_id}", json=update_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "monitored-channels"
        assert data["data"]["id"] == created_id
        assert data["data"]["attributes"]["enabled"] is False
        assert data["data"]["attributes"]["similarity_threshold"] == 0.9

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_monitored_channel_jsonapi_not_found(
        self,
        monitored_channels_jsonapi_auth_client,
    ):
        """Test PATCH /api/v2/monitored-channels/{id} returns 404 for non-existent channel."""
        fake_id = str(uuid4())

        update_body = {
            "data": {
                "type": "monitored-channels",
                "id": fake_id,
                "attributes": {
                    "enabled": False,
                },
            }
        }

        response = await monitored_channels_jsonapi_auth_client.patch(
            f"/api/v2/monitored-channels/{fake_id}", json=update_body
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_update_monitored_channel_jsonapi_id_mismatch(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test PATCH /api/v2/monitored-channels/{id} returns 409 if ID in body doesn't match URL."""
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_mismatch_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "monitored-channels",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                },
            }
        }
        create_response = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "monitored-channels",
                "id": str(uuid4()),
                "attributes": {
                    "enabled": False,
                },
            }
        }

        response = await monitored_channels_jsonapi_auth_client.patch(
            f"/api/v2/monitored-channels/{created_id}", json=update_body
        )

        assert response.status_code == 409


class TestMonitoredChannelsJSONAPIDelete:
    """Tests for DELETE /api/v2/monitored-channels/{id}."""

    @pytest.mark.asyncio
    async def test_delete_monitored_channel_jsonapi(
        self,
        monitored_channels_jsonapi_auth_client,
        monitored_channels_jsonapi_community_server,
    ):
        """Test DELETE /api/v2/monitored-channels/{id} removes a channel.

        JSON:API 1.1 requires:
        - Response with 204 No Content status
        - No response body
        """
        platform_id = monitored_channels_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_delete_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "monitored-channels",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                },
            }
        }
        create_response = await monitored_channels_jsonapi_auth_client.post(
            "/api/v2/monitored-channels", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await monitored_channels_jsonapi_auth_client.delete(
            f"/api/v2/monitored-channels/{created_id}"
        )

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

        get_response = await monitored_channels_jsonapi_auth_client.get(
            f"/api/v2/monitored-channels/{created_id}"
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_monitored_channel_jsonapi_not_found(
        self,
        monitored_channels_jsonapi_auth_client,
    ):
        """Test DELETE /api/v2/monitored-channels/{id} returns 404 for non-existent channel."""
        fake_id = str(uuid4())

        response = await monitored_channels_jsonapi_auth_client.delete(
            f"/api/v2/monitored-channels/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
