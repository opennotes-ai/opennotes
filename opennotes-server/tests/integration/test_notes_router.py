"""Integration tests for v2 JSON:API notes, ratings, and requests endpoints.

This module contains integration tests for the /api/v2/* endpoints that follow
the JSON:API 1.1 specification. All tests have been migrated from v1 to v2.

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.notes.schemas import HelpfulnessLevel, NoteClassification


@pytest.fixture
async def notes_test_user():
    """Create a unique test user for notes router tests to avoid conflicts"""
    return {
        "username": "notestestuser",
        "email": "notestest@example.com",
        "password": "TestPassword123!",
        "full_name": "Notes Test User",
    }


@pytest.fixture
async def notes_registered_user(notes_test_user, test_community_server):
    """Create a registered user specifically for notes tests.

    Sets a discord_id on the user to enable ownership verification for notes.
    The discord_id is used to match author_participant_id on notes.

    Also creates UserProfile, UserIdentity, and CommunityMember records
    required by the authorization middleware (task-713).
    """
    from datetime import UTC, datetime

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=notes_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == notes_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = "notes_test_discord_id_123"

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
                community_id=test_community_server["uuid"],
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
async def notes_auth_headers(notes_registered_user):
    """Generate auth headers for notes test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(notes_registered_user["id"]),
        "username": notes_registered_user["username"],
        "role": notes_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def auth_client(notes_auth_headers):
    """Auth client using notes-specific test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(notes_auth_headers)
        yield client


@pytest.fixture
async def test_community_server():
    """Create a test community server for use in tests.

    Returns the platform_community_server_id (Discord guild ID) which is what the API expects.
    The API uses platform_community_server_id to look up the CommunityServer.
    """
    from uuid import uuid4

    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = "test_guild_notes"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Notes",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
def sample_note_data(test_community_server, notes_registered_user):
    return {
        "classification": NoteClassification.NOT_MISLEADING,
        "summary": "This is a test note summary",
        "author_participant_id": notes_registered_user["discord_id"],
        "community_server_id": str(test_community_server["uuid"]),
    }


def _create_note_jsonapi_body(note_data: dict) -> dict:
    """Create a JSON:API request body for note creation."""
    attrs = {
        "summary": note_data["summary"],
        "author_participant_id": note_data["author_participant_id"],
    }
    if "community_server_id" in note_data:
        attrs["community_server_id"] = note_data["community_server_id"]
    if "classification" in note_data:
        classification = note_data["classification"]
        attrs["classification"] = (
            classification.value if hasattr(classification, "value") else classification
        )
    if "request_id" in note_data:
        attrs["request_id"] = note_data["request_id"]
    return {"data": {"type": "notes", "attributes": attrs}}


def _create_rating_jsonapi_body(rating_data: dict) -> dict:
    """Create a JSON:API request body for rating creation."""
    helpfulness = rating_data["helpfulness_level"]
    return {
        "data": {
            "type": "ratings",
            "attributes": {
                "note_id": rating_data["note_id"],
                "rater_participant_id": rating_data["rater_participant_id"],
                "helpfulness_level": (
                    helpfulness.value if hasattr(helpfulness, "value") else helpfulness
                ),
            },
        }
    }


def _create_request_jsonapi_body(request_data: dict) -> dict:
    """Create a JSON:API request body for request creation."""
    attrs = {
        "request_id": request_data["request_id"],
        "requested_by": request_data["requested_by"],
        "community_server_id": request_data["community_server_id"],
    }
    if "original_message_content" in request_data:
        attrs["original_message_content"] = request_data["original_message_content"]
    if "platform_message_id" in request_data and request_data["platform_message_id"] is not None:
        attrs["platform_message_id"] = request_data["platform_message_id"]
    if "platform_channel_id" in request_data and request_data["platform_channel_id"] is not None:
        attrs["platform_channel_id"] = request_data["platform_channel_id"]
    if "platform_author_id" in request_data and request_data["platform_author_id"] is not None:
        attrs["platform_author_id"] = request_data["platform_author_id"]
    if "platform_timestamp" in request_data and request_data["platform_timestamp"] is not None:
        attrs["platform_timestamp"] = request_data["platform_timestamp"]
    if "metadata" in request_data:
        attrs["metadata"] = request_data["metadata"]
    return {"data": {"type": "requests", "attributes": attrs}}


class TestNotesRouter:
    """Tests for the JSON:API v2 notes endpoint."""

    def _get_unique_note_data(self, sample_note_data):
        return sample_note_data.copy()

    @pytest.mark.asyncio
    async def test_create_note(self, auth_client, sample_note_data):
        """Test POST /api/v2/notes creates a note with JSON:API format."""
        body = _create_note_jsonapi_body(sample_note_data)
        response = await auth_client.post("/api/v2/notes", json=body)

        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "notes"
        assert "id" in data["data"]
        assert data["data"]["attributes"]["summary"] == sample_note_data["summary"]

    @pytest.mark.asyncio
    async def test_create_duplicate_note(
        self, auth_client, sample_note_data, test_community_server
    ):
        """Test POST /api/v2/notes returns 409 for duplicate note with same request_id and author."""
        request_data = {
            "request_id": "duplicate_test_request_1",
            "requested_by": "test_requester",
            "original_message_content": "Test message for duplicate note test",
            "community_server_id": test_community_server["platform_community_server_id"],
        }
        request_body = _create_request_jsonapi_body(request_data)
        await auth_client.post("/api/v2/requests", json=request_body)

        note_data = sample_note_data.copy()
        note_data["request_id"] = "duplicate_test_request_1"
        body = _create_note_jsonapi_body(note_data)
        first_response = await auth_client.post("/api/v2/notes", json=body)
        assert first_response.status_code == 201

        response = await auth_client.post("/api/v2/notes", json=body)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_notes(self, auth_client, sample_note_data, test_community_server):
        """Test GET /api/v2/notes returns JSON:API format with proper structure."""
        body = _create_note_jsonapi_body(sample_note_data)
        await auth_client.post("/api/v2/notes", json=body)

        response = await auth_client.get(
            f"/api/v2/notes?filter[community_server_id]={test_community_server['uuid']}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "meta" in data
        assert "count" in data["meta"]
        assert "links" in data

    @pytest.mark.asyncio
    async def test_list_notes_pagination(
        self, auth_client, sample_note_data, test_community_server
    ):
        """Test GET /api/v2/notes with JSON:API pagination parameters."""
        for i in range(5):
            note_data = sample_note_data.copy()
            note_data["summary"] = f"Pagination test note {i}"
            body = _create_note_jsonapi_body(note_data)
            await auth_client.post("/api/v2/notes", json=body)

        response = await auth_client.get(
            f"/api/v2/notes?page[number]=1&page[size]=2"
            f"&filter[community_server_id]={test_community_server['uuid']}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 2

    @pytest.mark.asyncio
    async def test_get_note_by_id(self, auth_client, sample_note_data):
        """Test GET /api/v2/notes/{id} returns JSON:API format."""
        note_data = self._get_unique_note_data(sample_note_data)
        body = _create_note_jsonapi_body(note_data)
        create_response = await auth_client.post("/api/v2/notes", json=body)
        note_id = create_response.json()["data"]["id"]

        response = await auth_client.get(f"/api/v2/notes/{note_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == note_id
        assert data["data"]["type"] == "notes"

    @pytest.mark.asyncio
    async def test_get_nonexistent_note(self, auth_client, test_community_server):
        """Test GET /api/v2/notes/{id} returns 404 for non-existent note."""
        from uuid import uuid4

        fake_uuid = str(uuid4())
        response = await auth_client.get(f"/api/v2/notes/{fake_uuid}")
        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_update_note(self, auth_client, sample_note_data):
        """Test PATCH /api/v2/notes/{id} updates note with JSON:API format."""
        note_data = self._get_unique_note_data(sample_note_data)
        body = _create_note_jsonapi_body(note_data)
        create_response = await auth_client.post("/api/v2/notes", json=body)
        note_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "notes",
                "id": note_id,
                "attributes": {"summary": "Updated summary"},
            }
        }

        response = await auth_client.patch(f"/api/v2/notes/{note_id}", json=update_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["summary"] == "Updated summary"

    @pytest.mark.asyncio
    async def test_delete_note(self, auth_client, sample_note_data):
        """Test DELETE /api/v2/notes/{id} deletes note."""
        note_data = self._get_unique_note_data(sample_note_data)
        body = _create_note_jsonapi_body(note_data)
        create_response = await auth_client.post("/api/v2/notes", json=body)
        note_id = create_response.json()["data"]["id"]

        response = await auth_client.delete(f"/api/v2/notes/{note_id}")
        assert response.status_code == 204

        get_response = await auth_client.get(f"/api/v2/notes/{note_id}")
        assert get_response.status_code == 404


class TestRatingsRouter:
    """Tests for the JSON:API v2 ratings endpoint."""

    @pytest.fixture
    async def created_note(self, auth_client, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = f"Rating test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        body = _create_note_jsonapi_body(note_data)
        response = await auth_client.post("/api/v2/notes", json=body)
        return response.json()["data"]

    @pytest.mark.asyncio
    async def test_create_rating(self, auth_client, created_note):
        """Test POST /api/v2/ratings creates a rating with JSON:API format."""
        rating_data = {
            "note_id": created_note["id"],
            "rater_participant_id": "rater_456",
            "helpfulness_level": HelpfulnessLevel.HELPFUL,
        }

        body = _create_rating_jsonapi_body(rating_data)
        response = await auth_client.post("/api/v2/ratings", json=body)
        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "ratings"
        assert data["data"]["attributes"]["note_id"] == rating_data["note_id"]
        assert (
            data["data"]["attributes"]["rater_participant_id"]
            == rating_data["rater_participant_id"]
        )

    @pytest.mark.asyncio
    async def test_list_ratings(self, auth_client, created_note):
        """Test GET /api/v2/notes/{id}/ratings returns JSON:API format."""
        rating_data = {
            "note_id": created_note["id"],
            "rater_participant_id": "rater_789",
            "helpfulness_level": HelpfulnessLevel.HELPFUL,
        }
        body = _create_rating_jsonapi_body(rating_data)
        await auth_client.post("/api/v2/ratings", json=body)

        response = await auth_client.get(f"/api/v2/notes/{created_note['id']}/ratings")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_get_rating_by_id(self, auth_client, created_note):
        """Test GET /api/v2/notes/{id}/ratings includes created rating."""
        rating_data = {
            "note_id": created_note["id"],
            "rater_participant_id": "rater_get",
            "helpfulness_level": HelpfulnessLevel.HELPFUL,
        }
        body = _create_rating_jsonapi_body(rating_data)
        create_response = await auth_client.post("/api/v2/ratings", json=body)
        rating_id = create_response.json()["data"]["id"]

        response = await auth_client.get(f"/api/v2/notes/{created_note['id']}/ratings")
        assert response.status_code == 200
        data = response.json()
        ratings = data["data"]
        assert any(r["id"] == rating_id for r in ratings)

    @pytest.mark.asyncio
    async def test_update_rating(self, auth_client, created_note, notes_registered_user):
        """Test PUT /api/v2/ratings/{id} updates rating with JSON:API format."""
        rating_data = {
            "note_id": created_note["id"],
            "rater_participant_id": notes_registered_user["discord_id"],
            "helpfulness_level": HelpfulnessLevel.HELPFUL,
        }
        body = _create_rating_jsonapi_body(rating_data)
        create_response = await auth_client.post("/api/v2/ratings", json=body)
        rating_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "ratings",
                "id": rating_id,
                "attributes": {"helpfulness_level": HelpfulnessLevel.NOT_HELPFUL.value},
            }
        }

        response = await auth_client.put(f"/api/v2/ratings/{rating_id}", json=update_body)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["helpfulness_level"] == HelpfulnessLevel.NOT_HELPFUL.value


class TestRequestsRouter:
    """Tests for the JSON:API v2 requests endpoint."""

    @pytest.mark.asyncio
    async def test_create_request(self, auth_client, test_community_server):
        """Test POST /api/v2/requests creates a request with JSON:API format."""
        request_data = {
            "request_id": "req_123",
            "requested_by": "requester_456",
            "original_message_content": "Test message",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "requests"
        assert data["data"]["attributes"]["request_id"] == request_data["request_id"]

    @pytest.mark.asyncio
    async def test_list_requests(self, auth_client, test_community_server):
        """Test GET /api/v2/requests returns JSON:API format."""
        request_data = {
            "request_id": "req_list_test",
            "requested_by": "requester_789",
            "original_message_content": "Test message",
            "community_server_id": test_community_server["platform_community_server_id"],
        }
        body = _create_request_jsonapi_body(request_data)
        await auth_client.post("/api/v2/requests", json=body)

        response = await auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={test_community_server['uuid']}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_get_request_by_id(self, auth_client, test_community_server):
        """Test GET /api/v2/requests/{id} returns JSON:API format."""
        request_data = {
            "request_id": "req_get_test",
            "requested_by": "requester_get",
            "original_message_content": "Test message",
            "community_server_id": test_community_server["platform_community_server_id"],
        }
        body = _create_request_jsonapi_body(request_data)
        create_response = await auth_client.post("/api/v2/requests", json=body)
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        response = await auth_client.get(f"/api/v2/requests/{request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["request_id"] == request_id

    @pytest.mark.asyncio
    async def test_update_request(self, auth_client, test_community_server, notes_registered_user):
        """Test PATCH /api/v2/requests/{id} updates request with JSON:API format."""
        request_data = {
            "request_id": "req_update_test",
            "requested_by": notes_registered_user["discord_id"],
            "original_message_content": "Test message",
            "community_server_id": test_community_server["platform_community_server_id"],
        }
        body = _create_request_jsonapi_body(request_data)
        create_response = await auth_client.post("/api/v2/requests", json=body)
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        update_body = {
            "data": {
                "type": "requests",
                "id": request_id,
                "attributes": {"status": "COMPLETED"},
            }
        }

        response = await auth_client.patch(f"/api/v2/requests/{request_id}", json=update_body)
        assert response.status_code == 200


class TestRequestsWithMessageArchive:
    """Tests for request creation with message archive via JSON:API v2."""

    @pytest.mark.asyncio
    async def test_create_request_with_message_content(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with message content."""
        request_data = {
            "request_id": "req_archive_1",
            "requested_by": "archive_requester_1",
            "original_message_content": "This is a test message content",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["request_id"] == request_data["request_id"]
        assert data["data"]["attributes"]["content"] == "This is a test message content"

    @pytest.mark.asyncio
    async def test_create_request_with_discord_metadata(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with Discord metadata."""
        request_data = {
            "request_id": "req_archive_discord_1",
            "requested_by": "archive_requester_2",
            "original_message_content": "Discord message content",
            "platform_message_id": "discord_msg_12345",
            "platform_channel_id": "channel_67890",
            "platform_author_id": "author_11111",
            "platform_timestamp": "2025-01-15T10:00:00Z",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["request_id"] == request_data["request_id"]
        assert data["data"]["attributes"]["content"] == "Discord message content"

    @pytest.mark.asyncio
    async def test_create_request_without_message_content(self, auth_client, test_community_server):
        """Test POST /api/v2/requests without message content returns 400."""
        request_data = {
            "request_id": "req_no_content_1",
            "requested_by": "archive_requester_3",
            "original_message_content": "",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_request_returns_content_field(self, auth_client, test_community_server):
        """Test GET /api/v2/requests/{id} includes content field."""
        request_data = {
            "request_id": "req_get_content_1",
            "requested_by": "archive_requester_4",
            "original_message_content": "Content for get request test",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        create_response = await auth_client.post("/api/v2/requests", json=body)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        get_response = await auth_client.get(f"/api/v2/requests/{request_id}")
        assert get_response.status_code == 200

        data = get_response.json()
        assert data["data"]["attributes"]["content"] == "Content for get request test"

    @pytest.mark.asyncio
    async def test_list_requests_returns_content_field(self, auth_client, test_community_server):
        """Test GET /api/v2/requests list includes content field."""
        request_data = {
            "request_id": "req_list_content_1",
            "requested_by": "archive_requester_5",
            "original_message_content": "Content for list request test",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        await auth_client.post("/api/v2/requests", json=body)

        response = await auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={test_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        matching_request = next(
            (r for r in data["data"] if r["attributes"]["request_id"] == "req_list_content_1"),
            None,
        )
        assert matching_request is not None
        assert matching_request["attributes"]["content"] == "Content for list request test"

    @pytest.mark.asyncio
    async def test_update_request_preserves_content(
        self, auth_client, test_community_server, notes_registered_user
    ):
        """Test PATCH /api/v2/requests/{id} preserves content."""
        request_data = {
            "request_id": "req_update_preserve_1",
            "requested_by": notes_registered_user["discord_id"],
            "original_message_content": "Content that should be preserved",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        create_response = await auth_client.post("/api/v2/requests", json=body)
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        update_body = {
            "data": {
                "type": "requests",
                "id": request_id,
                "attributes": {"status": "IN_PROGRESS"},
            }
        }
        update_response = await auth_client.patch(
            f"/api/v2/requests/{request_id}", json=update_body
        )
        assert update_response.status_code == 200

        data = update_response.json()
        assert data["data"]["attributes"]["status"] == "IN_PROGRESS"
        assert data["data"]["attributes"]["content"] == "Content that should be preserved"

    @pytest.mark.asyncio
    async def test_request_with_empty_content(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with empty content returns 400."""
        request_data = {
            "request_id": "req_empty_content_1",
            "requested_by": "archive_requester_7",
            "original_message_content": "",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_request_with_long_content(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with long content."""
        long_content = "A" * 15000
        request_data = {
            "request_id": "req_long_content_1",
            "requested_by": "archive_requester_8",
            "original_message_content": long_content,
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["content"] == long_content
        assert len(data["data"]["attributes"]["content"]) == 15000

    @pytest.mark.asyncio
    async def test_request_with_special_characters(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with special characters."""
        special_content = "Test with emojis and special chars: <>&\"'"
        request_data = {
            "request_id": "req_special_chars_1",
            "requested_by": "archive_requester_9",
            "original_message_content": special_content,
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["content"] == special_content

    @pytest.mark.asyncio
    async def test_request_with_null_discord_metadata(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with null Discord metadata."""
        request_data = {
            "request_id": "req_null_discord_1",
            "requested_by": "archive_requester_10",
            "original_message_content": "Content without Discord metadata",
            "platform_message_id": None,
            "platform_channel_id": None,
            "platform_author_id": None,
            "platform_timestamp": None,
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["content"] == "Content without Discord metadata"

    @pytest.mark.asyncio
    async def test_create_request_with_metadata(self, auth_client, test_community_server):
        """Test POST /api/v2/requests with structured metadata."""
        request_data = {
            "request_id": "req_with_metadata_1",
            "requested_by": "system-factcheck",
            "original_message_content": "Test message with fact-check match",
            "metadata": {
                "fact_check": {
                    "dataset_item_id": "fc-item-123",
                    "similarity_score": 0.92,
                    "dataset_name": "snopes",
                    "rating": "FALSE",
                },
                "source": "automated_monitor",
            },
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["request_id"] == request_data["request_id"]
        assert data["data"]["attributes"]["content"] == "Test message with fact-check match"
        assert "metadata" in data["data"]["attributes"]
        assert data["data"]["attributes"]["metadata"] == request_data["metadata"]
        assert (
            data["data"]["attributes"]["metadata"]["fact_check"]["dataset_item_id"] == "fc-item-123"
        )
        assert data["data"]["attributes"]["metadata"]["fact_check"]["similarity_score"] == 0.92

    @pytest.mark.asyncio
    async def test_get_request_returns_metadata(self, auth_client, test_community_server):
        """Test GET /api/v2/requests/{id} includes metadata."""
        request_data = {
            "request_id": "req_get_metadata_1",
            "requested_by": "system-factcheck",
            "original_message_content": "Another test message",
            "metadata": {
                "fact_check": {
                    "dataset_item_id": "fc-item-456",
                    "similarity_score": 0.85,
                    "dataset_name": "politifact",
                    "rating": "MOSTLY_FALSE",
                },
            },
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        create_response = await auth_client.post("/api/v2/requests", json=body)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        get_response = await auth_client.get(f"/api/v2/requests/{request_id}")
        assert get_response.status_code == 200

        data = get_response.json()
        assert data["data"]["attributes"]["metadata"] == request_data["metadata"]
        assert (
            data["data"]["attributes"]["metadata"]["fact_check"]["dataset_item_id"] == "fc-item-456"
        )

    @pytest.mark.asyncio
    async def test_list_requests_includes_metadata(self, auth_client, test_community_server):
        """Test GET /api/v2/requests list includes metadata for each request."""
        request_data = {
            "request_id": "req_list_metadata_1",
            "requested_by": "system-factcheck",
            "original_message_content": "List test message",
            "metadata": {
                "fact_check": {
                    "dataset_item_id": "fc-item-789",
                    "similarity_score": 0.95,
                    "dataset_name": "snopes",
                    "rating": "TRUE",
                },
            },
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        await auth_client.post("/api/v2/requests", json=body)

        response = await auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={test_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        matching_request = next(
            (r for r in data["data"] if r["attributes"]["request_id"] == "req_list_metadata_1"),
            None,
        )
        assert matching_request is not None
        assert "metadata" in matching_request["attributes"]
        assert matching_request["attributes"]["metadata"] == request_data["metadata"]

    @pytest.mark.asyncio
    async def test_create_request_without_metadata(self, auth_client, test_community_server):
        """Test POST /api/v2/requests without metadata (should default to empty dict or None)."""
        request_data = {
            "request_id": "req_no_metadata_1",
            "requested_by": "manual-requester",
            "original_message_content": "Manual request without metadata",
            "community_server_id": test_community_server["platform_community_server_id"],
        }

        body = _create_request_jsonapi_body(request_data)
        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 201

        data = response.json()
        assert data["data"]["attributes"]["request_id"] == request_data["request_id"]
        assert (
            data["data"]["attributes"]["metadata"] is None
            or data["data"]["attributes"]["metadata"] == {}
        )


class TestRequestsViaAPI:
    """Tests for request creation via v2 JSON:API with message archive."""

    @pytest.mark.asyncio
    async def test_create_request_via_api(self, auth_client, test_community_server):
        """Test request creation via v2 endpoint creates message archive."""
        request_body = _create_request_jsonapi_body(
            {
                "request_id": "api_req_1",
                "requested_by": "api_requester",
                "original_message_content": "API created content",
                "community_server_id": test_community_server["platform_community_server_id"],
            }
        )

        response = await auth_client.post("/api/v2/requests", json=request_body)
        assert response.status_code == 201

        get_response = await auth_client.get("/api/v2/requests/api_req_1")
        assert get_response.status_code == 200

        data = get_response.json()
        assert data["data"]["attributes"]["request_id"] == "api_req_1"
        assert data["data"]["attributes"]["content"] == "API created content"

    @pytest.mark.asyncio
    async def test_list_requests_returns_content(self, auth_client, test_community_server):
        """Test that requests list includes content from message archive."""
        request_body = _create_request_jsonapi_body(
            {
                "request_id": "list_content_req_1",
                "requested_by": "list_requester",
                "original_message_content": "Content for list test",
                "community_server_id": test_community_server["platform_community_server_id"],
            }
        )
        await auth_client.post("/api/v2/requests", json=request_body)

        response = await auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={test_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        matching_request = next(
            (r for r in data["data"] if r["attributes"]["request_id"] == "list_content_req_1"), None
        )
        assert matching_request is not None
        assert matching_request["attributes"]["content"] == "Content for list test"


class TestMessageArchiveRelationship:
    """Tests for message archive relationship via database.

    These tests verify internal DB relationships using v2 JSON:API to create data
    and then checking DB state directly.
    """

    @pytest.mark.asyncio
    async def test_request_links_to_message_archive(self, auth_client, test_community_server):
        """Test that request links to message archive in database."""
        from sqlalchemy import select

        from src.database import async_session_maker
        from src.notes.models import Request

        request_body = _create_request_jsonapi_body(
            {
                "request_id": "req_archive_link_1",
                "requested_by": "archive_link_requester",
                "original_message_content": "Content with archive link",
                "community_server_id": test_community_server["platform_community_server_id"],
            }
        )

        response = await auth_client.post("/api/v2/requests", json=request_body)
        assert response.status_code == 201

        async with async_session_maker() as db:
            stmt = select(Request).where(Request.request_id == "req_archive_link_1")
            result = await db.execute(stmt)
            request = result.scalar_one()

            assert request.message_archive_id is not None
            assert request.message_archive is not None
            assert request.message_archive.content_text == "Content with archive link"

    @pytest.mark.asyncio
    async def test_message_archive_stores_discord_metadata(
        self, auth_client, test_community_server
    ):
        """Test that message archive stores Discord metadata."""
        from sqlalchemy import select

        from src.database import async_session_maker
        from src.notes.models import Request

        request_body = _create_request_jsonapi_body(
            {
                "request_id": "req_discord_meta_1",
                "requested_by": "discord_meta_requester",
                "original_message_content": "Discord metadata test",
                "platform_message_id": "msg_meta_123",
                "platform_channel_id": "channel_meta_456",
                "platform_author_id": "author_meta_789",
                "community_server_id": test_community_server["platform_community_server_id"],
            }
        )

        response = await auth_client.post("/api/v2/requests", json=request_body)
        assert response.status_code == 201

        async with async_session_maker() as db:
            stmt = select(Request).where(Request.request_id == "req_discord_meta_1")
            result = await db.execute(stmt)
            request = result.scalar_one()

            assert request.message_archive.platform_message_id == "msg_meta_123"
            assert request.message_archive.platform_channel_id == "channel_meta_456"
            assert request.message_archive.platform_author_id == "author_meta_789"

    @pytest.mark.asyncio
    async def test_request_content_property_returns_archive_content(
        self, auth_client, test_community_server
    ):
        """Test that request content property returns archive content."""
        from sqlalchemy import select

        from src.database import async_session_maker
        from src.notes.models import Request

        request_body = _create_request_jsonapi_body(
            {
                "request_id": "req_content_property_1",
                "requested_by": "content_property_requester",
                "original_message_content": "Content via property test",
                "community_server_id": test_community_server["platform_community_server_id"],
            }
        )

        response = await auth_client.post("/api/v2/requests", json=request_body)
        assert response.status_code == 201

        async with async_session_maker() as db:
            stmt = select(Request).where(Request.request_id == "req_content_property_1")
            result = await db.execute(stmt)
            request = result.scalar_one()

            content_via_property = request.content
            assert content_via_property == "Content via property test"

    @pytest.mark.asyncio
    async def test_request_content_property_returns_none_without_archive(
        self, auth_client, test_community_server
    ):
        """Test that request content property returns None when no message archive exists."""
        from sqlalchemy import select

        from src.database import async_session_maker
        from src.notes.models import Request

        async with async_session_maker() as db:
            request_without_archive = Request(
                request_id="req_no_archive_1",
                requested_by="no_archive_requester",
                message_archive_id=None,
                community_server_id=test_community_server["uuid"],
            )
            db.add(request_without_archive)
            await db.commit()

        async with async_session_maker() as db:
            stmt = select(Request).where(Request.request_id == "req_no_archive_1")
            result = await db.execute(stmt)
            request = result.scalar_one()

            content_via_property = request.content
            assert content_via_property is None


class TestDataIntegrity:
    """Tests for data integrity constraints (task-555) via JSON:API v2."""

    @pytest.mark.asyncio
    async def test_create_note_without_community_server_id_returns_422(
        self, auth_client, sample_note_data
    ):
        """Test that creating a note without community_server_id returns 422 validation error."""
        note_data = sample_note_data.copy()
        note_data.pop("community_server_id", None)

        body = _create_note_jsonapi_body(note_data)
        response = await auth_client.post("/api/v2/notes", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_note_with_community_server_id_succeeds(
        self, auth_client, sample_note_data
    ):
        """Test that creating a note with community_server_id succeeds."""
        from uuid import uuid4

        from src.database import async_session_maker
        from src.llm_config.models import CommunityServer

        community_server_id = uuid4()
        async with async_session_maker() as db:
            community_server = CommunityServer(
                id=community_server_id,
                platform="discord",
                platform_community_server_id="test_guild_555",
                name="Test Guild 555",
            )
            db.add(community_server)
            await db.commit()

        note_data = sample_note_data.copy()
        note_data["community_server_id"] = str(community_server_id)

        body = _create_note_jsonapi_body(note_data)
        response = await auth_client.post("/api/v2/notes", json=body)
        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "notes"
        assert "id" in data["data"]

    @pytest.mark.asyncio
    async def test_create_request_without_community_server_id_returns_422(
        self, auth_client, test_community_server
    ):
        """Test that creating a request without community_server_id returns 422 validation error."""
        body = {
            "data": {
                "type": "requests",
                "attributes": {
                    "request_id": "req_no_community_555",
                    "requested_by": "test_requester_555",
                    "original_message_content": "Test content",
                },
            }
        }

        response = await auth_client.post("/api/v2/requests", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_note_with_mismatched_community_server_id_fails(
        self, auth_client, sample_note_data
    ):
        """Test that creating a note with mismatched community_server_id fails."""
        from src.database import async_session_maker
        from src.llm_config.models import CommunityServer

        # Use snowflake-like IDs for platform_community_server_id
        platform_id_1 = "738146839441965001"
        platform_id_2 = "738146839441965002"
        async with async_session_maker() as db:
            community_server_1 = CommunityServer(
                platform="discord",
                platform_community_server_id=platform_id_1,
                name="Test Guild 555 1",
            )
            community_server_2 = CommunityServer(
                platform="discord",
                platform_community_server_id=platform_id_2,
                name="Test Guild 555 2",
            )
            db.add(community_server_1)
            db.add(community_server_2)
            await db.commit()

        request_body = _create_request_jsonapi_body(
            {
                "request_id": "req_mismatch_555",
                "requested_by": "test_requester_555",
                "original_message_content": "Test content",
                # Pass platform_community_server_id, not internal UUID
                "community_server_id": platform_id_1,
            }
        )
        request_response = await auth_client.post("/api/v2/requests", json=request_body)
        assert request_response.status_code == 201

        note_data = sample_note_data.copy()
        note_data["request_id"] = "req_mismatch_555"
        # Pass different platform_community_server_id to test mismatch validation
        note_data["community_server_id"] = platform_id_2

        body = _create_note_jsonapi_body(note_data)
        response = await auth_client.post("/api/v2/notes", json=body)
        # 400 = Bad Request, 422 = Unprocessable Entity - both indicate validation failure
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"


class TestNotesFilterParameters:
    """Tests for rated_by_participant_id and exclude_status filter parameters via JSON:API v2 (task-778)."""

    @pytest.fixture
    async def notes_with_ratings(self, auth_client, sample_note_data, test_community_server):
        """Create notes with various ratings for testing filter functionality."""
        notes = []

        for i in range(5):
            note_data = sample_note_data.copy()
            note_data["summary"] = f"Filter test note {i}"
            body = _create_note_jsonapi_body(note_data)
            response = await auth_client.post("/api/v2/notes", json=body)
            assert response.status_code == 201
            notes.append(response.json()["data"])

        rater_a = "rater_participant_a"
        rater_b = "rater_participant_b"

        rating_body_0 = _create_rating_jsonapi_body(
            {
                "note_id": notes[0]["id"],
                "rater_participant_id": rater_a,
                "helpfulness_level": HelpfulnessLevel.HELPFUL,
            }
        )
        rating_response_0 = await auth_client.post("/api/v2/ratings", json=rating_body_0)
        assert rating_response_0.status_code == 201, f"Rating 0 failed: {rating_response_0.text}"

        rating_body_1 = _create_rating_jsonapi_body(
            {
                "note_id": notes[1]["id"],
                "rater_participant_id": rater_a,
                "helpfulness_level": HelpfulnessLevel.NOT_HELPFUL,
            }
        )
        rating_response_1 = await auth_client.post("/api/v2/ratings", json=rating_body_1)
        assert rating_response_1.status_code == 201, f"Rating 1 failed: {rating_response_1.text}"

        rating_body_2 = _create_rating_jsonapi_body(
            {
                "note_id": notes[2]["id"],
                "rater_participant_id": rater_b,
                "helpfulness_level": HelpfulnessLevel.HELPFUL,
            }
        )
        rating_response_2 = await auth_client.post("/api/v2/ratings", json=rating_body_2)
        assert rating_response_2.status_code == 201, f"Rating 2 failed: {rating_response_2.text}"

        return {
            "notes": notes,
            "rater_a": rater_a,
            "rater_b": rater_b,
            "community_server_id": test_community_server["uuid"],
        }

    @pytest.mark.asyncio
    async def test_filter_by_rated_by_participant_id_not_in(self, auth_client, notes_with_ratings):
        """Test filter[rated_by_participant_id__not_in] excludes notes rated by specified participant."""
        rater_a = notes_with_ratings["rater_a"]
        community_id = notes_with_ratings["community_server_id"]

        response = await auth_client.get(
            f"/api/v2/notes?filter[rated_by_participant_id__not_in]={rater_a}"
            f"&filter[community_server_id]={community_id}"
        )
        assert response.status_code == 200

        data = response.json()
        note_ids = [note["id"] for note in data["data"]]
        assert notes_with_ratings["notes"][0]["id"] not in note_ids
        assert notes_with_ratings["notes"][1]["id"] not in note_ids
        assert notes_with_ratings["notes"][2]["id"] in note_ids
        assert notes_with_ratings["notes"][3]["id"] in note_ids
        assert notes_with_ratings["notes"][4]["id"] in note_ids

    @pytest.mark.asyncio
    async def test_filter_by_rated_by_participant_id_not_in_no_ratings(
        self, auth_client, notes_with_ratings
    ):
        """Test filter[rated_by_participant_id__not_in] returns all when participant has no ratings."""
        nonexistent_rater = "rater_that_does_not_exist"
        community_id = notes_with_ratings["community_server_id"]

        response = await auth_client.get(
            f"/api/v2/notes?filter[rated_by_participant_id__not_in]={nonexistent_rater}"
            f"&filter[community_server_id]={community_id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) == 5

    @pytest.mark.asyncio
    async def test_exclude_status_filter(self, auth_client, notes_with_ratings):
        """Test filter[status__neq] properly excludes notes with specified status."""
        community_id = notes_with_ratings["community_server_id"]

        response = await auth_client.get(
            f"/api/v2/notes?filter[status__neq]=CURRENTLY_RATED_HELPFUL"
            f"&filter[community_server_id]={community_id}"
        )
        assert response.status_code == 200

        data = response.json()
        for note in data["data"]:
            assert note["attributes"]["status"] != "CURRENTLY_RATED_HELPFUL"

    @pytest.mark.asyncio
    async def test_combine_rated_by_and_exclude_status(
        self, auth_client, sample_note_data, test_community_server
    ):
        """Test combination of filter[rated_by_participant_id__not_in] and filter[status__neq]."""
        notes = []

        for i in range(3):
            note_data = sample_note_data.copy()
            note_data["summary"] = f"Combined filter test note {i}"
            body = _create_note_jsonapi_body(note_data)
            response = await auth_client.post("/api/v2/notes", json=body)
            assert response.status_code == 201
            notes.append(response.json()["data"])

        rater_a = "combined_test_rater_a"

        rating_body_0 = _create_rating_jsonapi_body(
            {
                "note_id": notes[0]["id"],
                "rater_participant_id": rater_a,
                "helpfulness_level": HelpfulnessLevel.NOT_HELPFUL,
            }
        )
        rating_0 = await auth_client.post("/api/v2/ratings", json=rating_body_0)
        assert rating_0.status_code == 201

        rating_body_1 = _create_rating_jsonapi_body(
            {
                "note_id": notes[1]["id"],
                "rater_participant_id": rater_a,
                "helpfulness_level": HelpfulnessLevel.HELPFUL,
            }
        )
        rating_1 = await auth_client.post("/api/v2/ratings", json=rating_body_1)
        assert rating_1.status_code == 201

        community_id = test_community_server["uuid"]

        response = await auth_client.get(
            f"/api/v2/notes?filter[rated_by_participant_id__not_in]={rater_a}"
            f"&filter[status__neq]=CURRENTLY_RATED_HELPFUL"
            f"&filter[community_server_id]={community_id}"
        )
        assert response.status_code == 200

        data = response.json()
        note_ids = [note["id"] for note in data["data"]]
        assert notes[2]["id"] in note_ids
        assert notes[0]["id"] not in note_ids
        assert notes[1]["id"] not in note_ids

    @pytest.mark.asyncio
    async def test_rated_by_participant_id_not_in_with_pagination(
        self, auth_client, sample_note_data, test_community_server
    ):
        """Test filter[rated_by_participant_id__not_in] with JSON:API pagination."""
        rater = "pagination_test_rater"
        notes = []
        for i in range(5):
            note_data = sample_note_data.copy()
            note_data["summary"] = f"Pagination filter test note {i}"
            body = _create_note_jsonapi_body(note_data)
            response = await auth_client.post("/api/v2/notes", json=body)
            assert response.status_code == 201
            notes.append(response.json()["data"])
            rating_body = _create_rating_jsonapi_body(
                {
                    "note_id": notes[-1]["id"],
                    "rater_participant_id": rater,
                    "helpfulness_level": HelpfulnessLevel.HELPFUL,
                }
            )
            await auth_client.post("/api/v2/ratings", json=rating_body)

        community_id = test_community_server["uuid"]

        response = await auth_client.get(
            f"/api/v2/notes?filter[rated_by_participant_id__not_in]={rater}"
            f"&page[number]=1&page[size]=2"
            f"&filter[community_server_id]={community_id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["meta"]["count"] == 0
