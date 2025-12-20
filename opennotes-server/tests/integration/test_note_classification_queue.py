"""Test that notes with different classifications appear in the note queue correctly."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.notes.schemas import NoteClassification, NoteStatus


@pytest.fixture
async def classification_test_user():
    """Create a unique test user for classification tests"""
    return {
        "username": "classificationtestuser",
        "email": "classificationtest@example.com",
        "password": "TestPassword123!",
        "full_name": "Classification Test User",
    }


@pytest.fixture
async def classification_registered_user(classification_test_user, community_server):
    """Create a registered user specifically for classification tests.

    Also creates UserProfile, UserIdentity, and CommunityMember records
    required by the authorization middleware (task-713).
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=classification_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == classification_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = "classification_test_discord_id_456"

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
                community_id=community_server,
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
async def classification_auth_headers(classification_registered_user):
    """Generate auth headers for classification test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(classification_registered_user["id"]),
        "username": classification_registered_user["username"],
        "role": classification_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def classification_auth_client(classification_auth_headers):
    """Auth client using classification-specific test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(classification_auth_headers)
        yield client


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
                "author_participant_id": note_data["author_participant_id"],
            },
        }
    }
    return await client.post("/api/v2/notes", json=request_body)


class TestNoteClassificationInQueue:
    """Test that notes with all classifications appear in the note queue"""

    @pytest.mark.asyncio
    async def test_not_misleading_note_appears_in_queue(
        self, classification_auth_client, community_server
    ):
        """Verify that a human-written NOT_MISLEADING note appears in the queue"""
        # Create a note with NOT_MISLEADING classification
        note_data = {
            "classification": NoteClassification.NOT_MISLEADING,
            "summary": f"This post is actually accurate and helpful {datetime.now(UTC).timestamp()}",
            "author_participant_id": "author_not_misleading",
            "community_server_id": str(community_server),
        }

        # Create the note
        create_response = await create_note_v2(classification_auth_client, note_data)
        assert create_response.status_code == 201
        created_note = create_response.json()["data"]

        # Verify the note was created with correct status
        assert created_note["attributes"]["classification"] == NoteClassification.NOT_MISLEADING
        assert created_note["attributes"]["status"] == NoteStatus.NEEDS_MORE_RATINGS

        # List notes with NEEDS_MORE_RATINGS status using v2 JSON:API filter syntax
        list_response = await classification_auth_client.get(
            "/api/v2/notes?filter[status]=NEEDS_MORE_RATINGS"
        )
        assert list_response.status_code == 200
        notes_data = list_response.json()

        # Verify our NOT_MISLEADING note appears in the queue
        note_ids = [note["id"] for note in notes_data["data"]]
        assert created_note["id"] in note_ids, (
            "NOT_MISLEADING note should appear in NEEDS_MORE_RATINGS queue"
        )

    @pytest.mark.asyncio
    async def test_misinformed_note_appears_in_queue(
        self, classification_auth_client, community_server
    ):
        """Verify that a MISINFORMED_OR_POTENTIALLY_MISLEADING note appears in the queue"""
        # Create a note with MISINFORMED_OR_POTENTIALLY_MISLEADING classification
        note_data = {
            "classification": NoteClassification.MISINFORMED_OR_POTENTIALLY_MISLEADING,
            "summary": f"This post contains misinformation {datetime.now(UTC).timestamp()}",
            "author_participant_id": "author_misleading",
            "community_server_id": str(community_server),
        }

        # Create the note
        create_response = await create_note_v2(classification_auth_client, note_data)
        assert create_response.status_code == 201
        created_note = create_response.json()["data"]

        # Verify the note was created with correct status
        assert (
            created_note["attributes"]["classification"]
            == NoteClassification.MISINFORMED_OR_POTENTIALLY_MISLEADING
        )
        assert created_note["attributes"]["status"] == NoteStatus.NEEDS_MORE_RATINGS

        # List notes with NEEDS_MORE_RATINGS status using v2 JSON:API filter syntax
        list_response = await classification_auth_client.get(
            "/api/v2/notes?filter[status]=NEEDS_MORE_RATINGS"
        )
        assert list_response.status_code == 200
        notes_data = list_response.json()

        # Verify our MISINFORMED note appears in the queue
        note_ids = [note["id"] for note in notes_data["data"]]
        assert created_note["id"] in note_ids, (
            "MISINFORMED note should appear in NEEDS_MORE_RATINGS queue"
        )

    @pytest.mark.asyncio
    async def test_both_classifications_appear_together(
        self, classification_auth_client, community_server
    ):
        """Verify that notes of both classifications appear together in the queue"""
        # Create one NOT_MISLEADING note
        not_misleading_note = {
            "classification": NoteClassification.NOT_MISLEADING,
            "summary": f"Accurate post #1 {datetime.now(UTC).timestamp()}",
            "author_participant_id": "author_accurate",
            "community_server_id": str(community_server),
        }

        # Create one MISINFORMED note
        misinformed_note = {
            "classification": NoteClassification.MISINFORMED_OR_POTENTIALLY_MISLEADING,
            "summary": f"Misleading post #1 {datetime.now(UTC).timestamp()}",
            "author_participant_id": "author_misleading_2",
            "community_server_id": str(community_server),
        }

        # Create both notes
        response1 = await create_note_v2(classification_auth_client, not_misleading_note)
        response2 = await create_note_v2(classification_auth_client, misinformed_note)

        assert response1.status_code == 201
        assert response2.status_code == 201

        note1 = response1.json()["data"]
        note2 = response2.json()["data"]

        # List all notes with NEEDS_MORE_RATINGS status using v2 JSON:API filter syntax
        list_response = await classification_auth_client.get(
            "/api/v2/notes?filter[status]=NEEDS_MORE_RATINGS&page[size]=100"
        )
        assert list_response.status_code == 200
        notes_data = list_response.json()

        note_ids = [note["id"] for note in notes_data["data"]]

        # Both notes should appear in the queue regardless of classification
        assert note1["id"] in note_ids, "NOT_MISLEADING note should be in queue"
        assert note2["id"] in note_ids, "MISINFORMED note should be in queue"

    @pytest.mark.asyncio
    async def test_classification_filter_works_independently(
        self, classification_auth_client, community_server
    ):
        """Verify that classification filtering works independently from status filtering"""
        # Create notes with different classifications
        not_misleading_note = {
            "classification": NoteClassification.NOT_MISLEADING,
            "summary": f"Accurate post #2 {datetime.now(UTC).timestamp()}",
            "author_participant_id": "author_accurate_2",
            "community_server_id": str(community_server),
        }

        misinformed_note = {
            "classification": NoteClassification.MISINFORMED_OR_POTENTIALLY_MISLEADING,
            "summary": f"Misleading post #2 {datetime.now(UTC).timestamp()}",
            "author_participant_id": "author_misleading_3",
            "community_server_id": str(community_server),
        }

        # Create both notes
        response1 = await create_note_v2(classification_auth_client, not_misleading_note)
        response2 = await create_note_v2(classification_auth_client, misinformed_note)

        assert response1.status_code == 201
        assert response2.status_code == 201

        note1 = response1.json()["data"]
        note2 = response2.json()["data"]

        # Filter by classification=NOT_MISLEADING and status=NEEDS_MORE_RATINGS using v2 JSON:API
        list_response = await classification_auth_client.get(
            "/api/v2/notes?filter[status]=NEEDS_MORE_RATINGS&filter[classification]=NOT_MISLEADING&page[size]=100"
        )
        assert list_response.status_code == 200
        notes_data = list_response.json()

        note_ids = [note["id"] for note in notes_data["data"]]

        # Only NOT_MISLEADING note should appear
        assert note1["id"] in note_ids, "NOT_MISLEADING note should match filter"
        assert note2["id"] not in note_ids, "MISINFORMED note should not match filter"

        # Filter by classification=MISINFORMED_OR_POTENTIALLY_MISLEADING using v2 JSON:API
        list_response2 = await classification_auth_client.get(
            "/api/v2/notes?filter[status]=NEEDS_MORE_RATINGS"
            "&filter[classification]=MISINFORMED_OR_POTENTIALLY_MISLEADING&page[size]=100"
        )
        assert list_response2.status_code == 200
        notes_data2 = list_response2.json()

        note_ids2 = [note["id"] for note in notes_data2["data"]]

        # Only MISINFORMED note should appear
        assert note1["id"] not in note_ids2, "NOT_MISLEADING note should not match filter"
        assert note2["id"] in note_ids2, "MISINFORMED note should match filter"
