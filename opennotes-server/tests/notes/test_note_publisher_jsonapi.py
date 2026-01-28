"""Tests for JSON:API v2 note-publisher endpoints.

This module contains integration tests for the note publisher endpoints
that follow the JSON:API 1.1 specification. These tests verify:
- GET /api/v2/note-publisher-configs returns paginated list
- GET /api/v2/note-publisher-configs/{id} returns single resource
- POST /api/v2/note-publisher-configs creates a config
- PATCH /api/v2/note-publisher-configs/{id} updates a config
- DELETE /api/v2/note-publisher-configs/{id} removes a config
- GET /api/v2/note-publisher-posts returns paginated list
- GET /api/v2/note-publisher-posts/{id} returns single resource
- POST /api/v2/note-publisher-posts creates a post record
- Proper JSON:API response envelope structure

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def note_publisher_jsonapi_community_server():
    """Create a test community server for note publisher JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_note_publisher_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Note Publisher JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def note_publisher_jsonapi_test_user():
    """Create a unique test user for note publisher JSON:API tests."""
    return {
        "username": f"note_publisher_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"note_publisher_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Note Publisher JSONAPI Test User",
    }


@pytest.fixture
async def note_publisher_jsonapi_registered_user(
    note_publisher_jsonapi_test_user, note_publisher_jsonapi_community_server
):
    """Create a registered user with admin role for note publisher JSON:API tests."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=note_publisher_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == note_publisher_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"note_publisher_jsonapi_discord_{uuid4().hex[:8]}"

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
                community_id=note_publisher_jsonapi_community_server["uuid"],
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
async def note_publisher_jsonapi_auth_headers(note_publisher_jsonapi_registered_user):
    """Generate auth headers for note publisher JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(note_publisher_jsonapi_registered_user["id"]),
        "username": note_publisher_jsonapi_registered_user["username"],
        "role": note_publisher_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def note_publisher_jsonapi_auth_client(note_publisher_jsonapi_auth_headers):
    """Auth client using note publisher JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(note_publisher_jsonapi_auth_headers)
        yield client


@pytest.fixture
async def note_publisher_jsonapi_test_note(note_publisher_jsonapi_community_server):
    """Create a test note for note publisher JSON:API tests."""
    from src.database import get_session_maker
    from src.notes.models import Note

    note_id = uuid4()
    async with get_session_maker()() as db:
        note = Note(
            id=note_id,
            summary=f"Test note summary for publisher JSONAPI {uuid4().hex[:8]}",
            classification="NOT_MISLEADING",
            author_id=f"test_author_{uuid4().hex[:8]}",
            channel_id=f"test_channel_{uuid4().hex[:8]}",
            community_server_id=note_publisher_jsonapi_community_server["uuid"],
            status="CURRENTLY_RATED_HELPFUL",
        )
        db.add(note)
        await db.commit()

    return {"id": note_id}


@pytest.fixture
async def note_publisher_jsonapi_unauth_user():
    """Create a test user without community membership for authorization tests."""
    return {
        "username": f"note_publisher_unauth_user_{uuid4().hex[:8]}",
        "email": f"note_publisher_unauth_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Note Publisher Unauthorized Test User",
    }


@pytest.fixture
async def note_publisher_jsonapi_unauth_registered_user(note_publisher_jsonapi_unauth_user):
    """Create a registered user WITHOUT community membership for authorization tests."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=note_publisher_jsonapi_unauth_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(
                User.username == note_publisher_jsonapi_unauth_user["username"]
            )
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"note_publisher_unauth_discord_{uuid4().hex[:8]}"

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
async def note_publisher_jsonapi_unauth_headers(note_publisher_jsonapi_unauth_registered_user):
    """Generate auth headers for unauthorized test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(note_publisher_jsonapi_unauth_registered_user["id"]),
        "username": note_publisher_jsonapi_unauth_registered_user["username"],
        "role": note_publisher_jsonapi_unauth_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def note_publisher_jsonapi_unauth_client(note_publisher_jsonapi_unauth_headers):
    """Auth client using unauthorized test user (no community membership)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(note_publisher_jsonapi_unauth_headers)
        yield client


class TestNotePublisherConfigsJSONAPIList:
    """Tests for GET /api/v2/note-publisher-configs."""

    @pytest.mark.asyncio
    async def test_list_note_publisher_configs_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test GET /api/v2/note-publisher-configs returns paginated list.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' array containing resource objects
        - Each resource has 'type', 'id', and 'attributes'
        - Pagination via page[number] and page[size]
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-configs?filter[community_server_id]={platform_id}"
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
    async def test_list_note_publisher_configs_jsonapi_pagination(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test GET /api/v2/note-publisher-configs supports JSON:API pagination."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-configs?filter[community_server_id]={platform_id}&page[number]=1&page[size]=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data, "Response must contain 'links' for pagination"
        assert "meta" in data, "Response must contain 'meta' for pagination info"

    @pytest.mark.asyncio
    async def test_list_note_publisher_configs_requires_community_server_id(
        self,
        note_publisher_jsonapi_auth_client,
    ):
        """Test GET /api/v2/note-publisher-configs requires community_server_id filter."""
        response = await note_publisher_jsonapi_auth_client.get("/api/v2/note-publisher-configs")

        assert response.status_code == 400
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestNotePublisherConfigsJSONAPIGet:
    """Tests for GET /api/v2/note-publisher-configs/{id}."""

    @pytest.mark.asyncio
    async def test_get_note_publisher_config_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test GET /api/v2/note-publisher-configs/{id} returns single resource.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' object containing single resource
        - Resource has 'type', 'id', and 'attributes'
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]

        create_body = {
            "data": {
                "type": "note-publisher-configs",
                "attributes": {
                    "community_server_id": platform_id,
                    "enabled": True,
                    "threshold": 0.75,
                },
            }
        }
        create_response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=create_body
        )
        assert create_response.status_code == 201, f"Create failed: {create_response.text}"
        created_id = create_response.json()["data"]["id"]

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-configs/{created_id}"
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "note-publisher-configs"
        assert data["data"]["id"] == created_id
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["enabled"] is True

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_note_publisher_config_jsonapi_not_found(
        self,
        note_publisher_jsonapi_auth_client,
    ):
        """Test GET /api/v2/note-publisher-configs/{id} returns 404 for non-existent config."""
        fake_id = str(uuid4())

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-configs/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestNotePublisherConfigsJSONAPICreate:
    """Tests for POST /api/v2/note-publisher-configs."""

    @pytest.mark.asyncio
    async def test_create_note_publisher_config_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test POST /api/v2/note-publisher-configs creates a config.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status
        - Response body with 'data' object containing created resource
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_create_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "note-publisher-configs",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                    "threshold": 0.8,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "note-publisher-configs"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["channel_id"] == channel_id
        assert data["data"]["attributes"]["enabled"] is True
        assert data["data"]["attributes"]["threshold"] == 0.8

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_note_publisher_config_jsonapi_invalid_type(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test POST /api/v2/note-publisher-configs rejects invalid resource type."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "community_server_id": platform_id,
                    "enabled": True,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_note_publisher_config_jsonapi_conflict(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test POST /api/v2/note-publisher-configs returns 409 for duplicate config."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_conflict_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "note-publisher-configs",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                },
            }
        }

        response1 = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=request_body
        )
        assert response1.status_code == 201

        response2 = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=request_body
        )
        assert response2.status_code == 409

        data = response2.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestNotePublisherConfigsJSONAPIUpdate:
    """Tests for PATCH /api/v2/note-publisher-configs/{id}."""

    @pytest.mark.asyncio
    async def test_update_note_publisher_config_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test PATCH /api/v2/note-publisher-configs/{id} updates a config.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type', 'id', and 'attributes'
        - Response with 200 OK status
        - Response body with 'data' object containing updated resource
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_update_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "note-publisher-configs",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                    "threshold": 0.75,
                },
            }
        }
        create_response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "note-publisher-configs",
                "id": created_id,
                "attributes": {
                    "enabled": False,
                    "threshold": 0.9,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.patch(
            f"/api/v2/note-publisher-configs/{created_id}", json=update_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "note-publisher-configs"
        assert data["data"]["id"] == created_id
        assert data["data"]["attributes"]["enabled"] is False
        assert data["data"]["attributes"]["threshold"] == 0.9

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_note_publisher_config_jsonapi_not_found(
        self,
        note_publisher_jsonapi_auth_client,
    ):
        """Test PATCH /api/v2/note-publisher-configs/{id} returns 404 for non-existent config."""
        fake_id = str(uuid4())

        update_body = {
            "data": {
                "type": "note-publisher-configs",
                "id": fake_id,
                "attributes": {
                    "enabled": False,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.patch(
            f"/api/v2/note-publisher-configs/{fake_id}", json=update_body
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_update_note_publisher_config_jsonapi_id_mismatch(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test PATCH /api/v2/note-publisher-configs/{id} returns 409 if ID in body doesn't match URL."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_mismatch_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "note-publisher-configs",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                },
            }
        }
        create_response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "note-publisher-configs",
                "id": str(uuid4()),
                "attributes": {
                    "enabled": False,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.patch(
            f"/api/v2/note-publisher-configs/{created_id}", json=update_body
        )

        assert response.status_code == 409


class TestNotePublisherConfigsJSONAPIDelete:
    """Tests for DELETE /api/v2/note-publisher-configs/{id}."""

    @pytest.mark.asyncio
    async def test_delete_note_publisher_config_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test DELETE /api/v2/note-publisher-configs/{id} removes a config.

        JSON:API 1.1 requires:
        - Response with 204 No Content status
        - No response body
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        channel_id = f"test_channel_delete_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "note-publisher-configs",
                "attributes": {
                    "community_server_id": platform_id,
                    "channel_id": channel_id,
                    "enabled": True,
                },
            }
        }
        create_response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-configs", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await note_publisher_jsonapi_auth_client.delete(
            f"/api/v2/note-publisher-configs/{created_id}"
        )

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

        get_response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-configs/{created_id}"
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_note_publisher_config_jsonapi_not_found(
        self,
        note_publisher_jsonapi_auth_client,
    ):
        """Test DELETE /api/v2/note-publisher-configs/{id} returns 404 for non-existent config."""
        fake_id = str(uuid4())

        response = await note_publisher_jsonapi_auth_client.delete(
            f"/api/v2/note-publisher-configs/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestNotePublisherPostsJSONAPIList:
    """Tests for GET /api/v2/note-publisher-posts."""

    @pytest.mark.asyncio
    async def test_list_note_publisher_posts_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test GET /api/v2/note-publisher-posts returns paginated list.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' array containing resource objects
        - Each resource has 'type', 'id', and 'attributes'
        - Pagination via page[number] and page[size]
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-posts?filter[community_server_id]={platform_id}"
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
    async def test_list_note_publisher_posts_jsonapi_pagination(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
    ):
        """Test GET /api/v2/note-publisher-posts supports JSON:API pagination."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-posts?filter[community_server_id]={platform_id}&page[number]=1&page[size]=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data, "Response must contain 'links' for pagination"
        assert "meta" in data, "Response must contain 'meta' for pagination info"

    @pytest.mark.asyncio
    async def test_list_note_publisher_posts_requires_community_server_id(
        self,
        note_publisher_jsonapi_auth_client,
    ):
        """Test GET /api/v2/note-publisher-posts requires community_server_id filter."""
        response = await note_publisher_jsonapi_auth_client.get("/api/v2/note-publisher-posts")

        assert response.status_code == 400
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestNotePublisherPostsJSONAPIGet:
    """Tests for GET /api/v2/note-publisher-posts/{id}."""

    @pytest.mark.asyncio
    async def test_get_note_publisher_post_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
        note_publisher_jsonapi_test_note,
    ):
        """Test GET /api/v2/note-publisher-posts/{id} returns single resource.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' object containing single resource
        - Resource has 'type', 'id', and 'attributes'
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        note_id = str(note_publisher_jsonapi_test_note["id"])

        create_body = {
            "data": {
                "type": "note-publisher-posts",
                "attributes": {
                    "note_id": note_id,
                    "original_message_id": f"test_msg_{uuid4().hex[:8]}",
                    "channel_id": f"test_channel_{uuid4().hex[:8]}",
                    "community_server_id": platform_id,
                    "score_at_post": 0.85,
                    "confidence_at_post": "high",
                    "success": True,
                },
            }
        }
        create_response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-posts", json=create_body
        )
        assert create_response.status_code == 201, f"Create failed: {create_response.text}"
        created_id = create_response.json()["data"]["id"]

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-posts/{created_id}"
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "note-publisher-posts"
        assert data["data"]["id"] == created_id
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["success"] is True

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_note_publisher_post_jsonapi_not_found(
        self,
        note_publisher_jsonapi_auth_client,
    ):
        """Test GET /api/v2/note-publisher-posts/{id} returns 404 for non-existent post."""
        fake_id = str(uuid4())

        response = await note_publisher_jsonapi_auth_client.get(
            f"/api/v2/note-publisher-posts/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestNotePublisherPostsJSONAPICreate:
    """Tests for POST /api/v2/note-publisher-posts."""

    @pytest.mark.asyncio
    async def test_create_note_publisher_post_jsonapi(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
        note_publisher_jsonapi_test_note,
    ):
        """Test POST /api/v2/note-publisher-posts creates a post record.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status
        - Response body with 'data' object containing created resource
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        note_id = str(note_publisher_jsonapi_test_note["id"])
        original_message_id = f"test_msg_create_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "note-publisher-posts",
                "attributes": {
                    "note_id": note_id,
                    "original_message_id": original_message_id,
                    "channel_id": f"test_channel_{uuid4().hex[:8]}",
                    "community_server_id": platform_id,
                    "score_at_post": 0.9,
                    "confidence_at_post": "very_high",
                    "success": True,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-posts", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "note-publisher-posts"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["original_message_id"] == original_message_id
        assert data["data"]["attributes"]["success"] is True
        assert data["data"]["attributes"]["score_at_post"] == 0.9

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_note_publisher_post_jsonapi_invalid_type(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
        note_publisher_jsonapi_test_note,
    ):
        """Test POST /api/v2/note-publisher-posts rejects invalid resource type."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        note_id = str(note_publisher_jsonapi_test_note["id"])

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "note_id": note_id,
                    "original_message_id": "test_msg",
                    "channel_id": "test_channel",
                    "community_server_id": platform_id,
                    "score_at_post": 0.85,
                    "confidence_at_post": "high",
                    "success": True,
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-posts", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_note_publisher_post_jsonapi_conflict(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
        note_publisher_jsonapi_test_note,
    ):
        """Test POST /api/v2/note-publisher-posts returns 409 for duplicate original_message_id."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        note_id = str(note_publisher_jsonapi_test_note["id"])
        original_message_id = f"test_msg_conflict_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "note-publisher-posts",
                "attributes": {
                    "note_id": note_id,
                    "original_message_id": original_message_id,
                    "channel_id": f"test_channel_{uuid4().hex[:8]}",
                    "community_server_id": platform_id,
                    "score_at_post": 0.85,
                    "confidence_at_post": "high",
                    "success": True,
                },
            }
        }

        response1 = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-posts", json=request_body
        )
        assert response1.status_code == 201

        response2 = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-posts", json=request_body
        )
        assert response2.status_code == 409

        data = response2.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_create_note_publisher_post_jsonapi_with_error(
        self,
        note_publisher_jsonapi_auth_client,
        note_publisher_jsonapi_community_server,
        note_publisher_jsonapi_test_note,
    ):
        """Test POST /api/v2/note-publisher-posts creates a failed post record."""
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        note_id = str(note_publisher_jsonapi_test_note["id"])
        original_message_id = f"test_msg_error_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "note-publisher-posts",
                "attributes": {
                    "note_id": note_id,
                    "original_message_id": original_message_id,
                    "channel_id": f"test_channel_{uuid4().hex[:8]}",
                    "community_server_id": platform_id,
                    "score_at_post": 0.85,
                    "confidence_at_post": "high",
                    "success": False,
                    "error_message": "Discord API rate limited",
                },
            }
        }

        response = await note_publisher_jsonapi_auth_client.post(
            "/api/v2/note-publisher-posts", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["success"] is False
        assert data["data"]["attributes"]["error_message"] == "Discord API rate limited"

    @pytest.mark.asyncio
    async def test_create_note_publisher_post_jsonapi_unauthorized(
        self,
        note_publisher_jsonapi_unauth_client,
        note_publisher_jsonapi_community_server,
        note_publisher_jsonapi_test_note,
    ):
        """Test that unauthorized users cannot create posts for communities they don't belong to.

        This test verifies the security fix for the authorization vulnerability where
        an authenticated user could create post records for any community they don't belong to.
        """
        platform_id = note_publisher_jsonapi_community_server["platform_community_server_id"]
        note_id = str(note_publisher_jsonapi_test_note["id"])
        original_message_id = f"test_msg_unauth_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "note-publisher-posts",
                "attributes": {
                    "note_id": note_id,
                    "original_message_id": original_message_id,
                    "channel_id": f"test_channel_{uuid4().hex[:8]}",
                    "community_server_id": platform_id,
                    "score_at_post": 0.9,
                    "confidence_at_post": "very_high",
                    "success": True,
                },
            }
        }

        response = await note_publisher_jsonapi_unauth_client.post(
            "/api/v2/note-publisher-posts", json=request_body
        )

        assert response.status_code == 403, (
            f"Expected 403 Forbidden, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "detail" in data, "Error response must contain 'detail' key"
        assert "not a member" in data["detail"].lower(), "Error should mention community membership"
