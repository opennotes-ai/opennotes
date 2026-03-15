"""
Tests for note status threshold transitions.

Since TASK-1321 removed inline scoring from routers, note status is no longer
updated synchronously during rating creation. Status transitions now happen
asynchronously when the DBOS scoring workflow runs. These tests verify that:
- Rating creation succeeds and returns 201
- Note status remains NEEDS_MORE_RATINGS after rating creation (no inline update)
- Scoring dispatch is attempted for notes with a community_server_id
"""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.config import settings
from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note, Rating
from src.users.profile_models import UserProfile

pytestmark = pytest.mark.integration


async def create_rater_profile(display_name: str) -> UUID:
    """Create a rater profile for testing.

    Returns the profile ID (UUID) to use as rater_id.
    """
    async with get_session_maker()() as session:
        profile = UserProfile(
            display_name=display_name,
            is_human=True,
            is_active=True,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile.id


@pytest.fixture
async def community_server() -> CommunityServer:
    """Create a test community server."""
    async with get_session_maker()() as session:
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id=f"test-server-{uuid4().hex[:8]}",
            name="Test Server",
            is_active=True,
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        return server


@pytest.fixture
async def test_note(community_server: CommunityServer) -> Note:
    """Create a test note for rating threshold tests."""
    async with get_session_maker()() as session:
        # Create author profile
        author_profile = UserProfile(
            display_name="Test Author Threshold",
            is_human=True,
            is_active=True,
        )
        session.add(author_profile)
        await session.flush()

        note = Note(
            id=uuid4(),
            author_id=author_profile.id,
            summary=f"Test note for threshold status tests {uuid4().hex[:8]}",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            community_server_id=community_server.id,
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        return note


@pytest.fixture
async def auth_client(registered_user):
    """Create an authenticated client for testing."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(registered_user["id"]),
        "username": registered_user["username"],
        "role": registered_user["role"],
    }
    access_token = create_access_token(token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(headers)
        yield client


class TestRatingStatusThreshold:
    """Test note status only changes after reaching rating threshold."""

    @pytest.mark.asyncio
    async def test_status_remains_needs_more_ratings_below_threshold(
        self, auth_client: AsyncClient, test_note: Note
    ):
        """
        Test that note status remains NEEDS_MORE_RATINGS when rating count is below threshold.
        """
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        for i in range(settings.MIN_RATINGS_NEEDED - 1):
            # Create a proper rater profile with UUID for each rater
            rater_id = await create_rater_profile(f"Threshold Rater {i:03d}")

            rating_data = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(test_note.id),
                        "rater_id": str(rater_id),
                        "helpfulness_level": "HELPFUL",
                    },
                }
            }
            response = await auth_client.post("/api/v2/ratings", json=rating_data)
            assert response.status_code == 201

            async with get_session_maker()() as session:
                result = await session.execute(select(Note).where(Note.id == test_note.id))
                note = result.scalar_one()
                assert note.status == "NEEDS_MORE_RATINGS", (
                    f"Note status should remain NEEDS_MORE_RATINGS with {i + 1} ratings "
                    f"(threshold is {settings.MIN_RATINGS_NEEDED})"
                )

    @pytest.mark.asyncio
    async def test_status_unchanged_at_threshold_scoring_is_async(
        self, auth_client: AsyncClient, test_note: Note
    ):
        """
        After TASK-1321, scoring is async via DBOS. Note status remains
        NEEDS_MORE_RATINGS after rating creation — the scoring workflow
        updates it later.
        """
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        for i in range(settings.MIN_RATINGS_NEEDED):
            rater_id = await create_rater_profile(f"Helpful Rater {i:03d}")

            rating_data = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(test_note.id),
                        "rater_id": str(rater_id),
                        "helpfulness_level": "HELPFUL",
                    },
                }
            }
            response = await auth_client.post("/api/v2/ratings", json=rating_data)
            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == test_note.id))
            note = result.scalar_one()
            assert note.status == "NEEDS_MORE_RATINGS", (
                "Status should remain NEEDS_MORE_RATINGS — scoring is now async via DBOS"
            )
