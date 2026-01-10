"""Tests for JSON:API v2 community-servers endpoint.

This module contains integration tests for the /api/v2/community-servers endpoint that follows
the JSON:API 1.1 specification. These tests verify:
- Proper JSON:API response envelope structure
- Community server lookup operations
- Community server retrieval by ID

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile


@pytest.fixture
async def communities_jsonapi_community_server():
    """Create a test community server for communities JSON:API tests."""
    community_server_id = uuid4()
    unique_suffix = uuid4().hex[:8]
    platform_id = f"test_guild_communities_jsonapi_{unique_suffix}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name=f"Test Guild for Communities JSONAPI {unique_suffix}",
            description="A test community for JSON:API endpoint testing",
            is_public=True,
            is_active=True,
        )
        db.add(community_server)
        await db.commit()

    return {
        "uuid": community_server_id,
        "platform_community_server_id": platform_id,
        "platform": "discord",
        "name": f"Test Guild for Communities JSONAPI {unique_suffix}",
    }


@pytest.fixture
async def communities_jsonapi_test_user():
    """Create a unique test user for communities JSON:API tests."""
    unique_suffix = uuid4().hex[:8]
    return {
        "username": f"communitiesjsonapitestuser_{unique_suffix}",
        "email": f"communitiesjsonapitest_{unique_suffix}@example.com",
        "password": "TestPassword123!",
        "full_name": "Communities JSONAPI Test User",
    }


@pytest.fixture
async def communities_jsonapi_registered_user(
    communities_jsonapi_test_user, communities_jsonapi_community_server
):
    """Create a registered user with profile for communities JSON:API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=communities_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == communities_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            unique_discord_id = f"communities_jsonapi_discord_{uuid4().hex[:12]}"
            user.discord_id = unique_discord_id

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
                provider_user_id=unique_discord_id,
            )
            session.add(identity)

            member = CommunityMember(
                community_id=communities_jsonapi_community_server["uuid"],
                profile_id=profile.id,
                role="member",
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
async def communities_jsonapi_auth_headers(communities_jsonapi_registered_user):
    """Generate auth headers for communities JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(communities_jsonapi_registered_user["id"]),
        "username": communities_jsonapi_registered_user["username"],
        "role": communities_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def communities_jsonapi_auth_client(communities_jsonapi_auth_headers):
    """Auth client using communities JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(communities_jsonapi_auth_headers)
        yield client


class TestCommunitiesJSONAPI:
    """Tests for the JSON:API v2 community-servers endpoint."""

    @pytest.mark.asyncio
    async def test_lookup_community_server_jsonapi_format(
        self, communities_jsonapi_auth_client, communities_jsonapi_community_server
    ):
        """Test GET /api/v2/community-servers/lookup returns proper JSON:API format.

        JSON:API 1.1 requires:
        - 'data' object containing resource object
        - 'jsonapi' object with version
        """
        response = await communities_jsonapi_auth_client.get(
            "/api/v2/community-servers/lookup",
            params={
                "platform": communities_jsonapi_community_server["platform"],
                "platform_community_server_id": communities_jsonapi_community_server[
                    "platform_community_server_id"
                ],
            },
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

    @pytest.mark.asyncio
    async def test_community_server_resource_object_structure(
        self, communities_jsonapi_auth_client, communities_jsonapi_community_server
    ):
        """Test that community server resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier ('community-servers')
        - 'id': unique identifier string
        - 'attributes': object containing resource attributes
        """
        response = await communities_jsonapi_auth_client.get(
            "/api/v2/community-servers/lookup",
            params={
                "platform": communities_jsonapi_community_server["platform"],
                "platform_community_server_id": communities_jsonapi_community_server[
                    "platform_community_server_id"
                ],
            },
        )
        assert response.status_code == 200

        data = response.json()
        server_resource = data["data"]

        assert "type" in server_resource, "Resource must have 'type'"
        assert server_resource["type"] == "community-servers", (
            "Resource type must be 'community-servers'"
        )

        assert "id" in server_resource, "Resource must have 'id'"
        assert isinstance(server_resource["id"], str), "Resource id must be a string"
        assert server_resource["id"] == str(communities_jsonapi_community_server["uuid"]), (
            "Resource id must match community server UUID"
        )

        assert "attributes" in server_resource, "Resource must have 'attributes'"
        attributes = server_resource["attributes"]
        assert "platform" in attributes, "Attributes must include 'platform'"
        assert "platform_community_server_id" in attributes, (
            "Attributes must include 'platform_community_server_id'"
        )
        assert "name" in attributes, "Attributes must include 'name'"
        assert "is_active" in attributes, "Attributes must include 'is_active'"

    @pytest.mark.asyncio
    async def test_get_community_server_by_id_jsonapi_format(
        self, communities_jsonapi_auth_client, communities_jsonapi_community_server
    ):
        """Test GET /api/v2/community-servers/{id} returns server in JSON:API format."""
        server_id = communities_jsonapi_community_server["uuid"]
        response = await communities_jsonapi_auth_client.get(
            f"/api/v2/community-servers/{server_id}"
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"
        assert data["data"]["type"] == "community-servers", (
            "Resource type must be 'community-servers'"
        )
        assert data["data"]["id"] == str(server_id), "Resource id must match"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1"

        attributes = data["data"]["attributes"]
        assert attributes["name"] == communities_jsonapi_community_server["name"]
        assert attributes["platform"] == "discord"
        assert attributes["is_active"] is True

    @pytest.mark.asyncio
    async def test_jsonapi_content_type_communities(
        self, communities_jsonapi_auth_client, communities_jsonapi_community_server
    ):
        """Test that response Content-Type is application/vnd.api+json."""
        response = await communities_jsonapi_auth_client.get(
            "/api/v2/community-servers/lookup",
            params={
                "platform": communities_jsonapi_community_server["platform"],
                "platform_community_server_id": communities_jsonapi_community_server[
                    "platform_community_server_id"
                ],
            },
        )
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_community_server_not_found_jsonapi_error(self, communities_jsonapi_auth_client):
        """Test that 404 errors are returned in JSON:API error format."""
        fake_id = str(uuid4())
        response = await communities_jsonapi_auth_client.get(f"/api/v2/community-servers/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert isinstance(data["errors"], list), "'errors' must be an array"

        error = data["errors"][0]
        assert "status" in error or "title" in error, "Error must have status or title"

    @pytest.mark.asyncio
    async def test_lookup_not_found_jsonapi_error(self, communities_jsonapi_auth_client):
        """Test that lookup 404 errors are returned in JSON:API error format."""
        response = await communities_jsonapi_auth_client.get(
            "/api/v2/community-servers/lookup",
            params={
                "platform": "discord",
                "platform_community_server_id": "nonexistent_guild_id_12345",
            },
        )
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert isinstance(data["errors"], list), "'errors' must be an array"

    @pytest.mark.asyncio
    async def test_unauthenticated_lookup_returns_401(self):
        """Test that GET /api/v2/community-servers/lookup without auth returns 401.

        Note: Authentication errors (401) are returned by FastAPI's security
        dependencies before reaching our JSON:API handlers, so they don't
        follow JSON:API error format. This is expected behavior.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v2/community-servers/lookup",
                params={"platform": "discord", "platform_community_server_id": "some_id"},
            )
            assert response.status_code == 401

            data = response.json()
            assert "detail" in data, "401 response from auth should contain 'detail'"
