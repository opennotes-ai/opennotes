"""
Tests for request status update when notes are published.

This test module verifies that when a note is published (either through
force-publish or threshold-based publishing), the associated request status
is automatically set to COMPLETED atomically with the publish operation.
"""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.auth import create_access_token
from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note, Request

pytestmark = pytest.mark.integration


async def create_note_v2_request(client, note_data):
    """Create a note using the v2 JSON:API endpoint."""
    attributes = {
        "summary": note_data["summary"],
        "classification": note_data["classification"],
        "community_server_id": str(note_data["community_server_id"]),
        "author_participant_id": note_data["author_participant_id"],
    }
    if "request_id" in note_data:
        attributes["request_id"] = note_data["request_id"]
    request_body = {
        "data": {
            "type": "notes",
            "attributes": attributes,
        }
    }
    return await client.post("/api/v2/notes", json=request_body)


async def create_note_with_request() -> tuple[Note, Request, CommunityServer]:
    """Create a test note with an associated request."""
    async with get_session_maker()() as session:
        community_server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id="test-server-123",
            name="Test Server",
            is_active=True,
        )
        session.add(community_server)
        await session.flush()

        request = Request(
            id=uuid4(),
            request_id=f"req_{uuid4()}",
            requested_by="test_user_001",
            status="PENDING",
            community_server_id=community_server.id,
        )
        session.add(request)
        await session.flush()

        note = Note(
            id=uuid4(),
            author_participant_id="test_author_001",
            summary=f"Test note for request status update {uuid4().hex[:8]}",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            community_server_id=community_server.id,
            request_id=request.request_id,
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        await session.refresh(request)
        return note, request, community_server


class TestRequestStatusOnPublish:
    """Test that request status is updated when notes are published."""

    @pytest.mark.asyncio
    async def test_force_publish_sets_request_to_completed(
        self,
        registered_user,
    ):
        """
        Test that force-publishing a note sets the associated request to COMPLETED.

        Scenario: Admin force-publishes a note
        Expected: Both note.force_published is True AND request.status is COMPLETED atomically
        """
        from src.users.models import User

        user_id = UUID(registered_user["id"])
        async with get_session_maker()() as session:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one()
            user.is_service_account = True
            await session.commit()

        note, request, _community_server = await create_note_with_request()

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            response = await client.post(f"/api/v2/notes/{note.id}/force-publish")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            request_result = await session.execute(
                select(Request).where(Request.request_id == request.request_id)
            )
            updated_request = request_result.scalar_one()

            assert updated_request.status == "COMPLETED"
            assert updated_request.request_id == request.request_id

    @pytest.mark.asyncio
    async def test_force_publish_without_request_succeeds(
        self,
        registered_user,
    ):
        """
        Test that force-publishing a note without an associated request still succeeds.

        Scenario: Note has no associated request
        Expected: Force-publish succeeds, note is marked as published
        """
        from src.users.models import User

        user_id = UUID(registered_user["id"])
        async with get_session_maker()() as session:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one()
            user.is_service_account = True
            await session.commit()

        async with get_session_maker()() as session:
            community_server = CommunityServer(
                id=uuid4(),
                platform="discord",
                platform_id="test-server-456",
                name="Test Server 2",
                is_active=True,
            )
            session.add(community_server)
            await session.flush()

            note = Note(
                id=uuid4(),
                author_participant_id="test_author_002",
                summary=f"Note without request {uuid4().hex[:8]}",
                classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                community_server_id=community_server.id,
                request_id=None,
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            note_id = note.id

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            response = await client.post(f"/api/v2/notes/{note_id}/force-publish")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            note_result = await session.execute(select(Note).where(Note.id == note_id))
            updated_note = note_result.scalar_one()
            assert updated_note.force_published is True

    @pytest.mark.asyncio
    async def test_threshold_rating_does_not_complete_request(
        self,
        registered_user,
    ):
        """
        Test that rating submission does NOT change request status.

        Scenario: Submit ratings that cause note score to reach publishing threshold (>= 0.5)
        Expected: Request status remains unchanged (ratings don't complete requests -
                  only actual note publication via note_publisher_router completes requests)
        """
        note, request, _community_server = await create_note_with_request()

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {"Authorization": f"Bearer {access_token}"}

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            rating_data_1 = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(note.id),
                        "rater_participant_id": "rater_001",
                        "helpfulness_level": "HELPFUL",
                    },
                }
            }
            response1 = await client.post("/api/v2/ratings", json=rating_data_1)
            assert response1.status_code == 201

            rating_data_2 = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(note.id),
                        "rater_participant_id": "rater_002",
                        "helpfulness_level": "HELPFUL",
                    },
                }
            }
            response2 = await client.post("/api/v2/ratings", json=rating_data_2)
            assert response2.status_code == 201

            rating_data_3 = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(note.id),
                        "rater_participant_id": "rater_003",
                        "helpfulness_level": "HELPFUL",
                    },
                }
            }
            response3 = await client.post("/api/v2/ratings", json=rating_data_3)
            assert response3.status_code == 201

        async with get_session_maker()() as session:
            request_result = await session.execute(
                select(Request).where(Request.request_id == request.request_id)
            )
            updated_request = request_result.scalar_one()
            assert updated_request.status == "PENDING"

    @pytest.mark.asyncio
    async def test_threshold_publish_with_low_score_no_update(
        self,
        registered_user,
    ):
        """
        Test that ratings that don't reach publishing threshold don't update request.

        Scenario: Submit a rating that results in score < 0.5
        Expected: Request status remains PENDING
        """
        note, request, _community_server = await create_note_with_request()

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            rating_data = {
                "data": {
                    "type": "ratings",
                    "attributes": {
                        "note_id": str(note.id),
                        "rater_participant_id": "rater_unhelpful",
                        "helpfulness_level": "NOT_HELPFUL",
                    },
                }
            }
            response = await client.post("/api/v2/ratings", json=rating_data)
            assert response.status_code == 201

        async with get_session_maker()() as session:
            request_result = await session.execute(
                select(Request).where(Request.request_id == request.request_id)
            )
            updated_request = request_result.scalar_one()
            assert updated_request.status == "PENDING"

    @pytest.mark.asyncio
    async def test_atomicity_force_publish_and_request_update(
        self,
        registered_user,
    ):
        """
        Test that force-publish and request update are atomic.

        Scenario: Force-publish a note with associated request
        Expected: Both database updates succeed together (no partial state possible)
        """
        from src.users.models import User

        user_id = UUID(registered_user["id"])
        async with get_session_maker()() as session:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one()
            user.is_service_account = True
            await session.commit()

        note, request, _community_server = await create_note_with_request()

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            response = await client.post(f"/api/v2/notes/{note.id}/force-publish")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            note_result = await session.execute(select(Note).where(Note.id == note.id))
            updated_note = note_result.scalar_one()

            request_result = await session.execute(
                select(Request).where(Request.request_id == request.request_id)
            )
            updated_request = request_result.scalar_one()

            assert updated_note.force_published is True
            assert updated_note.status == "CURRENTLY_RATED_HELPFUL"
            assert updated_request.status == "COMPLETED"


class TestRequestStatusOnNoteCreation:
    """Test that request status is updated when notes are created via API."""

    @pytest.mark.asyncio
    async def test_note_creation_sets_request_to_in_progress(
        self,
        registered_user,
    ):
        """
        Test that creating a note via API sets the associated request to IN_PROGRESS.

        Scenario: User creates a note linked to an existing request
        Expected: Request status changes from PENDING to IN_PROGRESS
        """
        async with get_session_maker()() as session:
            community_server = CommunityServer(
                id=uuid4(),
                platform="discord",
                platform_id="test-server-note-create-123",
                name="Test Server for Note Creation",
                is_active=True,
            )
            session.add(community_server)
            await session.flush()

            request = Request(
                id=uuid4(),
                request_id=f"req_note_create_{uuid4()}",
                requested_by="test_user_002",
                status="PENDING",
                community_server_id=community_server.id,
            )
            session.add(request)
            await session.commit()
            await session.refresh(request)
            request_id = request.request_id
            community_server_id = community_server.id

        assert request.status == "PENDING"

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {"Authorization": f"Bearer {access_token}"}

        note_data = {
            "author_participant_id": "test_author_002",
            "summary": f"Test note to verify IN_PROGRESS status {uuid4().hex[:8]}",
            "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            "community_server_id": str(community_server_id),
            "request_id": request_id,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            response = await create_note_v2_request(client, note_data)
            assert response.status_code == 201

        async with get_session_maker()() as session:
            request_result = await session.execute(
                select(Request).where(Request.request_id == request_id)
            )
            updated_request = request_result.scalar_one()

            assert updated_request.status == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_note_creation_without_request_succeeds(
        self,
        registered_user,
    ):
        """
        Test that creating a note without a request_id still succeeds.

        Scenario: User creates a note not linked to any request
        Expected: Note is created successfully
        """
        async with get_session_maker()() as session:
            community_server = CommunityServer(
                id=uuid4(),
                platform="discord",
                platform_id="test-server-no-request-456",
                name="Test Server No Request",
                is_active=True,
            )
            session.add(community_server)
            await session.commit()
            await session.refresh(community_server)
            community_server_id = community_server.id

        token_data = {
            "sub": str(registered_user["id"]),
            "username": registered_user["username"],
            "role": registered_user["role"],
        }
        access_token = create_access_token(token_data)
        headers = {"Authorization": f"Bearer {access_token}"}

        note_data = {
            "author_participant_id": "test_author_003",
            "summary": f"Test note without request {uuid4().hex[:8]}",
            "classification": "NOT_MISLEADING",
            "community_server_id": str(community_server_id),
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            response = await create_note_v2_request(client, note_data)
            assert response.status_code == 201
            response_data = response.json()
            assert response_data["data"]["id"] is not None
