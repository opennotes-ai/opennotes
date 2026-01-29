"""Tests for JSON:API v2 scoring endpoints.

This module contains integration tests for the /api/v2/scoring endpoints that follow
the JSON:API 1.1 specification. These tests verify:
- GET /api/v2/scoring/status returns system scoring status
- GET /api/v2/scoring/notes/{note_id}/score returns score for one note
- POST /api/v2/scoring/notes/batch-scores returns scores for multiple notes
- GET /api/v2/scoring/notes/top returns top-scored notes
- Proper JSON:API response envelope structure

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.notes.schemas import NoteClassification


@pytest.fixture
async def scoring_jsonapi_test_user():
    """Create a unique test user for scoring JSON:API tests to avoid conflicts"""
    return {
        "username": "scoringjsonapitestuser",
        "email": "scoringjsonapitest@example.com",
        "password": "TestPassword123!",
        "full_name": "Scoring JSONAPI Test User",
    }


@pytest.fixture
async def scoring_jsonapi_community_server():
    """Create a test community server for scoring JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = "test_guild_scoring_jsonapi"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Scoring JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def scoring_jsonapi_registered_user(
    scoring_jsonapi_test_user, scoring_jsonapi_community_server
):
    """Create a registered user for scoring JSON:API tests.

    Sets up all required records for community authorization.
    """
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=scoring_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == scoring_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = "scoring_jsonapi_test_discord_id_123"

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
                community_id=scoring_jsonapi_community_server["uuid"],
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
async def scoring_jsonapi_auth_headers(scoring_jsonapi_registered_user):
    """Generate auth headers for scoring JSON:API test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(scoring_jsonapi_registered_user["id"]),
        "username": scoring_jsonapi_registered_user["username"],
        "role": scoring_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def scoring_jsonapi_auth_client(scoring_jsonapi_auth_headers):
    """Auth client using scoring JSON:API test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(scoring_jsonapi_auth_headers)
        yield client


@pytest.fixture
def scoring_jsonapi_sample_note_data(
    scoring_jsonapi_community_server, scoring_jsonapi_registered_user
):
    return {
        "classification": NoteClassification.NOT_MISLEADING,
        "summary": "This is a test note summary for scoring JSON:API",
        "author_id": str(scoring_jsonapi_registered_user["profile_id"]),
        "community_server_id": str(scoring_jsonapi_community_server["uuid"]),
    }


async def create_note_v2(client, note_data):
    """Create a note using the v2 JSON:API endpoint."""
    request_body = {
        "data": {
            "type": "notes",
            "attributes": {
                "summary": note_data["summary"],
                "classification": note_data["classification"].value
                if hasattr(note_data["classification"], "value")
                else note_data["classification"],
                "community_server_id": str(note_data["community_server_id"]),
                "author_id": note_data["author_id"],
            },
        }
    }
    return await client.post("/api/v2/notes", json=request_body)


class TestScoringStatusJSONAPI:
    """Tests for GET /api/v2/scoring/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_scoring_status_jsonapi(self, scoring_jsonapi_auth_client):
        """Test GET /api/v2/scoring/status returns status in JSON:API format.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' object containing resource
        - Resource has 'type', 'id', and 'attributes'
        - 'jsonapi' object with version
        """
        response = await scoring_jsonapi_auth_client.get("/api/v2/scoring/status")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "scoring-status", "Resource type must be 'scoring-status'"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"], "Resource must have 'attributes'"

        attrs = data["data"]["attributes"]
        assert "current_note_count" in attrs
        assert "active_tier" in attrs
        assert "data_confidence" in attrs
        assert "tier_thresholds" in attrs
        assert "warnings" in attrs

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_scoring_status_unauthorized(self):
        """Test GET /api/v2/scoring/status requires authentication."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/scoring/status")

            assert response.status_code in [401, 403], (
                f"Expected 401 or 403, got {response.status_code}"
            )


class TestNoteScoreJSONAPI:
    """Tests for GET /api/v2/scoring/notes/{note_id}/score endpoint."""

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Scoring test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_get_note_score_jsonapi(
        self, scoring_jsonapi_auth_client, scoring_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/scoring/notes/{note_id}/score returns score in JSON:API format.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' object containing score resource
        - Resource has 'type', 'id', and 'attributes'
        """
        note_data = self._get_unique_note_data(scoring_jsonapi_sample_note_data)
        create_response = await create_note_v2(scoring_jsonapi_auth_client, note_data)
        assert create_response.status_code == 201, f"Failed to create note: {create_response.text}"
        note_id = create_response.json()["data"]["id"]

        response = await scoring_jsonapi_auth_client.get(f"/api/v2/scoring/notes/{note_id}/score")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "note-scores", "Resource type must be 'note-scores'"
        assert data["data"]["id"] == note_id, "Resource id must match note_id"
        assert "attributes" in data["data"], "Resource must have 'attributes'"

        attrs = data["data"]["attributes"]
        assert "score" in attrs
        assert "confidence" in attrs
        assert "algorithm" in attrs
        assert "rating_count" in attrs
        assert "tier" in attrs
        assert "tier_name" in attrs

        assert "jsonapi" in data
        assert data["jsonapi"].get("version") == "1.1"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_note_score_jsonapi_not_found(self, scoring_jsonapi_auth_client):
        """Test GET /api/v2/scoring/notes/{note_id}/score returns 404 for non-existent note."""
        fake_note_id = str(uuid4())

        response = await scoring_jsonapi_auth_client.get(
            f"/api/v2/scoring/notes/{fake_note_id}/score"
        )

        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert len(data["errors"]) > 0
        assert data["errors"][0]["status"] == "404"


class TestBatchScoresJSONAPI:
    """Tests for POST /api/v2/scoring/notes/batch-scores endpoint."""

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Batch scoring test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_batch_scores_jsonapi(
        self, scoring_jsonapi_auth_client, scoring_jsonapi_sample_note_data
    ):
        """Test POST /api/v2/scoring/notes/batch-scores returns scores in JSON:API format.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 200 OK status
        - 'data' array containing score resources
        """
        note_data_1 = self._get_unique_note_data(scoring_jsonapi_sample_note_data)
        create_response_1 = await create_note_v2(scoring_jsonapi_auth_client, note_data_1)
        assert create_response_1.status_code == 201
        note_id_1 = create_response_1.json()["data"]["id"]

        note_data_2 = self._get_unique_note_data(scoring_jsonapi_sample_note_data)
        create_response_2 = await create_note_v2(scoring_jsonapi_auth_client, note_data_2)
        assert create_response_2.status_code == 201
        note_id_2 = create_response_2.json()["data"]["id"]

        request_body = {
            "data": {
                "type": "batch-score-requests",
                "attributes": {"note_ids": [note_id_1, note_id_2]},
            }
        }

        response = await scoring_jsonapi_auth_client.post(
            "/api/v2/scoring/notes/batch-scores", json=request_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data
        assert data["jsonapi"].get("version") == "1.1"

        assert "meta" in data, "Response must contain 'meta' key"
        assert "total_requested" in data["meta"]
        assert "total_found" in data["meta"]
        assert data["meta"]["total_requested"] == 2
        assert data["meta"]["total_found"] == 2

        assert len(data["data"]) == 2
        for resource in data["data"]:
            assert resource["type"] == "note-scores"
            assert "id" in resource
            assert "attributes" in resource
            assert "score" in resource["attributes"]
            assert "confidence" in resource["attributes"]

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_batch_scores_jsonapi_partial_not_found(
        self, scoring_jsonapi_auth_client, scoring_jsonapi_sample_note_data
    ):
        """Test POST /api/v2/scoring/notes/batch-scores handles partial not found."""
        note_data = self._get_unique_note_data(scoring_jsonapi_sample_note_data)
        create_response = await create_note_v2(scoring_jsonapi_auth_client, note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["data"]["id"]

        fake_note_id = str(uuid4())

        request_body = {
            "data": {
                "type": "batch-score-requests",
                "attributes": {"note_ids": [note_id, fake_note_id]},
            }
        }

        response = await scoring_jsonapi_auth_client.post(
            "/api/v2/scoring/notes/batch-scores", json=request_body
        )

        assert response.status_code == 200

        data = response.json()
        assert data["meta"]["total_requested"] == 2
        assert data["meta"]["total_found"] == 1
        assert "not_found" in data["meta"]
        assert fake_note_id in data["meta"]["not_found"]

    @pytest.mark.asyncio
    async def test_batch_scores_jsonapi_empty_request(self, scoring_jsonapi_auth_client):
        """Test POST /api/v2/scoring/notes/batch-scores rejects empty list."""
        request_body = {"data": {"type": "batch-score-requests", "attributes": {"note_ids": []}}}

        response = await scoring_jsonapi_auth_client.post(
            "/api/v2/scoring/notes/batch-scores", json=request_body
        )

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"


class TestTopNotesJSONAPI:
    """Tests for GET /api/v2/scoring/notes/top endpoint."""

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Top notes test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_get_top_notes_jsonapi(
        self, scoring_jsonapi_auth_client, scoring_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/scoring/notes/top returns top notes in JSON:API format.

        JSON:API 1.1 requires:
        - Response with 200 OK status
        - 'data' array containing note score resources
        - Pagination links in 'links'
        - Meta information in 'meta'
        """
        note_data = self._get_unique_note_data(scoring_jsonapi_sample_note_data)
        create_response = await create_note_v2(scoring_jsonapi_auth_client, note_data)
        assert create_response.status_code == 201

        response = await scoring_jsonapi_auth_client.get("/api/v2/scoring/notes/top")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data
        assert data["jsonapi"].get("version") == "1.1"

        assert "meta" in data
        assert "total_count" in data["meta"]
        assert "current_tier" in data["meta"]

        for resource in data["data"]:
            assert resource["type"] == "note-scores"
            assert "id" in resource
            assert "attributes" in resource
            assert "score" in resource["attributes"]

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_top_notes_jsonapi_with_limit(
        self, scoring_jsonapi_auth_client, scoring_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/scoring/notes/top respects limit parameter."""
        for _ in range(3):
            note_data = self._get_unique_note_data(scoring_jsonapi_sample_note_data)
            create_response = await create_note_v2(scoring_jsonapi_auth_client, note_data)
            assert create_response.status_code == 201

        response = await scoring_jsonapi_auth_client.get("/api/v2/scoring/notes/top?limit=2")

        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) <= 2

    @pytest.mark.asyncio
    async def test_get_top_notes_jsonapi_with_confidence_filter(self, scoring_jsonapi_auth_client):
        """Test GET /api/v2/scoring/notes/top respects min_confidence filter."""
        response = await scoring_jsonapi_auth_client.get(
            "/api/v2/scoring/notes/top?min_confidence=standard"
        )

        assert response.status_code == 200

        data = response.json()
        assert "meta" in data
        if "filters_applied" in data["meta"]:
            assert "min_confidence" in data["meta"]["filters_applied"]

    @pytest.mark.asyncio
    async def test_get_top_notes_jsonapi_links(self, scoring_jsonapi_auth_client):
        """Test GET /api/v2/scoring/notes/top includes JSON:API links."""
        response = await scoring_jsonapi_auth_client.get("/api/v2/scoring/notes/top")

        assert response.status_code == 200

        data = response.json()
        assert "links" in data, "Response must contain 'links' key"
        assert "self" in data["links"], "Links must include 'self'"
