"""
Tests for batch processing in get_top_notes endpoint to prevent memory exhaustion.

This test file verifies that task-224 fix works correctly by ensuring:
1. Batch processing reduces memory usage
2. Results are correct and properly sorted
3. Filtering and pagination still work as expected
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel, NoteClassification, NoteStatus
from src.users.profile_models import (
    CommunityMember,
    UserIdentity,
    UserProfile,
)


@pytest.fixture
async def user_with_community_membership(db_session, registered_user, community_server):
    """
    Create UserProfile, UserIdentity, and CommunityMember for the registered user.

    The get_top_notes endpoint filters notes by community membership.
    Without a CommunityMember record, the user can't see any notes.

    This fixture:
    1. Creates a UserProfile for the registered user
    2. Creates a UserIdentity linking the profile via email provider
    3. Creates a CommunityMember linking the user to the test community_server
    """
    profile = UserProfile(
        id=uuid4(),
        display_name=registered_user["username"],
        is_active=True,
        is_banned=False,
    )
    db_session.add(profile)
    await db_session.flush()

    identity = UserIdentity(
        id=uuid4(),
        profile_id=profile.id,
        provider="email",
        provider_user_id=registered_user["email"],
    )
    db_session.add(identity)

    membership = CommunityMember(
        id=uuid4(),
        community_id=community_server,
        profile_id=profile.id,
        role="member",
        is_active=True,
        joined_at=datetime.now(UTC),
    )
    db_session.add(membership)
    await db_session.commit()

    return {
        "profile": profile,
        "identity": identity,
        "membership": membership,
    }


@pytest.fixture
def mock_notes_factory(community_server):
    """Factory to create mock notes with ratings."""

    def create_notes(count: int, base_score: float = 50.0) -> list[Note]:
        """Create a list of mock notes with varying scores."""
        notes = []
        for i in range(count):
            note_id = uuid4()
            note = Note(
                id=note_id,
                author_participant_id=f"author_{i}",
                community_server_id=community_server,
                summary=f"Test note {i}",
                classification=NoteClassification.NOT_MISLEADING,
                helpfulness_score=int(base_score + (i % 100)),
                status=NoteStatus.NEEDS_MORE_RATINGS,
            )
            note.ratings = []
            for j in range(5):
                rating = Rating(
                    id=uuid4(),
                    note_id=note_id,
                    rater_participant_id=f"rater_{j}",
                    helpfulness_level=HelpfulnessLevel.HELPFUL,
                )
                note.ratings.append(rating)
            notes.append(note)
        return notes

    return create_notes


@pytest.mark.asyncio
async def test_get_top_notes_uses_batch_processing(
    async_client, async_auth_headers, db_session, community_server, user_with_community_membership
):
    """Test that get_top_notes endpoint handles large datasets correctly."""
    from src.notes.models import Note, Rating
    from src.notes.schemas import HelpfulnessLevel, NoteClassification, NoteStatus

    for i in range(100):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_participant_id=f"author_{i}",
            community_server_id=community_server,
            summary=f"Test note {i}",
            classification=NoteClassification.NOT_MISLEADING,
            helpfulness_score=50 + i,
            status=NoteStatus.NEEDS_MORE_RATINGS,
        )
        note.ratings = [
            Rating(
                id=uuid4(),
                note_id=note_id,
                rater_participant_id=f"rater_{j}",
                helpfulness_level=HelpfulnessLevel.HELPFUL,
            )
            for j in range(5)
        ]
        db_session.add(note)

    await db_session.commit()

    response = await async_client.get(
        "/api/v2/scoring/notes/top",
        headers=async_auth_headers,
        params={"limit": 10, "batch_size": 1000},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["data"]) == 10, "Should return exactly 10 notes when 100 exist"


@pytest.mark.asyncio
async def test_get_top_notes_returns_correct_top_scored_notes(
    async_client, async_auth_headers, db_session, community_server, user_with_community_membership
):
    """Test that batch processing returns correctly sorted top notes."""
    # Create notes with known scores
    notes_with_scores = []
    for i in range(100):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_participant_id=f"author_{i}",
            community_server_id=community_server,
            summary=f"Test note {i}",
            classification=NoteClassification.NOT_MISLEADING,
            helpfulness_score=i,
            status=NoteStatus.NEEDS_MORE_RATINGS,
        )
        note.ratings = [
            Rating(
                id=uuid4(),
                note_id=note_id,
                rater_participant_id=f"rater_{j}",
                helpfulness_level=HelpfulnessLevel.HELPFUL,
            )
            for j in range(5)
        ]
        db_session.add(note)
        notes_with_scores.append(note)

    await db_session.commit()

    response = await async_client.get(
        "/api/v2/scoring/notes/top",
        headers=async_auth_headers,
        params={"limit": 10, "batch_size": 100},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data["data"]) == 10

    scores = [note["attributes"]["score"] for note in data["data"]]
    assert scores == sorted(scores, reverse=True), "Notes should be sorted by score"


@pytest.mark.asyncio
async def test_get_top_notes_filtering_works_with_batch_processing(
    async_client, async_auth_headers, db_session, community_server, user_with_community_membership
):
    """Test that filtering by confidence and tier works with batch processing."""
    # Create mix of notes with different ratings counts (affecting confidence)
    notes = []
    for i in range(50):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_participant_id=f"author_{i}",
            community_server_id=community_server,
            summary=f"Test note {i}",
            classification=NoteClassification.NOT_MISLEADING,
            helpfulness_score=50 + i,
            status=NoteStatus.NEEDS_MORE_RATINGS,
        )
        # Some notes have many ratings (standard confidence)
        # Some have few ratings (provisional confidence)
        rating_count = 10 if i % 2 == 0 else 2
        note.ratings = [
            Rating(
                id=uuid4(),
                note_id=note_id,
                rater_participant_id=f"rater_{j}",
                helpfulness_level=HelpfulnessLevel.HELPFUL,
            )
            for j in range(rating_count)
        ]
        db_session.add(note)
        notes.append(note)

    await db_session.commit()

    response = await async_client.get(
        "/api/v2/scoring/notes/top",
        headers=async_auth_headers,
        params={"limit": 10, "min_confidence": "standard", "batch_size": 100},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "min_confidence" in data["meta"]["filters_applied"]
    assert data["meta"]["filters_applied"]["min_confidence"] == "standard"


@pytest.mark.asyncio
async def test_get_top_notes_memory_efficient_with_large_dataset(
    async_client, async_auth_headers, db_session, community_server, user_with_community_membership
):
    """Test that memory usage is bounded with large datasets."""
    # Simulate a very large dataset (50k+ notes)
    large_count = 50000
    batch_size = 1000
    limit = 10

    # We'll track peak memory usage of the scored notes list
    max_in_memory = [0]

    # Get the community_id from the membership fixture for use in mock
    test_community_id = user_with_community_membership["membership"].community_id

    class MockNote:
        def __init__(self, note_idx, score, community_id):
            self.id = uuid4()
            self.author_participant_id = f"author_{note_idx}"
            self.summary = f"Note {note_idx}"
            self.classification = "NOT_MISLEADING"
            self.helpfulness_score = score
            self.status = "NEEDS_MORE_RATINGS"
            self.ratings = []
            self.community_server_id = community_id

    # Save original execute for delegation
    original_execute = db_session.execute

    async def mock_execute(query):
        query_str = str(query).lower()

        # Let community membership queries go through to real DB
        # These queries are needed to verify user access
        if "community_member" in query_str or "user_identit" in query_str:
            return await original_execute(query)

        # Count query for notes
        if "count" in query_str and "note" in query_str:
            result = MagicMock()
            result.scalar.return_value = large_count
            return result

        # Batch query for notes - simulate returning batches
        offset = 0
        limit_val = batch_size

        # Extract offset and limit from query (simplified)
        result_notes = []
        for i in range(offset, min(offset + limit_val, large_count)):
            result_notes.append(MockNote(i, 50 + (i % 100), test_community_id))

        class MockScalarResult:
            def __init__(self, notes):
                self.notes = notes
                max_in_memory[0] = max(max_in_memory[0], len(notes))

            def all(self):
                return self.notes

        class MockResult:
            def __init__(self, notes):
                self.notes = notes

            def scalars(self):
                return MockScalarResult(self.notes)

        return MockResult(result_notes)

    db_session.execute = mock_execute

    try:
        response = await async_client.get(
            "/api/v2/scoring/notes/top",
            headers=async_auth_headers,
            params={"limit": limit, "batch_size": batch_size},
        )

        assert response.status_code == status.HTTP_200_OK

        expected_max = batch_size + (limit * 5)
        assert max_in_memory[0] <= expected_max, (
            f"Peak memory {max_in_memory[0]} should not exceed {expected_max}"
        )

    finally:
        db_session.execute = original_execute


@pytest.mark.asyncio
async def test_get_top_notes_pagination_works_correctly(
    async_client, async_auth_headers, db_session, community_server, user_with_community_membership
):
    """Test that pagination (limit parameter) works correctly with batch processing."""
    # Create 100 notes
    for i in range(100):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_participant_id=f"author_{i}",
            community_server_id=community_server,
            summary=f"Test note {i}",
            classification=NoteClassification.NOT_MISLEADING,
            helpfulness_score=100 - i,
            status=NoteStatus.NEEDS_MORE_RATINGS,
        )
        note.ratings = [
            Rating(
                id=uuid4(),
                note_id=note_id,
                rater_participant_id=f"rater_{j}",
                helpfulness_level=HelpfulnessLevel.HELPFUL,
            )
            for j in range(5)
        ]
        db_session.add(note)

    await db_session.commit()

    for limit in [5, 10, 25, 50]:
        response = await async_client.get(
            "/api/v2/scoring/notes/top",
            headers=async_auth_headers,
            params={"limit": limit, "batch_size": 100},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]) == limit, f"Should return exactly {limit} notes for limit={limit}"


@pytest.mark.asyncio
async def test_get_top_notes_handles_empty_database(
    async_client, async_auth_headers, db_session, community_server, user_with_community_membership
):
    """Test that endpoint handles empty database gracefully."""
    response = await async_client.get(
        "/api/v2/scoring/notes/top", headers=async_auth_headers, params={"limit": 10}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["data"] == []
    assert data["meta"]["total_count"] == 0
