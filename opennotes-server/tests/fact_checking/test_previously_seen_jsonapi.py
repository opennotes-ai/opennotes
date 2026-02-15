"""Tests for JSON:API v2 previously-seen-messages endpoints.

This module contains integration tests for the /api/v2/previously-seen-messages endpoint
that follows the JSON:API 1.1 specification. These tests verify:
- GET /api/v2/previously-seen-messages returns paginated list
- GET /api/v2/previously-seen-messages/{id} returns single resource
- POST /api/v2/previously-seen-messages creates a record
- POST /api/v2/previously-seen-messages/check returns match info
- Proper JSON:API response envelope structure

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def previously_seen_jsonapi_community_server():
    """Create a test community server for previously seen JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_previously_seen_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Previously Seen JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def previously_seen_jsonapi_test_note(previously_seen_jsonapi_community_server):
    """Create a test note for previously seen JSON:API tests."""
    from src.database import get_session_maker
    from src.notes.models import Note

    note_id = uuid4()
    async with get_session_maker()() as db:
        note = Note(
            id=note_id,
            community_server_id=previously_seen_jsonapi_community_server["uuid"],
            author_id=f"test_author_{uuid4().hex[:8]}",
            summary=f"Test summary for previously seen tests {uuid4().hex[:8]}",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
        )
        db.add(note)
        await db.commit()

    return {"id": note_id}


@pytest.fixture
async def previously_seen_jsonapi_test_user():
    """Create a unique test user for previously seen JSON:API tests."""
    return {
        "username": f"previously_seen_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"previously_seen_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Previously Seen JSONAPI Test User",
    }


@pytest.fixture
async def previously_seen_jsonapi_registered_user(
    previously_seen_jsonapi_test_user, previously_seen_jsonapi_community_server
):
    """Create a registered user with admin role for previously seen JSON:API tests."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=previously_seen_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(
                User.username == previously_seen_jsonapi_test_user["username"]
            )
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"previously_seen_jsonapi_discord_{uuid4().hex[:8]}"

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
                community_id=previously_seen_jsonapi_community_server["uuid"],
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
async def previously_seen_jsonapi_auth_headers(previously_seen_jsonapi_registered_user):
    """Generate auth headers for previously seen JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(previously_seen_jsonapi_registered_user["id"]),
        "username": previously_seen_jsonapi_registered_user["username"],
        "role": previously_seen_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def previously_seen_jsonapi_auth_client(previously_seen_jsonapi_auth_headers):
    """Auth client using previously seen JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(previously_seen_jsonapi_auth_headers)
        yield client


class TestPreviouslySeenJSONAPIList:
    """Tests for GET /api/v2/previously-seen-messages."""

    @pytest.mark.asyncio
    async def test_list_previously_seen_messages_jsonapi(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
    ):
        """Test GET /api/v2/previously-seen-messages returns paginated list.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' array containing resource objects
        - Each resource has 'type', 'id', and 'attributes'
        - Pagination via page[number] and page[size]
        """
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])

        response = await previously_seen_jsonapi_auth_client.get(
            f"/api/v2/previously-seen-messages?filter[community_server_id]={community_uuid}"
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
    async def test_list_previously_seen_messages_jsonapi_pagination(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
    ):
        """Test GET /api/v2/previously-seen-messages supports JSON:API pagination."""
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])

        response = await previously_seen_jsonapi_auth_client.get(
            f"/api/v2/previously-seen-messages?filter[community_server_id]={community_uuid}&page[number]=1&page[size]=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data, "Response must contain 'links' for pagination"
        assert "meta" in data, "Response must contain 'meta' for pagination info"

    @pytest.mark.asyncio
    async def test_list_previously_seen_messages_requires_community_server_id(
        self,
        previously_seen_jsonapi_auth_client,
    ):
        """Test GET /api/v2/previously-seen-messages requires community_server_id filter."""
        response = await previously_seen_jsonapi_auth_client.get("/api/v2/previously-seen-messages")

        assert response.status_code == 400
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestPreviouslySeenJSONAPIGet:
    """Tests for GET /api/v2/previously-seen-messages/{id}."""

    @pytest.mark.asyncio
    async def test_get_previously_seen_message_jsonapi(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
        previously_seen_jsonapi_test_note,
    ):
        """Test GET /api/v2/previously-seen-messages/{id} returns single resource.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' object containing single resource
        - Resource has 'type', 'id', and 'attributes'
        """
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])
        note_id = str(previously_seen_jsonapi_test_note["id"])
        original_message_id = f"test_msg_{uuid4().hex[:8]}"

        create_body = {
            "data": {
                "type": "previously-seen-messages",
                "attributes": {
                    "community_server_id": community_uuid,
                    "original_message_id": original_message_id,
                    "published_note_id": note_id,
                },
            }
        }
        create_response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages", json=create_body
        )
        assert create_response.status_code == 201, f"Create failed: {create_response.text}"
        created_id = create_response.json()["data"]["id"]

        response = await previously_seen_jsonapi_auth_client.get(
            f"/api/v2/previously-seen-messages/{created_id}"
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "previously-seen-messages"
        assert data["data"]["id"] == created_id
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["original_message_id"] == original_message_id

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_previously_seen_message_jsonapi_not_found(
        self,
        previously_seen_jsonapi_auth_client,
    ):
        """Test GET /api/v2/previously-seen-messages/{id} returns 404 for non-existent record."""
        fake_id = str(uuid4())

        response = await previously_seen_jsonapi_auth_client.get(
            f"/api/v2/previously-seen-messages/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"


class TestPreviouslySeenJSONAPICreate:
    """Tests for POST /api/v2/previously-seen-messages."""

    @pytest.mark.asyncio
    async def test_create_previously_seen_message_jsonapi(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
        previously_seen_jsonapi_test_note,
    ):
        """Test POST /api/v2/previously-seen-messages creates a record.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status
        - Response body with 'data' object containing created resource
        """
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])
        note_id = str(previously_seen_jsonapi_test_note["id"])
        original_message_id = f"test_msg_create_{uuid4().hex[:8]}"

        request_body = {
            "data": {
                "type": "previously-seen-messages",
                "attributes": {
                    "community_server_id": community_uuid,
                    "original_message_id": original_message_id,
                    "published_note_id": note_id,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                    "extra_metadata": {"channel_id": "123456789"},
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "previously-seen-messages"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["original_message_id"] == original_message_id
        assert data["data"]["attributes"]["embedding_provider"] == "openai"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_previously_seen_message_jsonapi_invalid_type(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
        previously_seen_jsonapi_test_note,
    ):
        """Test POST /api/v2/previously-seen-messages rejects invalid resource type."""
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])
        note_id = str(previously_seen_jsonapi_test_note["id"])

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "community_server_id": community_uuid,
                    "original_message_id": "test_msg",
                    "published_note_id": note_id,
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_previously_seen_message_jsonapi_missing_required(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
    ):
        """Test POST /api/v2/previously-seen-messages returns 422 for missing required fields."""
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])

        request_body = {
            "data": {
                "type": "previously-seen-messages",
                "attributes": {
                    "community_server_id": community_uuid,
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_previously_seen_message_jsonapi_with_embedding(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
        previously_seen_jsonapi_test_note,
    ):
        """Test POST /api/v2/previously-seen-messages can include embedding vector."""
        community_uuid = str(previously_seen_jsonapi_community_server["uuid"])
        note_id = str(previously_seen_jsonapi_test_note["id"])
        original_message_id = f"test_msg_embedding_{uuid4().hex[:8]}"
        embedding = [0.1] * 1536

        request_body = {
            "data": {
                "type": "previously-seen-messages",
                "attributes": {
                    "community_server_id": community_uuid,
                    "original_message_id": original_message_id,
                    "published_note_id": note_id,
                    "embedding": embedding,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["embedding_provider"] == "openai"


class TestPreviouslySeenJSONAPICheck:
    """Tests for POST /api/v2/previously-seen-messages/check."""

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Check endpoint requires embedding service with OpenAI config. "
        "Testing full flow requires LLM config setup which is done in integration tests."
    )
    async def test_check_previously_seen_message_jsonapi_no_matches(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
    ):
        """Test POST /api/v2/previously-seen-messages/check returns empty matches for new message.

        JSON:API action endpoint that returns check results.
        Note: Requires LLM config for embedding generation.
        """
        platform_id = previously_seen_jsonapi_community_server["platform_community_server_id"]

        request_body = {
            "data": {
                "type": "previously-seen-check",
                "attributes": {
                    "message_text": "This is a completely unique test message that has never been seen before.",
                    "platform_community_server_id": platform_id,
                    "channel_id": "test_channel_123",
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages/check", json=request_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "previously-seen-check-result"
        assert "attributes" in data["data"]

        attrs = data["data"]["attributes"]
        assert "should_auto_publish" in attrs
        assert "should_auto_request" in attrs
        assert "matches" in attrs
        assert isinstance(attrs["matches"], list)

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_check_previously_seen_message_jsonapi_invalid_type(
        self,
        previously_seen_jsonapi_auth_client,
        previously_seen_jsonapi_community_server,
    ):
        """Test POST /api/v2/previously-seen-messages/check rejects invalid resource type."""
        platform_id = previously_seen_jsonapi_community_server["platform_community_server_id"]

        request_body = {
            "data": {
                "type": "wrong-type",
                "attributes": {
                    "message_text": "Test message",
                    "platform_community_server_id": platform_id,
                    "channel_id": "test_channel",
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages/check", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_check_previously_seen_message_jsonapi_missing_guild(
        self,
        previously_seen_jsonapi_auth_client,
    ):
        """Test POST /api/v2/previously-seen-messages/check returns error for unknown guild."""
        request_body = {
            "data": {
                "type": "previously-seen-check",
                "attributes": {
                    "message_text": "Test message",
                    "platform_community_server_id": "nonexistent_guild_id",
                    "channel_id": "test_channel",
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages/check", json=request_body
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_check_previously_seen_message_jsonapi_missing_required_fields(
        self,
        previously_seen_jsonapi_auth_client,
    ):
        """Test POST /api/v2/previously-seen-messages/check returns 422 for missing fields."""
        request_body = {
            "data": {
                "type": "previously-seen-check",
                "attributes": {
                    "message_text": "Test message",
                },
            }
        }

        response = await previously_seen_jsonapi_auth_client.post(
            "/api/v2/previously-seen-messages/check", json=request_body
        )

        assert response.status_code == 422
