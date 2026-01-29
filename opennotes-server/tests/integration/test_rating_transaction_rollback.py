"""
Tests for task-226: Verify rating submission and score update happen in same transaction.

This ensures data consistency by verifying that if score calculation fails,
both the rating and score updates are rolled back together.
"""

from unittest.mock import patch

import pytest
from fastapi import status
from sqlalchemy import select

from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel, NoteClassification, NoteStatus
from src.users.profile_models import UserProfile


def make_jsonapi_rating_request(note_id: str, rater_id: str, helpfulness_level: str):
    """Helper to create JSON:API formatted rating request."""
    return {
        "data": {
            "type": "ratings",
            "attributes": {
                "note_id": note_id,
                "rater_id": rater_id,
                "helpfulness_level": helpfulness_level,
            },
        }
    }


@pytest.fixture
async def test_note(db_session, community_server):
    """Create a test note for rating submission."""
    import secrets
    from uuid import uuid4

    # Create author profile
    author_profile = UserProfile(
        display_name="Test Author",
        is_human=True,
        is_active=True,
    )
    db_session.add(author_profile)
    await db_session.flush()

    note = Note(
        id=uuid4(),
        author_id=author_profile.id,
        summary=f"Test note for transaction testing {secrets.token_urlsafe(8)}",
        classification=NoteClassification.NOT_MISLEADING,
        helpfulness_score=0,
        status=NoteStatus.NEEDS_MORE_RATINGS,
        community_server_id=community_server,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.mark.asyncio
async def test_rating_and_score_in_same_transaction_success(
    async_client, async_auth_headers, db_session, test_note
):
    """Test that rating creation and score update happen in the same transaction on success."""
    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        "test_rater_1",
        HelpfulnessLevel.HELPFUL,
    )

    response = await async_client.post(
        "/api/v2/ratings",
        json=rating_data,
        headers=async_auth_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["data"]["attributes"]["note_id"] == str(test_note.id)

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == "test_rater_1",
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None
    assert rating.helpfulness_level == HelpfulnessLevel.HELPFUL

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.helpfulness_score > 0
    assert refreshed_note.status == NoteStatus.NEEDS_MORE_RATINGS


@pytest.mark.asyncio
async def test_transaction_rollback_on_score_calculation_failure(
    async_client, async_auth_headers, db_session, test_note
):
    """Test that if score calculation fails, both rating and score updates are rolled back."""

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        "test_rater_2",
        HelpfulnessLevel.HELPFUL,
    )

    with patch("src.notes.ratings_jsonapi_router.calculate_note_score") as mock_calculate:
        mock_calculate.side_effect = Exception("Score calculation failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "errors" in response_data
        assert response_data["errors"][0]["detail"] == "Failed to create rating"

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == "test_rater_2",
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is None, "Rating should not exist after rollback"

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.helpfulness_score == 0
    assert refreshed_note.status == NoteStatus.NEEDS_MORE_RATINGS


@pytest.mark.asyncio
async def test_transaction_rollback_on_database_error(
    async_client, async_auth_headers, db_session, test_note
):
    """Test that database errors trigger full transaction rollback."""

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        "test_rater_3",
        HelpfulnessLevel.HELPFUL,
    )

    with patch("src.notes.ratings_jsonapi_router.calculate_note_score") as mock_calculate:
        mock_calculate.side_effect = Exception("Score calculation failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == "test_rater_3",
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is None, "Rating should not exist after rollback"


@pytest.mark.asyncio
async def test_event_publish_failure_does_not_affect_transaction(
    async_client, async_auth_headers, db_session, test_note
):
    """Test that event publishing failures don't affect database consistency."""

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        "test_rater_4",
        HelpfulnessLevel.HELPFUL,
    )

    with patch(
        "src.events.scoring_events.ScoringEventPublisher.publish_note_score_updated"
    ) as mock_publish:
        mock_publish.side_effect = Exception("Event publish failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == "test_rater_4",
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None, "Rating should exist even if event publishing fails"

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.helpfulness_score > 0
    assert refreshed_note.status == NoteStatus.NEEDS_MORE_RATINGS


@pytest.mark.asyncio
async def test_no_partial_state_after_score_update_failure(
    async_client, async_auth_headers, db_session, test_note
):
    """Test that there's no partial state where rating exists but score is not updated."""

    initial_score = test_note.helpfulness_score
    initial_status = test_note.status

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        "test_rater_5",
        HelpfulnessLevel.HELPFUL,
    )

    with patch("src.notes.ratings_jsonapi_router.calculate_note_score") as mock_calculate:
        mock_calculate.side_effect = Exception("Score calculation failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == "test_rater_5",
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is None, "Rating should not exist"

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.helpfulness_score == initial_score, "Score should be unchanged"
    assert refreshed_note.status == initial_status, "Status should be unchanged"


@pytest.mark.asyncio
async def test_upsert_updates_existing_rating_in_same_transaction(
    async_client, async_auth_headers, db_session, test_note
):
    """Test that updating existing rating also updates score in same transaction."""

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        "test_rater_6",
        HelpfulnessLevel.SOMEWHAT_HELPFUL,
    )

    response1 = await async_client.post(
        "/api/v2/ratings", json=rating_data, headers=async_auth_headers
    )
    assert response1.status_code == status.HTTP_201_CREATED

    db_session.expunge_all()
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    note_after_first = note_result.scalar_one_or_none()
    assert note_after_first is not None
    first_score = note_after_first.helpfulness_score
    assert first_score > 0, "Score should be updated after first rating"

    rating_data["data"]["attributes"]["helpfulness_level"] = HelpfulnessLevel.HELPFUL
    response2 = await async_client.post(
        "/api/v2/ratings", json=rating_data, headers=async_auth_headers
    )
    assert response2.status_code == status.HTTP_201_CREATED

    db_session.expunge_all()
    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == "test_rater_6",
        )
    )
    ratings = rating_result.scalars().all()
    assert len(ratings) == 1, "Should have exactly one rating (upsert)"
    assert ratings[0].helpfulness_level == HelpfulnessLevel.HELPFUL

    db_session.expunge_all()
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    note_after_second = note_result.scalar_one_or_none()
    assert note_after_second is not None
    assert note_after_second.status == NoteStatus.NEEDS_MORE_RATINGS, (
        "Note status should remain NEEDS_MORE_RATINGS until rating threshold is reached"
    )
    final_rating = ratings[0]
    assert final_rating.helpfulness_level == HelpfulnessLevel.HELPFUL, (
        "Rating should be updated to HELPFUL"
    )
