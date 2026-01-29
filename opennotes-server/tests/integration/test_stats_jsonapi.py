"""Tests for JSON:API v2 stats endpoints.

This module contains integration tests for the /api/v2/stats endpoints that follow
the JSON:API 1.1 specification. These tests verify:
- Proper JSON:API response envelope structure
- Note statistics aggregation
- Participant statistics retrieval
- Date range filtering via filter[date_from] and filter[date_to]
- Community filtering via filter[community_server_id]

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note, Rating
from src.notes.schemas import NoteClassification, NoteStatus
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile


@pytest.fixture
async def stats_jsonapi_community_server():
    """Create a test community server for stats JSON:API tests."""
    community_server_id = uuid4()
    unique_suffix = uuid4().hex[:8]
    platform_id = f"test_guild_stats_jsonapi_{unique_suffix}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name=f"Test Guild for Stats JSONAPI {unique_suffix}",
            description="A test community for stats JSON:API endpoint testing",
            is_public=True,
            is_active=True,
        )
        db.add(community_server)
        await db.commit()

    return {
        "uuid": community_server_id,
        "platform_community_server_id": platform_id,
        "platform": "discord",
        "name": f"Test Guild for Stats JSONAPI {unique_suffix}",
    }


@pytest.fixture
async def stats_jsonapi_test_user():
    """Create a unique test user for stats JSON:API tests."""
    unique_suffix = uuid4().hex[:8]
    return {
        "username": f"statsjsonapitestuser_{unique_suffix}",
        "email": f"statsjsonapitest_{unique_suffix}@example.com",
        "password": "TestPassword123!",
        "full_name": "Stats JSONAPI Test User",
    }


@pytest.fixture
async def stats_jsonapi_registered_user(stats_jsonapi_test_user, stats_jsonapi_community_server):
    """Create a registered user with profile for stats JSON:API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=stats_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == stats_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            unique_discord_id = f"stats_jsonapi_discord_{uuid4().hex[:12]}"
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
                community_id=stats_jsonapi_community_server["uuid"],
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
async def stats_jsonapi_auth_headers(stats_jsonapi_registered_user):
    """Generate auth headers for stats JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(stats_jsonapi_registered_user["id"]),
        "username": stats_jsonapi_registered_user["username"],
        "role": stats_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def stats_jsonapi_auth_client(stats_jsonapi_auth_headers):
    """Auth client using stats JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(stats_jsonapi_auth_headers)
        yield client


@pytest.fixture
async def stats_jsonapi_test_notes(stats_jsonapi_community_server):
    """Create test notes with various statuses for stats JSON:API tests."""
    async with get_session_maker()() as db:
        notes = []

        # Create a user profile for the author/participant
        participant_profile = UserProfile(
            display_name=f"Test Participant {uuid4().hex[:8]}",
            is_human=True,
            is_active=True,
        )
        db.add(participant_profile)
        await db.flush()

        note_helpful = Note(
            id=uuid4(),
            author_id=participant_profile.id,
            summary="This is a helpful note for testing",
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=stats_jsonapi_community_server["uuid"],
            status=NoteStatus.CURRENTLY_RATED_HELPFUL,
            helpfulness_score=85,
            created_at=datetime.now(UTC),
        )
        db.add(note_helpful)
        notes.append(note_helpful)

        note_not_helpful = Note(
            id=uuid4(),
            author_id=participant_profile.id,
            summary="This is a not helpful note for testing",
            classification=NoteClassification.MISINFORMED_OR_POTENTIALLY_MISLEADING,
            community_server_id=stats_jsonapi_community_server["uuid"],
            status=NoteStatus.CURRENTLY_RATED_NOT_HELPFUL,
            helpfulness_score=15,
            created_at=datetime.now(UTC),
        )
        db.add(note_not_helpful)
        notes.append(note_not_helpful)

        note_pending = Note(
            id=uuid4(),
            author_id=participant_profile.id,
            summary="This is a pending note for testing",
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=stats_jsonapi_community_server["uuid"],
            status=NoteStatus.NEEDS_MORE_RATINGS,
            helpfulness_score=50,
            created_at=datetime.now(UTC),
        )
        db.add(note_pending)
        notes.append(note_pending)

        await db.commit()

        return {
            "notes": notes,
            "participant_id": str(participant_profile.id),
            "community_server_id": stats_jsonapi_community_server["uuid"],
        }


@pytest.fixture
async def stats_jsonapi_test_ratings(stats_jsonapi_test_notes):
    """Create test ratings for the test notes."""
    async with get_session_maker()() as db:
        # Create a user profile for the rater
        rater_profile = UserProfile(
            display_name=f"Test Rater {uuid4().hex[:8]}",
            is_human=True,
            is_active=True,
        )
        db.add(rater_profile)
        await db.flush()

        for note in stats_jsonapi_test_notes["notes"]:
            rating = Rating(
                id=uuid4(),
                note_id=note.id,
                rater_id=rater_profile.id,
                helpfulness_level="HELPFUL"
                if note.status == NoteStatus.CURRENTLY_RATED_HELPFUL
                else "NOT_HELPFUL",
                created_at=datetime.now(UTC),
            )
            db.add(rating)

        await db.commit()

        return {
            "rater_id": str(rater_profile.id),
        }


class TestStatsJSONAPI:
    """Tests for the JSON:API v2 stats endpoints."""

    @pytest.mark.asyncio
    async def test_get_notes_stats_jsonapi_format(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes
    ):
        """Test GET /api/v2/stats/notes returns proper JSON:API format.

        JSON:API 1.1 requires:
        - 'data' object containing resource object
        - 'jsonapi' object with version
        """
        response = await stats_jsonapi_auth_client.get("/api/v2/stats/notes")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

    @pytest.mark.asyncio
    async def test_notes_stats_resource_object_structure(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes
    ):
        """Test that notes stats resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier ('note-stats')
        - 'id': unique identifier string
        - 'attributes': object containing resource attributes
        """
        response = await stats_jsonapi_auth_client.get("/api/v2/stats/notes")
        assert response.status_code == 200

        data = response.json()
        stats_resource = data["data"]

        assert "type" in stats_resource, "Resource must have 'type'"
        assert stats_resource["type"] == "note-stats", "Resource type must be 'note-stats'"

        assert "id" in stats_resource, "Resource must have 'id'"
        assert isinstance(stats_resource["id"], str), "Resource id must be a string"

        assert "attributes" in stats_resource, "Resource must have 'attributes'"
        attributes = stats_resource["attributes"]
        assert "total_notes" in attributes, "Attributes must include 'total_notes'"
        assert "helpful_notes" in attributes, "Attributes must include 'helpful_notes'"
        assert "not_helpful_notes" in attributes, "Attributes must include 'not_helpful_notes'"
        assert "pending_notes" in attributes, "Attributes must include 'pending_notes'"
        assert "average_helpfulness_score" in attributes, (
            "Attributes must include 'average_helpfulness_score'"
        )

    @pytest.mark.asyncio
    async def test_notes_stats_content_type(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes
    ):
        """Test that response Content-Type is application/vnd.api+json."""
        response = await stats_jsonapi_auth_client.get("/api/v2/stats/notes")
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_notes_stats_with_community_filter(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes
    ):
        """Test GET /api/v2/stats/notes with community_server_id filter."""
        community_id = str(stats_jsonapi_test_notes["community_server_id"])
        response = await stats_jsonapi_auth_client.get(
            "/api/v2/stats/notes",
            params={"filter[community_server_id]": community_id},
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        attributes = data["data"]["attributes"]

        assert attributes["total_notes"] == 3
        assert attributes["helpful_notes"] == 1
        assert attributes["not_helpful_notes"] == 1
        assert attributes["pending_notes"] == 1

    @pytest.mark.asyncio
    async def test_notes_stats_with_date_range_filter(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes
    ):
        """Test GET /api/v2/stats/notes with date range filters."""
        date_from = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        date_to = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        response = await stats_jsonapi_auth_client.get(
            "/api/v2/stats/notes",
            params={
                "filter[date_from]": date_from,
                "filter[date_to]": date_to,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "note-stats"

    @pytest.mark.asyncio
    async def test_get_participant_stats_jsonapi_format(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes, stats_jsonapi_test_ratings
    ):
        """Test GET /api/v2/stats/author/{id} returns proper JSON:API format."""
        participant_id = stats_jsonapi_test_notes["participant_id"]
        response = await stats_jsonapi_auth_client.get(f"/api/v2/stats/author/{participant_id}")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

    @pytest.mark.asyncio
    async def test_participant_stats_resource_object_structure(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes, stats_jsonapi_test_ratings
    ):
        """Test that participant stats resource objects have correct JSON:API structure."""
        participant_id = stats_jsonapi_test_notes["participant_id"]
        response = await stats_jsonapi_auth_client.get(f"/api/v2/stats/author/{participant_id}")
        assert response.status_code == 200

        data = response.json()
        stats_resource = data["data"]

        assert "type" in stats_resource, "Resource must have 'type'"
        assert stats_resource["type"] == "participant-stats", (
            "Resource type must be 'participant-stats'"
        )

        assert "id" in stats_resource, "Resource must have 'id'"
        assert stats_resource["id"] == participant_id, "Resource id must match participant_id"

        assert "attributes" in stats_resource, "Resource must have 'attributes'"
        attributes = stats_resource["attributes"]
        assert "notes_created" in attributes, "Attributes must include 'notes_created'"
        assert "ratings_given" in attributes, "Attributes must include 'ratings_given'"
        assert "average_helpfulness_received" in attributes, (
            "Attributes must include 'average_helpfulness_received'"
        )
        assert "top_classification" in attributes, "Attributes must include 'top_classification'"

    @pytest.mark.asyncio
    async def test_participant_stats_content_type(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes
    ):
        """Test that participant stats response Content-Type is application/vnd.api+json."""
        participant_id = stats_jsonapi_test_notes["participant_id"]
        response = await stats_jsonapi_auth_client.get(f"/api/v2/stats/author/{participant_id}")
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_participant_stats_with_community_filter(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes, stats_jsonapi_test_ratings
    ):
        """Test GET /api/v2/stats/author/{id} with community_server_id filter."""
        participant_id = stats_jsonapi_test_notes["participant_id"]
        community_id = str(stats_jsonapi_test_notes["community_server_id"])

        response = await stats_jsonapi_auth_client.get(
            f"/api/v2/stats/author/{participant_id}",
            params={"filter[community_server_id]": community_id},
        )
        assert response.status_code == 200

        data = response.json()
        attributes = data["data"]["attributes"]

        assert attributes["notes_created"] == 3
        assert attributes["ratings_given"] == 0

    @pytest.mark.asyncio
    async def test_participant_stats_rater(
        self, stats_jsonapi_auth_client, stats_jsonapi_test_notes, stats_jsonapi_test_ratings
    ):
        """Test GET /api/v2/stats/author/{id} for a rater."""
        rater_id = stats_jsonapi_test_ratings["rater_id"]
        community_id = str(stats_jsonapi_test_notes["community_server_id"])

        response = await stats_jsonapi_auth_client.get(
            f"/api/v2/stats/author/{rater_id}",
            params={"filter[community_server_id]": community_id},
        )
        assert response.status_code == 200

        data = response.json()
        attributes = data["data"]["attributes"]

        assert attributes["notes_created"] == 0
        assert attributes["ratings_given"] == 3

    @pytest.mark.asyncio
    async def test_unauthenticated_stats_returns_401(self):
        """Test that GET /api/v2/stats/notes without auth returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/stats/notes")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_participant_stats_returns_401(self):
        """Test that GET /api/v2/stats/author/{id} without auth returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/stats/author/00000000-0000-0000-0000-000000000000")
            assert response.status_code == 401
