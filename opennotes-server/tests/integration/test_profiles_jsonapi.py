"""Tests for JSON:API v2 profiles endpoint.

This module contains integration tests for the /api/v2/profiles endpoint that follows
the JSON:API 1.1 specification. These tests verify:
- Proper JSON:API response envelope structure
- Profile retrieval and update operations
- Relationship data inclusion (communities)

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
async def profiles_jsonapi_community_server():
    """Create a test community server for profiles JSON:API tests."""
    community_server_id = uuid4()
    platform_id = f"test_guild_profiles_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Profiles JSONAPI",
            is_public=True,
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def profiles_jsonapi_test_user():
    """Create a unique test user for profiles JSON:API tests."""
    unique_suffix = uuid4().hex[:8]
    return {
        "username": f"profilesjsonapitestuser_{unique_suffix}",
        "email": f"profilesjsonapitest_{unique_suffix}@example.com",
        "password": "TestPassword123!",
        "full_name": "Profiles JSONAPI Test User",
    }


@pytest.fixture
async def profiles_jsonapi_registered_user(
    profiles_jsonapi_test_user, profiles_jsonapi_community_server
):
    """Create a registered user with profile for profiles JSON:API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=profiles_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == profiles_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            unique_discord_id = f"profiles_jsonapi_discord_{uuid4().hex[:12]}"
            user.discord_id = unique_discord_id

            profile = UserProfile(
                display_name=user.full_name or user.username,
                is_human=True,
                is_active=True,
                bio="Test bio for JSON:API profile",
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
                community_id=profiles_jsonapi_community_server["uuid"],
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
async def profiles_jsonapi_auth_headers(profiles_jsonapi_registered_user):
    """Generate auth headers for profiles JSON:API test user."""
    from src.auth.profile_auth import create_profile_access_token

    access_token = create_profile_access_token(
        profile_id=profiles_jsonapi_registered_user["profile_id"],
        display_name=profiles_jsonapi_registered_user["full_name"],
        provider="discord",
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def profiles_jsonapi_auth_client(profiles_jsonapi_auth_headers):
    """Auth client using profiles JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(profiles_jsonapi_auth_headers)
        yield client


class TestProfilesJSONAPI:
    """Tests for the JSON:API v2 profiles endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_profile_jsonapi_format(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me returns proper JSON:API format.

        JSON:API 1.1 requires:
        - 'data' object containing resource object
        - 'jsonapi' object with version
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

    @pytest.mark.asyncio
    async def test_profile_resource_object_structure(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test that profile resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier ('profiles')
        - 'id': unique identifier string
        - 'attributes': object containing resource attributes
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me")
        assert response.status_code == 200

        data = response.json()
        profile_resource = data["data"]

        assert "type" in profile_resource, "Resource must have 'type'"
        assert profile_resource["type"] == "profiles", "Resource type must be 'profiles'"

        assert "id" in profile_resource, "Resource must have 'id'"
        assert isinstance(profile_resource["id"], str), "Resource id must be a string"
        assert profile_resource["id"] == str(profiles_jsonapi_registered_user["profile_id"]), (
            "Resource id must match profile_id"
        )

        assert "attributes" in profile_resource, "Resource must have 'attributes'"
        attributes = profile_resource["attributes"]
        assert "display_name" in attributes, "Attributes must include 'display_name'"
        assert "is_active" in attributes, "Attributes must include 'is_active'"
        assert "created_at" in attributes, "Attributes must include 'created_at'"

    @pytest.mark.asyncio
    async def test_get_public_profile_jsonapi_format(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/{id} returns public profile in JSON:API format."""
        profile_id = profiles_jsonapi_registered_user["profile_id"]
        response = await profiles_jsonapi_auth_client.get(f"/api/v2/profiles/{profile_id}")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"
        assert data["data"]["type"] == "profiles", "Resource type must be 'profiles'"
        assert data["data"]["id"] == str(profile_id), "Resource id must match"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1"

    @pytest.mark.asyncio
    async def test_update_profile_jsonapi_format(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test PATCH /api/v2/profiles/me updates profile with JSON:API format.

        JSON:API PATCH request should use standard JSON:API request body format
        with data object containing type, id, and attributes.
        """
        unique_suffix = uuid4().hex[:8]
        update_request = {
            "data": {
                "type": "profiles",
                "id": str(profiles_jsonapi_registered_user["profile_id"]),
                "attributes": {
                    "display_name": f"Updated Name {unique_suffix}",
                    "bio": "Updated bio via JSON:API",
                },
            }
        }

        response = await profiles_jsonapi_auth_client.patch(
            "/api/v2/profiles/me",
            json=update_request,
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "profiles", "Resource type must be 'profiles'"

        attributes = data["data"]["attributes"]
        assert attributes["display_name"] == f"Updated Name {unique_suffix}"
        assert attributes["bio"] == "Updated bio via JSON:API"

    @pytest.mark.asyncio
    async def test_list_user_communities_jsonapi_format(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities returns communities in JSON:API format."""
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/communities")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1"

        assert len(data["data"]) >= 1, "Should have at least one community membership"

        membership_resource = data["data"][0]
        assert "type" in membership_resource, "Resource must have 'type'"
        assert membership_resource["type"] == "community-memberships", (
            "Resource type must be 'community-memberships'"
        )
        assert "id" in membership_resource, "Resource must have 'id'"
        assert "attributes" in membership_resource, "Resource must have 'attributes'"

    @pytest.mark.asyncio
    async def test_list_communities_pagination_default_values(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities returns default pagination meta.

        When no pagination parameters are provided, the response should include:
        - meta.count: total number of communities
        - meta.limit: default of 50
        - meta.offset: default of 0
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/communities")
        assert response.status_code == 200

        data = response.json()

        assert "meta" in data, "Response must contain 'meta' key"
        meta = data["meta"]

        assert "count" in meta, "Meta must include 'count'"
        assert isinstance(meta["count"], int), "Count must be an integer"

        assert "limit" in meta, "Meta must include 'limit' for pagination"
        assert meta["limit"] == 50, "Default limit must be 50"

        assert "offset" in meta, "Meta must include 'offset' for pagination"
        assert meta["offset"] == 0, "Default offset must be 0"

    @pytest.mark.asyncio
    async def test_list_communities_pagination_with_custom_limit(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities respects custom limit parameter.

        When limit is provided, the response should:
        - Return at most 'limit' items in data array
        - Include limit value in meta
        """
        response = await profiles_jsonapi_auth_client.get(
            "/api/v2/profiles/me/communities?limit=10"
        )
        assert response.status_code == 200

        data = response.json()
        meta = data["meta"]

        assert meta["limit"] == 10, "Limit should reflect the requested value"
        assert len(data["data"]) <= 10, "Data array should not exceed limit"

    @pytest.mark.asyncio
    async def test_list_communities_pagination_with_offset(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities respects offset parameter.

        When offset is provided, the response should:
        - Skip the first 'offset' items
        - Include offset value in meta
        """
        response = await profiles_jsonapi_auth_client.get(
            "/api/v2/profiles/me/communities?offset=1"
        )
        assert response.status_code == 200

        data = response.json()
        meta = data["meta"]

        assert meta["offset"] == 1, "Offset should reflect the requested value"

    @pytest.mark.asyncio
    async def test_list_communities_pagination_limit_validation_max(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities validates limit max value.

        Limit values greater than 100 should return 400 error.
        """
        response = await profiles_jsonapi_auth_client.get(
            "/api/v2/profiles/me/communities?limit=101"
        )
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0, "Errors array must not be empty"

    @pytest.mark.asyncio
    async def test_list_communities_pagination_limit_validation_min(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities validates limit min value.

        Limit values less than 1 should return 400 error.
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/communities?limit=0")
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0, "Errors array must not be empty"

    @pytest.mark.asyncio
    async def test_list_communities_pagination_offset_validation(
        self,
        profiles_jsonapi_auth_client,
        profiles_jsonapi_registered_user,
        profiles_jsonapi_community_server,
    ):
        """Test GET /api/v2/profiles/me/communities validates offset value.

        Negative offset values should return 400 error.
        """
        response = await profiles_jsonapi_auth_client.get(
            "/api/v2/profiles/me/communities?offset=-1"
        )
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0, "Errors array must not be empty"

    @pytest.mark.asyncio
    async def test_jsonapi_content_type_profiles(self, profiles_jsonapi_auth_client):
        """Test that response Content-Type is application/vnd.api+json."""
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me")
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_profile_not_found_jsonapi_error(self, profiles_jsonapi_auth_client):
        """Test that 404 errors are returned in JSON:API error format."""
        fake_id = str(uuid4())
        response = await profiles_jsonapi_auth_client.get(f"/api/v2/profiles/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert isinstance(data["errors"], list), "'errors' must be an array"

        error = data["errors"][0]
        assert "status" in error or "title" in error, "Error must have status or title"

    @pytest.mark.asyncio
    async def test_unauthenticated_get_me_returns_401(self):
        """Test that GET /api/v2/profiles/me without auth returns 401.

        Note: Authentication errors (401) are returned by FastAPI's security
        dependencies before reaching our JSON:API handlers, so they don't
        follow JSON:API error format. This is expected behavior.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/profiles/me")
            assert response.status_code == 401

            data = response.json()
            assert "detail" in data, "401 response from auth should contain 'detail'"


class TestIdentitiesJSONAPI:
    """Tests for the JSON:API v2 identity management endpoints."""

    @pytest.mark.asyncio
    async def test_list_identities_jsonapi_format(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities returns proper JSON:API format.

        JSON:API 1.1 requires:
        - 'data' array containing resource objects
        - 'jsonapi' object with version
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

    @pytest.mark.asyncio
    async def test_identity_resource_object_structure(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test that identity resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier ('identities')
        - 'id': unique identifier string
        - 'attributes': object containing resource attributes
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities")
        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) >= 1, "Should have at least one identity"

        identity_resource = data["data"][0]

        assert "type" in identity_resource, "Resource must have 'type'"
        assert identity_resource["type"] == "identities", "Resource type must be 'identities'"

        assert "id" in identity_resource, "Resource must have 'id'"
        assert isinstance(identity_resource["id"], str), "Resource id must be a string"

        assert "attributes" in identity_resource, "Resource must have 'attributes'"
        attributes = identity_resource["attributes"]
        assert "provider" in attributes, "Attributes must include 'provider'"
        assert "provider_user_id" in attributes, "Attributes must include 'provider_user_id'"

    @pytest.mark.asyncio
    async def test_jsonapi_content_type_identities(self, profiles_jsonapi_auth_client):
        """Test that response Content-Type is application/vnd.api+json."""
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities")
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_link_identity_jsonapi_format(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test POST /api/v2/profiles/me/identities creates identity with JSON:API format.

        JSON:API POST request should use standard JSON:API request body format
        with data object containing type and attributes.
        """
        unique_github_id = f"github_test_{uuid4().hex[:8]}"
        create_request = {
            "data": {
                "type": "identities",
                "attributes": {
                    "provider": "github",
                    "provider_user_id": unique_github_id,
                    "credentials": {"oauth_verified": True},
                },
            }
        }

        response = await profiles_jsonapi_auth_client.post(
            "/api/v2/profiles/me/identities",
            json=create_request,
        )
        assert response.status_code == 201

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "identities", "Resource type must be 'identities'"

        attributes = data["data"]["attributes"]
        assert attributes["provider"] == "github"
        assert attributes["provider_user_id"] == unique_github_id

    @pytest.mark.asyncio
    async def test_link_identity_requires_oauth_verification(self, profiles_jsonapi_auth_client):
        """Test POST /api/v2/profiles/me/identities requires OAuth verification.

        Security requirement: Must have oauth_verified in credentials.
        """
        create_request = {
            "data": {
                "type": "identities",
                "attributes": {
                    "provider": "github",
                    "provider_user_id": f"github_test_{uuid4().hex[:8]}",
                },
            }
        }

        response = await profiles_jsonapi_auth_client.post(
            "/api/v2/profiles/me/identities",
            json=create_request,
        )
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_link_identity_conflict_jsonapi_error(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test POST /api/v2/profiles/me/identities returns 409 for duplicate provider.

        The fixture already has a Discord identity, so trying to add another
        should fail with conflict error.
        """
        create_request = {
            "data": {
                "type": "identities",
                "attributes": {
                    "provider": "discord",
                    "provider_user_id": profiles_jsonapi_registered_user["discord_id"],
                    "credentials": {"oauth_verified": True},
                },
            }
        }

        response = await profiles_jsonapi_auth_client.post(
            "/api/v2/profiles/me/identities",
            json=create_request,
        )
        assert response.status_code == 409

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_unlink_identity_jsonapi(self, profiles_jsonapi_auth_client):
        """Test DELETE /api/v2/profiles/me/identities/{id} deletes identity.

        First add a new identity, then delete it.
        """
        unique_github_id = f"github_delete_test_{uuid4().hex[:8]}"
        create_request = {
            "data": {
                "type": "identities",
                "attributes": {
                    "provider": "github",
                    "provider_user_id": unique_github_id,
                    "credentials": {"oauth_verified": True},
                },
            }
        }

        create_response = await profiles_jsonapi_auth_client.post(
            "/api/v2/profiles/me/identities",
            json=create_request,
        )
        assert create_response.status_code == 201
        identity_id = create_response.json()["data"]["id"]

        delete_response = await profiles_jsonapi_auth_client.delete(
            f"/api/v2/profiles/me/identities/{identity_id}",
        )
        assert delete_response.status_code == 204

    @pytest.mark.asyncio
    async def test_unlink_last_identity_fails(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test DELETE /api/v2/profiles/me/identities/{id} fails for last identity.

        Users must keep at least one identity.
        """
        list_response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities")
        identities = list_response.json()["data"]

        if len(identities) == 1:
            identity_id = identities[0]["id"]
            delete_response = await profiles_jsonapi_auth_client.delete(
                f"/api/v2/profiles/me/identities/{identity_id}",
            )
            assert delete_response.status_code == 400

            data = delete_response.json()
            assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_unlink_identity_not_found(self, profiles_jsonapi_auth_client):
        """Test DELETE /api/v2/profiles/me/identities/{id} returns 404 for invalid id."""
        fake_id = str(uuid4())
        response = await profiles_jsonapi_auth_client.delete(
            f"/api/v2/profiles/me/identities/{fake_id}",
        )
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_unauthenticated_list_identities_returns_401(self):
        """Test that GET /api/v2/profiles/me/identities without auth returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/profiles/me/identities")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_identities_pagination_default_values(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities returns default pagination meta.

        When no pagination parameters are provided, the response should include:
        - meta.count: total number of identities (already exists)
        - meta.limit: default of 50
        - meta.offset: default of 0
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities")
        assert response.status_code == 200

        data = response.json()

        assert "meta" in data, "Response must contain 'meta' key"
        meta = data["meta"]

        assert "count" in meta, "Meta must include 'count'"
        assert isinstance(meta["count"], int), "Count must be an integer"

        assert "limit" in meta, "Meta must include 'limit' for pagination"
        assert meta["limit"] == 50, "Default limit must be 50"

        assert "offset" in meta, "Meta must include 'offset' for pagination"
        assert meta["offset"] == 0, "Default offset must be 0"

    @pytest.mark.asyncio
    async def test_list_identities_pagination_with_custom_limit(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities respects custom limit parameter.

        When limit is provided, the response should:
        - Return at most 'limit' items in data array
        - Include limit value in meta
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities?limit=10")
        assert response.status_code == 200

        data = response.json()
        meta = data["meta"]

        assert meta["limit"] == 10, "Limit should reflect the requested value"
        assert len(data["data"]) <= 10, "Data array should not exceed limit"

    @pytest.mark.asyncio
    async def test_list_identities_pagination_with_offset(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities respects offset parameter.

        When offset is provided, the response should:
        - Skip the first 'offset' items
        - Include offset value in meta
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities?offset=1")
        assert response.status_code == 200

        data = response.json()
        meta = data["meta"]

        assert meta["offset"] == 1, "Offset should reflect the requested value"

    @pytest.mark.asyncio
    async def test_list_identities_pagination_limit_validation_max(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities validates limit max value.

        Limit values greater than 100 should return 400 error.
        """
        response = await profiles_jsonapi_auth_client.get(
            "/api/v2/profiles/me/identities?limit=101"
        )
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0, "Errors array must not be empty"

    @pytest.mark.asyncio
    async def test_list_identities_pagination_limit_validation_min(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities validates limit min value.

        Limit values less than 1 should return 400 error.
        """
        response = await profiles_jsonapi_auth_client.get("/api/v2/profiles/me/identities?limit=0")
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0, "Errors array must not be empty"

    @pytest.mark.asyncio
    async def test_list_identities_pagination_offset_validation(
        self, profiles_jsonapi_auth_client, profiles_jsonapi_registered_user
    ):
        """Test GET /api/v2/profiles/me/identities validates offset value.

        Negative offset values should return 400 error.
        """
        response = await profiles_jsonapi_auth_client.get(
            "/api/v2/profiles/me/identities?offset=-1"
        )
        assert response.status_code == 400

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0, "Errors array must not be empty"


class TestAdminStatusJSONAPIFixtures:
    """Fixtures for admin status JSON:API testing scenarios."""

    @pytest.fixture
    async def admin_test_profile(self):
        """Create a profile for testing admin status changes."""
        from src.database import get_session_maker
        from src.users.profile_crud import create_profile_with_identity
        from src.users.profile_schemas import (
            AuthProvider,
            UserProfileCreate,
        )

        unique_suffix = uuid4().hex[:8]
        unique_discord_id = f"discord_admin_test_{unique_suffix}"

        async with get_session_maker()() as db:
            profile_create = UserProfileCreate(
                display_name=f"Admin Test User {unique_suffix}",
                avatar_url=None,
                bio="Test user for admin status tests",
                role="user",
                is_opennotes_admin=False,
                is_human=True,
                is_active=True,
                is_banned=False,
                banned_at=None,
                banned_reason=None,
            )

            profile, _identity = await create_profile_with_identity(
                db=db,
                profile_create=profile_create,
                provider=AuthProvider.DISCORD,
                provider_user_id=unique_discord_id,
                credentials=None,
            )

            await db.commit()
            await db.refresh(profile)

            return {
                "profile_id": profile.id,
                "discord_id": unique_discord_id,
            }

    @pytest.fixture
    async def service_account_user_for_jsonapi(self):
        """Create a service account user for JSON:API admin tests."""
        from src.database import get_session_maker
        from src.users.models import User

        unique_suffix = uuid4().hex[:8]

        async with get_session_maker()() as db:
            user = User(
                id=uuid4(),
                username=f"admin-bot-jsonapi-{unique_suffix}-service",
                email=f"admin-bot-jsonapi-{unique_suffix}@opennotes.local",
                hashed_password="hashed_password_placeholder",
                role="user",
                is_active=True,
                is_superuser=False,
                is_service_account=True,
                discord_id=f"discord_service_{unique_suffix}",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            return {"user": user}

    @pytest.fixture
    async def service_account_headers_jsonapi(self, service_account_user_for_jsonapi):
        """Auth headers for service account in JSON:API tests."""
        from src.auth.auth import create_access_token

        user = service_account_user_for_jsonapi["user"]
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    async def service_account_client_jsonapi(self, service_account_headers_jsonapi):
        """Auth client for service account in JSON:API tests."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(service_account_headers_jsonapi)
            yield client


class TestAdminStatusJSONAPI(TestAdminStatusJSONAPIFixtures):
    """Tests for the JSON:API v2 admin status endpoints."""

    @pytest.mark.asyncio
    async def test_get_admin_status_jsonapi_format(
        self, service_account_client_jsonapi, admin_test_profile
    ):
        """Test GET /api/v2/profiles/{id}/opennotes-admin returns JSON:API format.

        JSON:API 1.1 requires:
        - 'data' object containing resource object
        - 'jsonapi' object with version
        """
        profile_id = admin_test_profile["profile_id"]
        response = await service_account_client_jsonapi.get(
            f"/api/v2/profiles/{profile_id}/opennotes-admin"
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

    @pytest.mark.asyncio
    async def test_admin_status_resource_object_structure(
        self, service_account_client_jsonapi, admin_test_profile
    ):
        """Test that admin status resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier ('admin-status')
        - 'id': unique identifier string (profile_id)
        - 'attributes': object containing resource attributes
        """
        profile_id = admin_test_profile["profile_id"]
        response = await service_account_client_jsonapi.get(
            f"/api/v2/profiles/{profile_id}/opennotes-admin"
        )
        assert response.status_code == 200

        data = response.json()
        admin_resource = data["data"]

        assert "type" in admin_resource, "Resource must have 'type'"
        assert admin_resource["type"] == "admin-status", "Resource type must be 'admin-status'"

        assert "id" in admin_resource, "Resource must have 'id'"
        assert admin_resource["id"] == str(profile_id), "Resource id must match profile_id"

        assert "attributes" in admin_resource, "Resource must have 'attributes'"
        attributes = admin_resource["attributes"]
        assert "is_opennotes_admin" in attributes, "Attributes must include 'is_opennotes_admin'"

    @pytest.mark.asyncio
    async def test_jsonapi_content_type_admin_status(
        self, service_account_client_jsonapi, admin_test_profile
    ):
        """Test that response Content-Type is application/vnd.api+json."""
        profile_id = admin_test_profile["profile_id"]
        response = await service_account_client_jsonapi.get(
            f"/api/v2/profiles/{profile_id}/opennotes-admin"
        )
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_update_admin_status_jsonapi_format(
        self, service_account_client_jsonapi, admin_test_profile
    ):
        """Test PATCH /api/v2/profiles/{id}/opennotes-admin updates with JSON:API format.

        JSON:API PATCH request should use standard JSON:API request body format
        with data object containing type, id, and attributes.
        """
        profile_id = admin_test_profile["profile_id"]
        update_request = {
            "data": {
                "type": "admin-status",
                "id": str(profile_id),
                "attributes": {
                    "is_opennotes_admin": True,
                },
            }
        }

        response = await service_account_client_jsonapi.patch(
            f"/api/v2/profiles/{profile_id}/opennotes-admin",
            json=update_request,
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "admin-status", "Resource type must be 'admin-status'"

        attributes = data["data"]["attributes"]
        assert attributes["is_opennotes_admin"] is True

    @pytest.mark.asyncio
    async def test_revoke_admin_status_jsonapi(
        self, service_account_client_jsonapi, admin_test_profile
    ):
        """Test PATCH /api/v2/profiles/{id}/opennotes-admin can revoke admin status."""
        profile_id = admin_test_profile["profile_id"]

        grant_request = {
            "data": {
                "type": "admin-status",
                "id": str(profile_id),
                "attributes": {"is_opennotes_admin": True},
            }
        }
        await service_account_client_jsonapi.patch(
            f"/api/v2/profiles/{profile_id}/opennotes-admin",
            json=grant_request,
        )

        revoke_request = {
            "data": {
                "type": "admin-status",
                "id": str(profile_id),
                "attributes": {"is_opennotes_admin": False},
            }
        }
        response = await service_account_client_jsonapi.patch(
            f"/api/v2/profiles/{profile_id}/opennotes-admin",
            json=revoke_request,
        )
        assert response.status_code == 200

        attributes = response.json()["data"]["attributes"]
        assert attributes["is_opennotes_admin"] is False

    @pytest.mark.asyncio
    async def test_get_admin_status_profile_not_found(self, service_account_client_jsonapi):
        """Test GET /api/v2/profiles/{id}/opennotes-admin returns 404 for invalid id."""
        fake_id = str(uuid4())
        response = await service_account_client_jsonapi.get(
            f"/api/v2/profiles/{fake_id}/opennotes-admin"
        )
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_update_admin_status_profile_not_found(self, service_account_client_jsonapi):
        """Test PATCH /api/v2/profiles/{id}/opennotes-admin returns 404 for invalid id."""
        fake_id = str(uuid4())
        update_request = {
            "data": {
                "type": "admin-status",
                "id": fake_id,
                "attributes": {"is_opennotes_admin": True},
            }
        }
        response = await service_account_client_jsonapi.patch(
            f"/api/v2/profiles/{fake_id}/opennotes-admin",
            json=update_request,
        )
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.fixture
    async def non_service_account_user_for_jsonapi(self):
        """Create a regular user (NOT a service account) for JSON:API tests."""
        from src.database import get_session_maker
        from src.users.models import User

        unique_suffix = uuid4().hex[:8]

        async with get_session_maker()() as db:
            user = User(
                id=uuid4(),
                username=f"regular-user-jsonapi-{unique_suffix}",
                email=f"regular-user-jsonapi-{unique_suffix}@example.com",
                hashed_password="hashed_password_placeholder",
                role="user",
                is_active=True,
                is_superuser=False,
                is_service_account=False,
                discord_id=f"discord_regular_{unique_suffix}",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            return {"user": user}

    @pytest.fixture
    async def non_service_account_headers_jsonapi(self, non_service_account_user_for_jsonapi):
        """Auth headers for non-service account user in JSON:API tests."""
        from src.auth.auth import create_access_token

        user = non_service_account_user_for_jsonapi["user"]
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    async def non_service_account_client_jsonapi(self, non_service_account_headers_jsonapi):
        """Auth client for non-service account user in JSON:API tests."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(non_service_account_headers_jsonapi)
            yield client

    @pytest.mark.asyncio
    async def test_non_service_account_cannot_get_admin_status(
        self, non_service_account_client_jsonapi, admin_test_profile
    ):
        """Test that non-service account users cannot access admin status endpoint."""
        profile_id = admin_test_profile["profile_id"]
        response = await non_service_account_client_jsonapi.get(
            f"/api/v2/profiles/{profile_id}/opennotes-admin"
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_service_account_cannot_update_admin_status(
        self, non_service_account_client_jsonapi, admin_test_profile
    ):
        """Test that non-service account users cannot update admin status."""
        profile_id = admin_test_profile["profile_id"]
        update_request = {
            "data": {
                "type": "admin-status",
                "id": str(profile_id),
                "attributes": {"is_opennotes_admin": True},
            }
        }
        response = await non_service_account_client_jsonapi.patch(
            f"/api/v2/profiles/{profile_id}/opennotes-admin",
            json=update_request,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_admin_status_returns_401(self):
        """Test that unauthenticated requests to admin status endpoint return 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake_id = str(uuid4())
            response = await client.get(f"/api/v2/profiles/{fake_id}/opennotes-admin")
            assert response.status_code == 401
