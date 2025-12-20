"""Tests for JSON:API v2 notes endpoint.

This module contains integration tests for the /api/v2/notes endpoint that follows
the JSON:API 1.0 specification. These tests verify:
- Proper JSON:API response envelope structure
- Filtering capabilities
- Pagination support
- Relationship data inclusion

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.notes.schemas import NoteClassification


@pytest.fixture
async def jsonapi_test_user():
    """Create a unique test user for JSON:API tests to avoid conflicts"""
    return {
        "username": "jsonapitestuser",
        "email": "jsonapitest@example.com",
        "password": "TestPassword123!",
        "full_name": "JSONAPI Test User",
    }


@pytest.fixture
async def jsonapi_registered_user(jsonapi_test_user, jsonapi_community_server):
    """Create a registered user for JSON:API tests.

    Sets up all required records for community authorization.
    """
    from datetime import UTC, datetime

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = "jsonapi_test_discord_id_123"

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
                community_id=jsonapi_community_server["uuid"],
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
async def jsonapi_auth_headers(jsonapi_registered_user):
    """Generate auth headers for JSON:API test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(jsonapi_registered_user["id"]),
        "username": jsonapi_registered_user["username"],
        "role": jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def jsonapi_auth_client(jsonapi_auth_headers):
    """Auth client using JSON:API test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(jsonapi_auth_headers)
        yield client


@pytest.fixture
async def jsonapi_community_server():
    """Create a test community server for JSON:API tests."""
    from uuid import uuid4

    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = "test_guild_jsonapi"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_id=platform_id,
            name="Test Guild for JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_id": platform_id}


@pytest.fixture
def jsonapi_sample_note_data(jsonapi_community_server, jsonapi_registered_user):
    return {
        "classification": NoteClassification.NOT_MISLEADING,
        "summary": "This is a test note summary for JSON:API",
        "author_participant_id": jsonapi_registered_user["discord_id"],
        "community_server_id": str(jsonapi_community_server["uuid"]),
    }


class TestJSONAPINotesEndpoint:
    """Tests for the JSON:API v2 notes endpoint."""

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"JSONAPI test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_list_notes_jsonapi_format(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test GET /api/v2/notes returns proper JSON:API format.

        JSON:API 1.0 requires:
        - 'data' array containing resource objects
        - 'jsonapi' object with version
        - 'links' object for pagination
        - 'meta' object with count
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?filter[community_server_id]={jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

        assert "links" in data, "Response must contain 'links' key"

        assert "meta" in data, "Response must contain 'meta' key"
        assert "count" in data["meta"], "'meta' must contain 'count'"

    @pytest.mark.asyncio
    async def test_note_resource_object_structure(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test that note resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier
        - 'id': unique identifier string
        - 'attributes': object containing resource attributes
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?filter[community_server_id]={jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) > 0, "Should have at least one note"

        note_resource = data["data"][0]

        assert "type" in note_resource, "Resource must have 'type'"
        assert note_resource["type"] == "notes", "Resource type must be 'notes'"

        assert "id" in note_resource, "Resource must have 'id'"
        assert isinstance(note_resource["id"], str), "Resource id must be a string"

        assert "attributes" in note_resource, "Resource must have 'attributes'"
        attributes = note_resource["attributes"]
        assert "summary" in attributes, "Attributes must include 'summary'"
        assert "status" in attributes, "Attributes must include 'status'"
        assert "classification" in attributes, "Attributes must include 'classification'"

    @pytest.mark.asyncio
    async def test_get_single_note_jsonapi_format(
        self, jsonapi_auth_client, jsonapi_sample_note_data
    ):
        """Test GET /api/v2/notes/{id} returns single note in JSON:API format.

        For single resource, 'data' should be an object, not an array.
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await jsonapi_auth_client.get(f"/api/v2/notes/{note_id}")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object for single resource"
        assert data["data"]["id"] == note_id, "Returned note id must match requested id"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1"

    @pytest.mark.asyncio
    async def test_filter_notes_by_status(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes by status using JSON:API filter syntax.

        JSON:API filtering: filter[field]=value
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        filter_query = (
            f"filter[status]=NEEDS_MORE_RATINGS"
            f"&filter[community_server_id]={jsonapi_community_server['uuid']}"
        )
        response = await jsonapi_auth_client.get(f"/api/v2/notes?{filter_query}")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        for note in data["data"]:
            assert note["attributes"]["status"] == "NEEDS_MORE_RATINGS"

    @pytest.mark.asyncio
    async def test_pagination_with_page_params(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test pagination using JSON:API page[number] and page[size] parameters."""
        for i in range(5):
            note_data = self._get_unique_note_data(jsonapi_sample_note_data)
            note_data["summary"] = f"Pagination test note {i}"
            response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
            assert response.status_code == 201

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?page[number]=1&page[size]=2"
            f"&filter[community_server_id]={jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert len(data["data"]) <= 2, "Should return at most 2 notes per page"

        assert "meta" in data
        assert "count" in data["meta"], "Meta should contain total count"
        assert data["meta"]["count"] >= 5, "Total count should be at least 5"

        assert "links" in data
        links = data["links"]
        assert "self" in links or "first" in links, "Links should contain pagination URLs"

    @pytest.mark.asyncio
    async def test_jsonapi_content_type(self, jsonapi_auth_client, jsonapi_community_server):
        """Test that response Content-Type is application/vnd.api+json."""
        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?filter[community_server_id]={jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_note_not_found_jsonapi_error(self, jsonapi_auth_client):
        """Test that 404 errors are returned in JSON:API error format."""
        from uuid import uuid4

        fake_id = str(uuid4())
        response = await jsonapi_auth_client.get(f"/api/v2/notes/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert isinstance(data["errors"], list), "'errors' must be an array"

        error = data["errors"][0]
        assert "status" in error or "title" in error, "Error must have status or title"


class TestJSONAPIAdvancedFilters:
    """Tests for advanced filter operators using fastapi-filter.

    These tests verify the filter operators:
    - neq (not equal): filter[status__neq]=NEEDS_MORE_RATINGS
    - gte (greater than or equal): filter[created_at__gte]=2024-01-01
    - lte (less than or equal): filter[created_at__lte]=2024-12-31
    - not_in: filter[rated_by_participant_id__not_in]=user1,user2

    The primary use case is rated_by_participant_id__not_in which enables
    filtering out notes already rated by the current user (task-783).
    """

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Advanced filter test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_filter_notes_exclude_rated_by_participant(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes to exclude those already rated by a user (PRIMARY USE CASE).

        This is the main use case from task-783: showing notes that still need
        rating by the current user by filtering out already-rated notes.

        filter[rated_by_participant_id__not_in]=user1 should return only notes
        NOT rated by user1.
        """
        note_data_1 = self._get_unique_note_data(jsonapi_sample_note_data)
        note_data_1["summary"] = "Rated note for exclusion test"
        create_resp_1 = await jsonapi_auth_client.post("/api/v1/notes", json=note_data_1)
        assert create_resp_1.status_code == 201
        rated_note_id = create_resp_1.json()["id"]

        note_data_2 = self._get_unique_note_data(jsonapi_sample_note_data)
        note_data_2["summary"] = "Unrated note for exclusion test"
        create_resp_2 = await jsonapi_auth_client.post("/api/v1/notes", json=note_data_2)
        assert create_resp_2.status_code == 201
        unrated_note_id = create_resp_2.json()["id"]

        rater_id = "test_rater_for_exclusion"
        rating_data = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": rated_note_id,
                    "rater_participant_id": rater_id,
                    "helpfulness_level": "HELPFUL",
                },
            }
        }
        rating_resp = await jsonapi_auth_client.post("/api/v2/ratings", json=rating_data)
        assert rating_resp.status_code in [200, 201]

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[rated_by_participant_id__not_in]={rater_id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        returned_note_ids = [note["id"] for note in data["data"]]

        assert unrated_note_id in returned_note_ids, (
            f"Unrated note should be returned. Got IDs: {returned_note_ids}"
        )
        assert rated_note_id not in returned_note_ids, (
            f"Rated note should be excluded. Got IDs: {returned_note_ids}"
        )

    @pytest.mark.asyncio
    async def test_filter_notes_by_rated_by_participant(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes to only include those rated by a specific user.

        filter[rated_by_participant_id]=user1 should return only notes
        that have been rated by user1. This is the inverse of
        rated_by_participant_id__not_in which EXCLUDES notes.

        Use case: Discord client's listNotesRatedByUser() function needs
        to find all notes that a specific user has rated.
        """
        note_data_1 = self._get_unique_note_data(jsonapi_sample_note_data)
        note_data_1["summary"] = "Rated note for inclusion test"
        create_resp_1 = await jsonapi_auth_client.post("/api/v1/notes", json=note_data_1)
        assert create_resp_1.status_code == 201
        rated_note_id = create_resp_1.json()["id"]

        note_data_2 = self._get_unique_note_data(jsonapi_sample_note_data)
        note_data_2["summary"] = "Unrated note for inclusion test"
        create_resp_2 = await jsonapi_auth_client.post("/api/v1/notes", json=note_data_2)
        assert create_resp_2.status_code == 201
        unrated_note_id = create_resp_2.json()["id"]

        rater_id = "test_rater_for_inclusion"
        rating_data = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": rated_note_id,
                    "rater_participant_id": rater_id,
                    "helpfulness_level": "HELPFUL",
                },
            }
        }
        rating_resp = await jsonapi_auth_client.post("/api/v2/ratings", json=rating_data)
        assert rating_resp.status_code in [200, 201]

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[rated_by_participant_id]={rater_id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        returned_note_ids = [note["id"] for note in data["data"]]

        assert rated_note_id in returned_note_ids, (
            f"Rated note should be returned. Got IDs: {returned_note_ids}"
        )
        assert unrated_note_id not in returned_note_ids, (
            f"Unrated note should be excluded. Got IDs: {returned_note_ids}"
        )

    @pytest.mark.asyncio
    async def test_filter_notes_by_status_neq(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes with status not equal to a value.

        filter[status__neq]=NEEDS_MORE_RATINGS should exclude notes with that status.
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[status__neq]=NEEDS_MORE_RATINGS"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        for note in data["data"]:
            assert note["attributes"]["status"] != "NEEDS_MORE_RATINGS", (
                f"Note with status {note['attributes']['status']} should be excluded"
            )

    @pytest.mark.asyncio
    async def test_filter_notes_by_date_gte(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes created on or after a specific date.

        filter[created_at__gte]=2024-01-01T00:00:00Z should return notes created
        on or after that date.
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        filter_date = "2024-01-01T00:00:00Z"
        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[created_at__gte]={filter_date}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        from datetime import datetime as dt

        filter_datetime = dt.fromisoformat(filter_date.replace("Z", "+00:00"))

        for note in data["data"]:
            note_created = note["attributes"]["created_at"]
            if note_created:
                note_datetime = dt.fromisoformat(note_created.replace("Z", "+00:00"))
                assert note_datetime >= filter_datetime, (
                    f"Note created_at {note_created} is before filter date {filter_date}"
                )

    @pytest.mark.asyncio
    async def test_filter_notes_by_date_lte(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes created on or before a specific date.

        filter[created_at__lte]=2030-12-31T23:59:59Z should return notes created
        on or before that date (essentially all notes for this test).
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        filter_date = "2030-12-31T23:59:59Z"
        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[created_at__lte]={filter_date}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert len(data["data"]) > 0, "Should return at least one note created before 2030"

        from datetime import datetime as dt

        filter_datetime = dt.fromisoformat(filter_date.replace("Z", "+00:00"))

        for note in data["data"]:
            note_created = note["attributes"]["created_at"]
            if note_created:
                note_datetime = dt.fromisoformat(note_created.replace("Z", "+00:00"))
                assert note_datetime <= filter_datetime, (
                    f"Note created_at {note_created} is after filter date {filter_date}"
                )

    @pytest.mark.asyncio
    async def test_filter_notes_combined(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test combining multiple filter operators with AND logic.

        filter[status__neq]=CURRENTLY_RATED_NOT_HELPFUL&filter[created_at__gte]=2024-01-01
        should return notes that:
        - Have status NOT equal to CURRENTLY_RATED_NOT_HELPFUL AND
        - Were created on or after 2024-01-01
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201

        filter_date = "2024-01-01T00:00:00Z"
        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[status__neq]=CURRENTLY_RATED_NOT_HELPFUL"
            f"&filter[created_at__gte]={filter_date}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        from datetime import datetime as dt

        filter_datetime = dt.fromisoformat(filter_date.replace("Z", "+00:00"))

        for note in data["data"]:
            assert note["attributes"]["status"] != "CURRENTLY_RATED_NOT_HELPFUL", (
                "Note with CURRENTLY_RATED_NOT_HELPFUL status should be excluded"
            )
            note_created = note["attributes"]["created_at"]
            if note_created:
                note_datetime = dt.fromisoformat(note_created.replace("Z", "+00:00"))
                assert note_datetime >= filter_datetime, (
                    f"Note created_at {note_created} is before filter date {filter_date}"
                )

    @pytest.mark.asyncio
    async def test_filter_notes_by_platform_message_id(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test filtering notes by platform_message_id.

        filter[platform_message_id]=<discord_message_id> should return only notes
        whose associated request's message_archive has that platform_message_id.

        This enables the Discord client to find notes by Discord message snowflake ID.
        """
        from src.database import get_session_maker
        from src.notes.request_service import RequestService

        unique_platform_msg_id = f"discord_msg_{int(datetime.now(tz=UTC).timestamp() * 1000000)}"

        async with get_session_maker()() as session:
            request = await RequestService.create_from_message(
                db=session,
                request_id=f"req_platform_filter_{unique_platform_msg_id}",
                content="Test content for platform_message_id filter",
                community_server_id=jsonapi_community_server["uuid"],
                requested_by="test_user",
                platform_message_id=unique_platform_msg_id,
                platform_channel_id="test_channel_123",
            )
            await session.commit()
            await session.refresh(request)
            request_id = request.request_id

        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        note_data["request_id"] = request_id
        note_data["summary"] = f"Note for platform_message_id filter test {unique_platform_msg_id}"
        create_resp = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_resp.status_code == 201
        note_with_platform_id = create_resp.json()["id"]

        note_data_2 = self._get_unique_note_data(jsonapi_sample_note_data)
        note_data_2["summary"] = "Note without platform_message_id"
        create_resp_2 = await jsonapi_auth_client.post("/api/v1/notes", json=note_data_2)
        assert create_resp_2.status_code == 201
        note_without_platform_id = create_resp_2.json()["id"]

        response = await jsonapi_auth_client.get(
            f"/api/v2/notes?"
            f"filter[community_server_id]={jsonapi_community_server['uuid']}"
            f"&filter[platform_message_id]={unique_platform_msg_id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        returned_note_ids = [note["id"] for note in data["data"]]

        assert note_with_platform_id in returned_note_ids, (
            f"Note with matching platform_message_id should be returned. Got IDs: {returned_note_ids}"
        )
        assert note_without_platform_id not in returned_note_ids, (
            f"Note without matching platform_message_id should be excluded. Got IDs: {returned_note_ids}"
        )


class TestNotesWriteOperations:
    """Tests for JSON:API v2 notes write operations (POST, PATCH, DELETE).

    These tests verify:
    - POST /api/v2/notes creates a note with JSON:API request body
    - PATCH /api/v2/notes/{id} updates a note with JSON:API request body
    - DELETE /api/v2/notes/{id} deletes a note and returns 204
    """

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Write operations test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_create_note_jsonapi(
        self, jsonapi_auth_client, jsonapi_sample_note_data, jsonapi_community_server
    ):
        """Test POST /api/v2/notes creates a note with JSON:API request body.

        JSON:API 1.0 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status
        - Response body with 'data' object containing created resource
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)

        request_body = {
            "data": {
                "type": "notes",
                "attributes": {
                    "summary": note_data["summary"],
                    "classification": note_data["classification"].value,
                    "community_server_id": str(note_data["community_server_id"]),
                    "author_participant_id": note_data["author_participant_id"],
                },
            }
        }

        response = await jsonapi_auth_client.post("/api/v2/notes", json=request_body)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "notes", "Resource type must be 'notes'"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"], "Resource must have 'attributes'"
        assert data["data"]["attributes"]["summary"] == note_data["summary"]

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_note_jsonapi_invalid_type(
        self, jsonapi_auth_client, jsonapi_sample_note_data
    ):
        """Test POST /api/v2/notes rejects invalid resource type."""
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "summary": note_data["summary"],
                    "classification": note_data["classification"].value,
                    "community_server_id": str(note_data["community_server_id"]),
                    "author_participant_id": note_data["author_participant_id"],
                },
            }
        }

        response = await jsonapi_auth_client.post("/api/v2/notes", json=request_body)

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_update_note_jsonapi(self, jsonapi_auth_client, jsonapi_sample_note_data):
        """Test PATCH /api/v2/notes/{id} updates a note with JSON:API request body.

        JSON:API 1.0 requires:
        - Request body with 'data' object containing 'type', 'id', and 'attributes'
        - Response with 200 OK status
        - Response body with 'data' object containing updated resource
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        updated_summary = "Updated summary via JSON:API"
        request_body = {
            "data": {
                "type": "notes",
                "id": note_id,
                "attributes": {
                    "summary": updated_summary,
                },
            }
        }

        response = await jsonapi_auth_client.patch(f"/api/v2/notes/{note_id}", json=request_body)

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "notes"
        assert data["data"]["id"] == note_id
        assert data["data"]["attributes"]["summary"] == updated_summary

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_note_jsonapi_id_mismatch(
        self, jsonapi_auth_client, jsonapi_sample_note_data
    ):
        """Test PATCH /api/v2/notes/{id} rejects mismatched IDs."""
        from uuid import uuid4

        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        request_body = {
            "data": {
                "type": "notes",
                "id": str(uuid4()),
                "attributes": {
                    "summary": "Updated summary",
                },
            }
        }

        response = await jsonapi_auth_client.patch(f"/api/v2/notes/{note_id}", json=request_body)

        assert response.status_code == 409, f"Expected 409, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_delete_note_jsonapi(self, jsonapi_auth_client, jsonapi_sample_note_data):
        """Test DELETE /api/v2/notes/{id} deletes a note and returns 204.

        JSON:API 1.0 requires:
        - Response with 204 No Content status
        - No response body
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await jsonapi_auth_client.delete(f"/api/v2/notes/{note_id}")

        assert response.status_code == 204, f"Expected 204, got {response.status_code}"

        get_response = await jsonapi_auth_client.get(f"/api/v2/notes/{note_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_note_jsonapi_not_found(self, jsonapi_auth_client):
        """Test DELETE /api/v2/notes/{id} returns 404 for non-existent note."""
        from uuid import uuid4

        fake_id = str(uuid4())
        response = await jsonapi_auth_client.delete(f"/api/v2/notes/{fake_id}")

        assert response.status_code == 404


class TestForcePublishNote:
    """Tests for JSON:API v2 notes force-publish endpoint.

    POST /api/v2/notes/{id}/force-publish

    This endpoint allows administrators to manually publish notes that haven't
    met automatic publication thresholds. Requires admin permissions.
    """

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Force publish test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.fixture
    async def admin_user_and_headers(self, jsonapi_registered_user, jsonapi_community_server):
        """Create an admin user with proper membership for force-publish tests."""
        from src.auth.auth import create_access_token
        from src.database import get_session_maker
        from src.users.profile_models import CommunityMember

        async with get_session_maker()() as session:
            from sqlalchemy import update

            # Update the existing member to be an admin
            stmt = (
                update(CommunityMember)
                .where(
                    CommunityMember.community_id == jsonapi_community_server["uuid"],
                    CommunityMember.profile_id == jsonapi_registered_user["profile_id"],
                )
                .values(role="admin")
            )
            await session.execute(stmt)
            await session.commit()

        token_data = {
            "sub": str(jsonapi_registered_user["id"]),
            "username": jsonapi_registered_user["username"],
            "role": jsonapi_registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {"Authorization": f"Bearer {access_token}"}

        return jsonapi_registered_user, headers

    @pytest.fixture
    async def admin_auth_client(self, admin_user_and_headers):
        """Auth client using admin user."""
        from httpx import ASGITransport, AsyncClient

        from src.main import app

        _, headers = admin_user_and_headers
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(headers)
            yield client

    @pytest.mark.asyncio
    async def test_force_publish_note_success(
        self,
        admin_auth_client,
        jsonapi_auth_client,
        jsonapi_sample_note_data,
        jsonapi_community_server,
    ):
        """Test POST /api/v2/notes/{id}/force-publish successfully publishes a note.

        JSON:API response should contain:
        - data object with updated note resource
        - force_published attribute set to true
        - status updated to CURRENTLY_RATED_HELPFUL
        """
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await admin_auth_client.post(f"/api/v2/notes/{note_id}/force-publish")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "notes"
        assert data["data"]["id"] == note_id
        assert data["data"]["attributes"]["force_published"] is True
        assert data["data"]["attributes"]["status"] == "CURRENTLY_RATED_HELPFUL"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_force_publish_note_not_found(self, admin_auth_client):
        """Test POST /api/v2/notes/{id}/force-publish returns 404 for non-existent note."""
        from uuid import uuid4

        fake_id = str(uuid4())
        response = await admin_auth_client.post(f"/api/v2/notes/{fake_id}/force-publish")

        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_force_publish_note_non_admin_forbidden(
        self, jsonapi_auth_client, jsonapi_sample_note_data
    ):
        """Test POST /api/v2/notes/{id}/force-publish returns 403 for non-admin users."""
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await jsonapi_auth_client.post(f"/api/v2/notes/{note_id}/force-publish")

        assert response.status_code == 403, (
            f"Expected 403 for non-admin, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_force_publish_note_jsonapi_content_type(
        self,
        admin_auth_client,
        jsonapi_auth_client,
        jsonapi_sample_note_data,
    ):
        """Test that force-publish response Content-Type is application/vnd.api+json."""
        note_data = self._get_unique_note_data(jsonapi_sample_note_data)
        create_response = await jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await admin_auth_client.post(f"/api/v2/notes/{note_id}/force-publish")

        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )
