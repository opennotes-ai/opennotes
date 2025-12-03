"""Tests for JSON:API v2 ratings endpoints.

This module contains integration tests for the /api/v2/ratings endpoint that follows
the JSON:API 1.0 specification. These tests verify:
- POST /api/v2/ratings creates/upserts a rating
- GET /api/v2/notes/{id}/ratings returns ratings collection
- Proper JSON:API response envelope structure

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.notes.schemas import NoteClassification


@pytest.fixture
async def ratings_jsonapi_test_user():
    """Create a unique test user for ratings JSON:API tests to avoid conflicts"""
    return {
        "username": "ratingsjsonapitestuser",
        "email": "ratingsjsonapitest@example.com",
        "password": "TestPassword123!",
        "full_name": "Ratings JSONAPI Test User",
    }


@pytest.fixture
async def ratings_jsonapi_community_server():
    """Create a test community server for ratings JSON:API tests."""
    from uuid import uuid4

    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = "test_guild_ratings_jsonapi"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_id=platform_id,
            name="Test Guild for Ratings JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_id": platform_id}


@pytest.fixture
async def ratings_jsonapi_registered_user(
    ratings_jsonapi_test_user, ratings_jsonapi_community_server
):
    """Create a registered user for ratings JSON:API tests.

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
        await client.post("/api/v1/auth/register", json=ratings_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == ratings_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = "ratings_jsonapi_test_discord_id_123"

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
                community_id=ratings_jsonapi_community_server["uuid"],
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
async def ratings_jsonapi_auth_headers(ratings_jsonapi_registered_user):
    """Generate auth headers for ratings JSON:API test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(ratings_jsonapi_registered_user["id"]),
        "username": ratings_jsonapi_registered_user["username"],
        "role": ratings_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def ratings_jsonapi_auth_client(ratings_jsonapi_auth_headers):
    """Auth client using ratings JSON:API test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(ratings_jsonapi_auth_headers)
        yield client


@pytest.fixture
def ratings_jsonapi_sample_note_data(
    ratings_jsonapi_community_server, ratings_jsonapi_registered_user
):
    return {
        "classification": NoteClassification.NOT_MISLEADING,
        "summary": "This is a test note summary for ratings JSON:API",
        "author_participant_id": ratings_jsonapi_registered_user["discord_id"],
        "community_server_id": str(ratings_jsonapi_community_server["uuid"]),
    }


class TestRatingsJSONAPI:
    """Tests for the JSON:API v2 ratings endpoint."""

    def _get_unique_note_data(self, sample_note_data):
        note_data = sample_note_data.copy()
        note_data["summary"] = (
            f"Ratings JSONAPI test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        return note_data

    @pytest.mark.asyncio
    async def test_create_rating_jsonapi(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test POST /api/v2/ratings creates a rating with JSON:API request body.

        JSON:API 1.0 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status for new rating
        - Response body with 'data' object containing created resource
        """
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        request_body = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": "test_rater_jsonapi_123",
                    "helpfulness_level": "HELPFUL",
                },
            }
        }

        response = await ratings_jsonapi_auth_client.post("/api/v2/ratings", json=request_body)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "ratings", "Resource type must be 'ratings'"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"], "Resource must have 'attributes'"
        assert data["data"]["attributes"]["helpfulness_level"] == "HELPFUL"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_rating_jsonapi_upsert(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test POST /api/v2/ratings upserts an existing rating.

        If a rating already exists for the same note + rater, it should be updated.
        """
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        rater_id = "test_rater_upsert_jsonapi"

        request_body_1 = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": rater_id,
                    "helpfulness_level": "HELPFUL",
                },
            }
        }
        response_1 = await ratings_jsonapi_auth_client.post("/api/v2/ratings", json=request_body_1)
        assert response_1.status_code == 201

        request_body_2 = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": rater_id,
                    "helpfulness_level": "NOT_HELPFUL",
                },
            }
        }
        response_2 = await ratings_jsonapi_auth_client.post("/api/v2/ratings", json=request_body_2)

        assert response_2.status_code in [200, 201], (
            f"Expected 200 or 201, got {response_2.status_code}"
        )

        data = response_2.json()
        assert data["data"]["attributes"]["helpfulness_level"] == "NOT_HELPFUL"

    @pytest.mark.asyncio
    async def test_create_rating_jsonapi_invalid_type(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test POST /api/v2/ratings rejects invalid resource type."""
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": "test_rater",
                    "helpfulness_level": "HELPFUL",
                },
            }
        }

        response = await ratings_jsonapi_auth_client.post("/api/v2/ratings", json=request_body)

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_create_rating_jsonapi_note_not_found(self, ratings_jsonapi_auth_client):
        """Test POST /api/v2/ratings returns 404 for non-existent note."""
        from uuid import uuid4

        fake_note_id = str(uuid4())

        request_body = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": fake_note_id,
                    "rater_participant_id": "test_rater",
                    "helpfulness_level": "HELPFUL",
                },
            }
        }

        response = await ratings_jsonapi_auth_client.post("/api/v2/ratings", json=request_body)

        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_list_note_ratings_jsonapi(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/notes/{id}/ratings returns ratings collection.

        JSON:API 1.0 requires:
        - Response with 200 OK status
        - 'data' array containing rating resource objects
        - Each resource has 'type', 'id', and 'attributes'
        """
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        rating_body = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": "test_rater_list_jsonapi",
                    "helpfulness_level": "HELPFUL",
                },
            }
        }
        rating_response = await ratings_jsonapi_auth_client.post(
            "/api/v2/ratings", json=rating_body
        )
        assert rating_response.status_code in [200, 201]

        response = await ratings_jsonapi_auth_client.get(f"/api/v2/notes/{note_id}/ratings")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

        assert len(data["data"]) > 0, "Should have at least one rating"

        rating_resource = data["data"][0]
        assert "type" in rating_resource, "Resource must have 'type'"
        assert rating_resource["type"] == "ratings", "Resource type must be 'ratings'"
        assert "id" in rating_resource, "Resource must have 'id'"
        assert "attributes" in rating_resource, "Resource must have 'attributes'"
        assert "helpfulness_level" in rating_resource["attributes"]

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_list_note_ratings_jsonapi_empty(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/notes/{id}/ratings returns empty array for unrated note."""
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await ratings_jsonapi_auth_client.get(f"/api/v2/notes/{note_id}/ratings")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0

    @pytest.mark.asyncio
    async def test_list_note_ratings_jsonapi_not_found(self, ratings_jsonapi_auth_client):
        """Test GET /api/v2/notes/{id}/ratings returns 404 for non-existent note."""
        from uuid import uuid4

        fake_note_id = str(uuid4())

        response = await ratings_jsonapi_auth_client.get(f"/api/v2/notes/{fake_note_id}/ratings")

        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_update_rating_jsonapi(
        self,
        ratings_jsonapi_auth_client,
        ratings_jsonapi_sample_note_data,
        ratings_jsonapi_registered_user,
    ):
        """Test PUT /api/v2/ratings/{rating_id} updates a rating with JSON:API request body.

        JSON:API 1.0 requires:
        - Request body with 'data' object containing 'type', 'id', and 'attributes'
        - Response with 200 OK status for updated resource
        - Response body with 'data' object containing updated resource
        """
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        rater_id = ratings_jsonapi_registered_user["discord_id"]

        create_rating_body = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": rater_id,
                    "helpfulness_level": "HELPFUL",
                },
            }
        }
        rating_response = await ratings_jsonapi_auth_client.post(
            "/api/v2/ratings", json=create_rating_body
        )
        assert rating_response.status_code == 201
        rating_id = rating_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "ratings",
                "id": rating_id,
                "attributes": {
                    "helpfulness_level": "NOT_HELPFUL",
                },
            }
        }

        response = await ratings_jsonapi_auth_client.put(
            f"/api/v2/ratings/{rating_id}", json=update_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "ratings", "Resource type must be 'ratings'"
        assert data["data"]["id"] == rating_id, "Resource ID must match"
        assert data["data"]["attributes"]["helpfulness_level"] == "NOT_HELPFUL"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_rating_jsonapi_not_found(self, ratings_jsonapi_auth_client):
        """Test PUT /api/v2/ratings/{rating_id} returns 404 for non-existent rating."""
        from uuid import uuid4

        fake_rating_id = str(uuid4())

        update_body = {
            "data": {
                "type": "ratings",
                "id": fake_rating_id,
                "attributes": {
                    "helpfulness_level": "NOT_HELPFUL",
                },
            }
        }

        response = await ratings_jsonapi_auth_client.put(
            f"/api/v2/ratings/{fake_rating_id}", json=update_body
        )

        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

    @pytest.mark.asyncio
    async def test_update_rating_jsonapi_invalid_type(
        self,
        ratings_jsonapi_auth_client,
        ratings_jsonapi_sample_note_data,
        ratings_jsonapi_registered_user,
    ):
        """Test PUT /api/v2/ratings/{rating_id} rejects invalid resource type."""
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        rater_id = ratings_jsonapi_registered_user["discord_id"]

        create_rating_body = {
            "data": {
                "type": "ratings",
                "attributes": {
                    "note_id": note_id,
                    "rater_participant_id": rater_id,
                    "helpfulness_level": "HELPFUL",
                },
            }
        }
        rating_response = await ratings_jsonapi_auth_client.post(
            "/api/v2/ratings", json=create_rating_body
        )
        assert rating_response.status_code == 201
        rating_id = rating_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "invalid_type",
                "id": rating_id,
                "attributes": {
                    "helpfulness_level": "NOT_HELPFUL",
                },
            }
        }

        response = await ratings_jsonapi_auth_client.put(
            f"/api/v2/ratings/{rating_id}", json=update_body
        )

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_get_rating_stats_jsonapi(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/notes/{note_id}/ratings/stats returns statistics.

        JSON:API 1.0 requires:
        - Response with 200 OK status
        - 'data' object containing singleton/aggregate resource
        - Resource has 'type', 'id', and 'attributes'
        """
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        for i, level in enumerate(["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"]):
            rating_body = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": note_id,
                        "rater_participant_id": f"test_rater_stats_{i}",
                        "helpfulness_level": level,
                    },
                }
            }
            r = await ratings_jsonapi_auth_client.post("/api/v2/ratings", json=rating_body)
            assert r.status_code == 201

        response = await ratings_jsonapi_auth_client.get(f"/api/v2/notes/{note_id}/ratings/stats")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "rating-stats", "Resource type must be 'rating-stats'"
        assert data["data"]["id"] == note_id, "Resource ID must be the note_id"

        attrs = data["data"]["attributes"]
        assert "total" in attrs
        assert "helpful" in attrs
        assert "somewhat_helpful" in attrs
        assert "not_helpful" in attrs
        assert "average_score" in attrs

        assert attrs["total"] == 3
        assert attrs["helpful"] == 1
        assert attrs["somewhat_helpful"] == 1
        assert attrs["not_helpful"] == 1
        assert 1.0 <= attrs["average_score"] <= 3.0

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_rating_stats_jsonapi_empty(
        self, ratings_jsonapi_auth_client, ratings_jsonapi_sample_note_data
    ):
        """Test GET /api/v2/notes/{note_id}/ratings/stats returns zero stats for unrated note."""
        note_data = self._get_unique_note_data(ratings_jsonapi_sample_note_data)
        create_response = await ratings_jsonapi_auth_client.post("/api/v1/notes", json=note_data)
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        response = await ratings_jsonapi_auth_client.get(f"/api/v2/notes/{note_id}/ratings/stats")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

        attrs = data["data"]["attributes"]
        assert attrs["total"] == 0
        assert attrs["helpful"] == 0
        assert attrs["somewhat_helpful"] == 0
        assert attrs["not_helpful"] == 0
        assert attrs["average_score"] == 0.0

    @pytest.mark.asyncio
    async def test_get_rating_stats_jsonapi_not_found(self, ratings_jsonapi_auth_client):
        """Test GET /api/v2/notes/{note_id}/ratings/stats returns 404 for non-existent note."""
        from uuid import uuid4

        fake_note_id = str(uuid4())

        response = await ratings_jsonapi_auth_client.get(
            f"/api/v2/notes/{fake_note_id}/ratings/stats"
        )

        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
