from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import status
from sqlalchemy import select

from src.database import get_session_maker
from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel, NoteClassification, NoteStatus
from src.users.profile_models import UserProfile

DISPATCH_PATCH_TARGET = "src.notes.ratings_jsonapi_router.dispatch_community_scoring"


async def create_rater_profile(display_name: str) -> UUID:
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


def make_jsonapi_rating_request(note_id: str, rater_id: str, helpfulness_level: str):
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
    import secrets
    from uuid import uuid4

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
    rater_id = await create_rater_profile("Test Rater 1")

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        str(rater_id),
        HelpfulnessLevel.HELPFUL,
    )

    with patch(DISPATCH_PATCH_TARGET, new_callable=AsyncMock) as mock_dispatch:
        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["data"]["attributes"]["note_id"] == str(test_note.id)
        mock_dispatch.assert_called_once_with(test_note.community_server_id)

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == rater_id,
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None
    assert rating.helpfulness_level == HelpfulnessLevel.HELPFUL

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.status == NoteStatus.NEEDS_MORE_RATINGS


@pytest.mark.asyncio
async def test_dispatch_failure_does_not_rollback_rating(
    async_client, async_auth_headers, db_session, test_note
):
    rater_id = await create_rater_profile("Test Rater 2")

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        str(rater_id),
        HelpfulnessLevel.HELPFUL,
    )

    with patch(DISPATCH_PATCH_TARGET, new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.side_effect = Exception("Dispatch failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == rater_id,
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None, "Rating should persist even when dispatch fails"

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.helpfulness_score == 0
    assert refreshed_note.status == NoteStatus.NEEDS_MORE_RATINGS


@pytest.mark.asyncio
async def test_dispatch_failure_preserves_database_state(
    async_client, async_auth_headers, db_session, test_note
):
    rater_id = await create_rater_profile("Test Rater 3")

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        str(rater_id),
        HelpfulnessLevel.HELPFUL,
    )

    with patch(DISPATCH_PATCH_TARGET, new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.side_effect = Exception("Dispatch failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == rater_id,
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None, "Rating should exist despite dispatch failure"


@pytest.mark.asyncio
async def test_scoring_dispatch_failure_does_not_affect_response(
    async_client, async_auth_headers, db_session, test_note
):
    rater_id = await create_rater_profile("Test Rater 4")

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        str(rater_id),
        HelpfulnessLevel.HELPFUL,
    )

    with patch(DISPATCH_PATCH_TARGET, new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.side_effect = Exception("Scoring dispatch failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == rater_id,
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None, "Rating should exist even if scoring dispatch fails"

    db_session.expunge(test_note)
    note_result = await db_session.execute(select(Note).where(Note.id == test_note.id))
    refreshed_note = note_result.scalar_one_or_none()
    assert refreshed_note is not None
    assert refreshed_note.helpfulness_score == 0
    assert refreshed_note.status == NoteStatus.NEEDS_MORE_RATINGS


@pytest.mark.asyncio
async def test_no_partial_state_after_dispatch_failure(
    async_client, async_auth_headers, db_session, test_note
):
    rater_id = await create_rater_profile("Test Rater 5")

    initial_score = test_note.helpfulness_score
    initial_status = test_note.status

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        str(rater_id),
        HelpfulnessLevel.HELPFUL,
    )

    with patch(DISPATCH_PATCH_TARGET, new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.side_effect = Exception("Dispatch failed")

        response = await async_client.post(
            "/api/v2/ratings",
            json=rating_data,
            headers=async_auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == rater_id,
        )
    )
    rating = rating_result.scalar_one_or_none()
    assert rating is not None, "Rating should exist after dispatch failure"

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
    rater_id = await create_rater_profile("Test Rater 6")

    rating_data = make_jsonapi_rating_request(
        str(test_note.id),
        str(rater_id),
        HelpfulnessLevel.SOMEWHAT_HELPFUL,
    )

    with patch(DISPATCH_PATCH_TARGET, new_callable=AsyncMock):
        response1 = await async_client.post(
            "/api/v2/ratings", json=rating_data, headers=async_auth_headers
        )
        assert response1.status_code == status.HTTP_201_CREATED

        rating_data["data"]["attributes"]["helpfulness_level"] = HelpfulnessLevel.HELPFUL
        response2 = await async_client.post(
            "/api/v2/ratings", json=rating_data, headers=async_auth_headers
        )
        assert response2.status_code == status.HTTP_201_CREATED

    db_session.expunge_all()
    rating_result = await db_session.execute(
        select(Rating).where(
            Rating.note_id == test_note.id,
            Rating.rater_id == rater_id,
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
    assert ratings[0].helpfulness_level == HelpfulnessLevel.HELPFUL, (
        "Rating should be updated to HELPFUL"
    )
