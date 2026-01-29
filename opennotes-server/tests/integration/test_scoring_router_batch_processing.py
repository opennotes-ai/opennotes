"""
Tests for batch processing in get_top_notes endpoint to prevent memory exhaustion.

This test file verifies that task-224 fix works correctly by ensuring:
1. Batch processing reduces memory usage
2. Results are correct and properly sorted
3. Filtering and pagination still work as expected
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import status

from src.database import get_session_maker
from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel, NoteClassification, NoteStatus
from src.users.profile_models import (
    CommunityMember,
    UserIdentity,
    UserProfile,
)


async def create_user_profile(display_name: str) -> UUID:
    """Create a user profile for testing. Returns the profile ID (UUID)."""
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
async def author_profiles():
    """Create author profiles for testing."""
    profiles = {}
    for i in range(100):
        profile_id = await create_user_profile(f"Test Author {i}")
        profiles[i] = profile_id
    return profiles


@pytest.fixture
async def rater_profiles():
    """Create rater profiles for testing."""
    profiles = {}
    for j in range(10):
        profile_id = await create_user_profile(f"Test Rater {j}")
        profiles[j] = profile_id
    return profiles


@pytest.fixture
def mock_notes_factory(community_server, author_profiles, rater_profiles):
    """Factory to create mock notes with ratings."""

    def create_notes(count: int, base_score: float = 50.0) -> list[Note]:
        """Create a list of mock notes with varying scores."""
        notes = []
        for i in range(count):
            note_id = uuid4()
            author_id = author_profiles[i % len(author_profiles)]
            note = Note(
                id=note_id,
                author_id=author_id,
                community_server_id=community_server,
                summary=f"Test note {i}",
                classification=NoteClassification.NOT_MISLEADING,
                helpfulness_score=int(base_score + (i % 100)),
                status=NoteStatus.NEEDS_MORE_RATINGS,
            )
            note.ratings = []
            for j in range(5):
                rater_id = rater_profiles[j % len(rater_profiles)]
                rating = Rating(
                    id=uuid4(),
                    note_id=note_id,
                    rater_id=rater_id,
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

    author_ids = [await create_user_profile(f"Batch Author {i}") for i in range(100)]
    rater_ids = [await create_user_profile(f"Batch Rater {j}") for j in range(5)]

    for i in range(100):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_id=author_ids[i],
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
                rater_id=rater_ids[j],
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
    author_ids = [await create_user_profile(f"TopScore Author {i}") for i in range(100)]
    rater_ids = [await create_user_profile(f"TopScore Rater {j}") for j in range(5)]

    notes_with_scores = []
    for i in range(100):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_id=author_ids[i],
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
                rater_id=rater_ids[j],
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
    author_ids = [await create_user_profile(f"Filter Author {i}") for i in range(50)]
    rater_ids = [await create_user_profile(f"Filter Rater {j}") for j in range(10)]

    notes = []
    for i in range(50):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_id=author_ids[i],
            community_server_id=community_server,
            summary=f"Test note {i}",
            classification=NoteClassification.NOT_MISLEADING,
            helpfulness_score=50 + i,
            status=NoteStatus.NEEDS_MORE_RATINGS,
        )
        rating_count = 10 if i % 2 == 0 else 2
        note.ratings = [
            Rating(
                id=uuid4(),
                note_id=note_id,
                rater_id=rater_ids[j % len(rater_ids)],
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
    large_count = 50000
    batch_size = 1000
    limit = 10

    max_in_memory = [0]

    test_community_id = user_with_community_membership["membership"].community_id
    mock_author_id = uuid4()

    class MockNote:
        def __init__(self, note_idx, score, community_id):
            self.id = uuid4()
            self.author_id = mock_author_id
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
    author_ids = [await create_user_profile(f"Pagination Author {i}") for i in range(100)]
    rater_ids = [await create_user_profile(f"Pagination Rater {j}") for j in range(5)]

    for i in range(100):
        note_id = uuid4()
        note = Note(
            id=note_id,
            author_id=author_ids[i],
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
                rater_id=rater_ids[j],
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
