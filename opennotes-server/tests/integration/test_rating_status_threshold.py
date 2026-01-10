"""
Tests for note status threshold transitions.

This test module verifies that note status only changes from NEEDS_MORE_RATINGS
to CURRENTLY_RATED_HELPFUL or CURRENTLY_RATED_NOT_HELPFUL after reaching the
minimum rating threshold (MIN_RATINGS_NEEDED).
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.config import settings
from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note, Rating

pytestmark = pytest.mark.integration


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
        note = Note(
            id=uuid4(),
            author_participant_id="test_author_threshold",
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
            rating_data = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(test_note.id),
                        "rater_participant_id": f"threshold_rater_{i:03d}",
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
    async def test_status_changes_to_helpful_at_threshold(
        self, auth_client: AsyncClient, test_note: Note
    ):
        """
        Test that note status changes to CURRENTLY_RATED_HELPFUL when:
        - rating count reaches MIN_RATINGS_NEEDED
        - score >= 0.5
        """
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        for i in range(settings.MIN_RATINGS_NEEDED):
            rating_data = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(test_note.id),
                        "rater_participant_id": f"helpful_rater_{i:03d}",
                        "helpfulness_level": "HELPFUL",
                    },
                }
            }
            response = await auth_client.post("/api/v2/ratings", json=rating_data)
            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == test_note.id))
            note = result.scalar_one()
            assert note.status == "CURRENTLY_RATED_HELPFUL", (
                f"Note status should be CURRENTLY_RATED_HELPFUL after "
                f"{settings.MIN_RATINGS_NEEDED} helpful ratings"
            )

    @pytest.mark.asyncio
    async def test_status_changes_to_not_helpful_at_threshold(
        self, auth_client: AsyncClient, test_note: Note
    ):
        """
        Test that note status changes to CURRENTLY_RATED_NOT_HELPFUL when:
        - rating count reaches MIN_RATINGS_NEEDED
        - score < 0.5
        """
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        for i in range(settings.MIN_RATINGS_NEEDED):
            rating_data = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(test_note.id),
                        "rater_participant_id": f"unhelpful_rater_{i:03d}",
                        "helpfulness_level": "NOT_HELPFUL",
                    },
                }
            }
            response = await auth_client.post("/api/v2/ratings", json=rating_data)
            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == test_note.id))
            note = result.scalar_one()
            assert note.status == "CURRENTLY_RATED_NOT_HELPFUL", (
                f"Note status should be CURRENTLY_RATED_NOT_HELPFUL after "
                f"{settings.MIN_RATINGS_NEEDED} not helpful ratings"
            )
