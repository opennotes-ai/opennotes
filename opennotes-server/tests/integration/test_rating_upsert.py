"""
Tests for rating upsert functionality to verify race condition fixes.

This test module verifies that the upsert pattern in submit_rating prevents
race conditions when multiple concurrent requests try to create ratings for
the same (note_id, rater_participant_id) pair.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.database import get_session_maker
from src.main import app
from src.notes.models import Note, Rating
from src.users.profile_models import UserProfile  # noqa: F401 - needed for relationship resolution

pytestmark = pytest.mark.integration


@pytest.fixture
async def test_note() -> Note:
    """Create a test note for rating tests."""
    from uuid import uuid4

    from src.llm_config.models import CommunityServer

    async with get_session_maker()() as session:
        # Create a community server first
        community_server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="test-server-123",
            name="Test Server",
            is_active=True,
        )
        session.add(community_server)
        await session.flush()

        note = Note(
            id=uuid4(),
            author_participant_id="test_author_001",
            summary=f"Test note for concurrent rating tests {uuid4().hex[:8]}",
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
    """Create an authenticated client for testing using a registered test user."""
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


class TestRatingUpsert:
    """Test rating upsert functionality to prevent race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_rating_creation_no_duplicates(
        self, auth_client: AsyncClient, test_note: Note
    ):
        """
        Test that concurrent attempts to create the same rating don't create duplicates.

        Scenario: Multiple threads try to rate the same note by the same user simultaneously.
        Expected: Only one rating is created (upsert pattern works correctly).
        """
        # Clear any existing ratings for this note
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        rating_attributes = {
            "note_id": str(test_note.id),
            "rater_participant_id": "concurrent_rater_001",
            "helpfulness_level": "HELPFUL",
        }
        rating_data = {
            "data": {
                "type": "ratings",
                "attributes": rating_attributes,
            }
        }

        async def submit_rating_request():
            """Submit a rating request."""
            response = await auth_client.post("/api/v2/ratings", json=rating_data)
            return response.status_code, response.json()

        # Launch 10 concurrent requests
        tasks = [submit_rating_request() for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should succeed (upsert pattern)
        status_codes = [r[0] for r in results if isinstance(r, tuple)]
        assert all(code == 201 for code in status_codes), "All requests should return 201 Created"

        # Verify only ONE rating exists in database
        async with get_session_maker()() as session:
            count_result = await session.execute(
                select(func.count(Rating.id)).where(
                    Rating.note_id == test_note.id,
                    Rating.rater_participant_id == rating_attributes["rater_participant_id"],
                )
            )
            rating_count = count_result.scalar()
            assert rating_count == 1, f"Expected 1 rating, found {rating_count}"

            # Verify the rating has correct data
            rating_result = await session.execute(
                select(Rating).where(
                    Rating.note_id == test_note.id,
                    Rating.rater_participant_id == rating_attributes["rater_participant_id"],
                )
            )
            rating = rating_result.scalar_one()
            assert rating.helpfulness_level == "HELPFUL"

    @pytest.mark.asyncio
    async def test_concurrent_rating_updates(self, auth_client: AsyncClient, test_note: Note):
        """
        Test that concurrent rating updates work correctly with upsert.

        Scenario: Multiple threads try to update the same rating with different values.
        Expected: Last write wins, no database errors.
        """
        # Clear any existing ratings
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        # Create initial rating
        rating_attributes = {
            "note_id": str(test_note.id),
            "rater_participant_id": "update_rater_001",
            "helpfulness_level": "HELPFUL",
        }
        rating_data = {
            "data": {
                "type": "ratings",
                "attributes": rating_attributes,
            }
        }
        response = await auth_client.post("/api/v2/ratings", json=rating_data)
        assert response.status_code == 201

        # Now concurrently try to update with different values
        async def submit_update(helpfulness_level: str):
            """Submit rating update."""
            data = {
                "data": {
                    "type": "ratings",
                    "attributes": {**rating_attributes, "helpfulness_level": helpfulness_level},
                }
            }
            response = await auth_client.post("/api/v2/ratings", json=data)
            return response.status_code

        # Launch concurrent updates with different values
        tasks = [
            submit_update("NOT_HELPFUL"),
            submit_update("SOMEWHAT_HELPFUL"),
            submit_update("HELPFUL"),
            submit_update("NOT_HELPFUL"),
            submit_update("SOMEWHAT_HELPFUL"),
        ]
        status_codes = await asyncio.gather(*tasks)

        # All should succeed
        assert all(code == 201 for code in status_codes), "All updates should succeed"

        # Verify only ONE rating exists
        async with get_session_maker()() as session:
            count_result = await session.execute(
                select(func.count(Rating.id)).where(
                    Rating.note_id == test_note.id,
                    Rating.rater_participant_id == "update_rater_001",
                )
            )
            rating_count = count_result.scalar()
            assert rating_count == 1, f"Expected 1 rating, found {rating_count}"

            # Verify rating has a valid helpfulness level (last write wins)
            rating_result = await session.execute(
                select(Rating).where(
                    Rating.note_id == test_note.id,
                    Rating.rater_participant_id == "update_rater_001",
                )
            )
            rating = rating_result.scalar_one()
            assert rating.helpfulness_level in ["HELPFUL", "NOT_HELPFUL", "SOMEWHAT_HELPFUL"]

    @pytest.mark.asyncio
    async def test_no_integrity_errors_under_load(self, auth_client: AsyncClient, test_note: Note):
        """
        Test that high concurrent load doesn't cause database integrity errors.

        Scenario: High volume of concurrent rating attempts.
        Expected: No IntegrityError exceptions, all requests handled gracefully.
        """
        # Clear any existing ratings
        async with get_session_maker()() as session:
            await session.execute(Rating.__table__.delete().where(Rating.note_id == test_note.id))
            await session.commit()

        rating_attributes = {
            "note_id": str(test_note.id),
            "rater_participant_id": "load_test_rater",
            "helpfulness_level": "HELPFUL",
        }
        rating_data = {
            "data": {
                "type": "ratings",
                "attributes": rating_attributes,
            }
        }

        async def submit_rating_request():
            """Submit a rating request."""
            try:
                response = await auth_client.post("/api/v2/ratings", json=rating_data)
                return response.status_code, None
            except Exception as e:
                return None, str(e)

        # Launch 20 concurrent requests (high load)
        tasks = [submit_rating_request() for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for IntegrityError exceptions
        errors = [r[1] for r in results if isinstance(r, tuple) and r[1] is not None]
        assert not any("IntegrityError" in str(e) for e in errors), (
            "Should not have IntegrityError exceptions"
        )

        # Verify only ONE rating exists
        async with get_session_maker()() as session:
            count_result = await session.execute(
                select(func.count(Rating.id)).where(
                    Rating.note_id == test_note.id,
                    Rating.rater_participant_id == rating_attributes["rater_participant_id"],
                )
            )
            rating_count = count_result.scalar()
            assert rating_count == 1, f"Expected 1 rating, found {rating_count}"
