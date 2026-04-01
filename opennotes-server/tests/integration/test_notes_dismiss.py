"""
Integration tests for the dismiss note endpoint.

Tests that POST /api/v2/notes/{note_id}/dismiss:
- Sets note status to CURRENTLY_RATED_NOT_HELPFUL
- Sets associated request status to COMPLETED
- Requires admin auth (403 for non-admin)
- Returns 404 for non-existent note
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.auth import create_access_token
from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note, Request
from src.users.models import User
from src.users.profile_models import CommunityMember, UserProfile

pytestmark = pytest.mark.integration


def _mark_app_ready() -> None:
    """Set startup_complete on the app state so the startup gate allows requests through.

    In integration tests, AsyncClient with ASGITransport does NOT trigger the ASGI
    lifespan (that requires TestClient.__enter__). We bypass the startup gate here
    because we are testing endpoint logic, not the startup sequence.
    """
    app.state.startup_complete = True
    app.state.startup_failed = False


async def _create_admin_user_and_headers(community_server_id: UUID) -> tuple[User, dict[str, str]]:
    """Create a service-account user that is an admin of the given community server.

    Returns the User object and JWT auth headers.
    """
    from src.auth.password import get_password_hash

    ts = datetime.now(tz=UTC).timestamp()
    async with get_session_maker()() as session:
        user = User(
            id=uuid4(),
            username=f"dismiss_admin_{ts:.0f}_{uuid4().hex[:4]}",
            email=f"dismiss_admin_{ts:.0f}_{uuid4().hex[:4]}@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Dismiss Admin User",
            role="user",
            is_active=True,
            is_service_account=True,
        )
        session.add(user)
        await session.flush()

        profile = UserProfile(
            display_name="Dismiss Admin Profile",
            is_human=True,
            is_active=True,
        )
        session.add(profile)
        await session.flush()

        member = CommunityMember(
            community_id=community_server_id,
            profile_id=profile.id,
            role="admin",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        session.add(member)

        await session.commit()
        await session.refresh(user)

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    token = create_access_token(token_data)
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


async def _create_non_admin_user_headers() -> dict[str, str]:
    """Create a regular (non-admin, non-service-account) user and return JWT headers."""
    from src.auth.password import get_password_hash

    ts = datetime.now(tz=UTC).timestamp()
    async with get_session_maker()() as session:
        user = User(
            id=uuid4(),
            username=f"dismiss_nonadmin_{ts:.0f}_{uuid4().hex[:4]}",
            email=f"dismiss_nonadmin_{ts:.0f}_{uuid4().hex[:4]}@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Non-Admin User",
            role="user",
            is_active=True,
            is_service_account=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


async def _create_community_server() -> CommunityServer:
    """Create and persist a community server."""
    async with get_session_maker()() as session:
        community_server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id=f"dismiss-server-{uuid4().hex[:8]}",
            name="Dismiss Test Server",
            is_active=True,
        )
        session.add(community_server)
        await session.commit()
        await session.refresh(community_server)
        return community_server


async def _create_note_with_request(
    community_server_id: UUID,
) -> tuple[Note, Request]:
    """Create a test note with an associated PENDING request."""
    async with get_session_maker()() as session:
        author_profile = UserProfile(
            display_name=f"Dismiss Author {uuid4().hex[:6]}",
            is_human=True,
            is_active=True,
        )
        session.add(author_profile)
        await session.flush()

        associated_request = Request(
            id=uuid4(),
            request_id=f"req_dismiss_{uuid4()}",
            requested_by="dismiss_test_user",
            status="PENDING",
            community_server_id=community_server_id,
        )
        session.add(associated_request)
        await session.flush()

        note = Note(
            id=uuid4(),
            author_id=author_profile.id,
            summary=f"Dismiss test note {uuid4().hex[:8]}",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            community_server_id=community_server_id,
            request_id=associated_request.id,
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        await session.refresh(associated_request)
        return note, associated_request


async def _create_note_without_request(community_server_id: UUID) -> Note:
    """Create a test note with no associated request."""
    async with get_session_maker()() as session:
        author_profile = UserProfile(
            display_name=f"Dismiss Author No Req {uuid4().hex[:6]}",
            is_human=True,
            is_active=True,
        )
        session.add(author_profile)
        await session.flush()

        note = Note(
            id=uuid4(),
            author_id=author_profile.id,
            summary=f"Dismiss test note no request {uuid4().hex[:8]}",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            community_server_id=community_server_id,
            request_id=None,
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        return note


class TestDismissNoteStatus:
    """Test that dismiss sets note status to CURRENTLY_RATED_NOT_HELPFUL."""

    @pytest.mark.asyncio
    async def test_dismiss_sets_note_status_not_helpful(self):
        """Dismissing a note sets its status to CURRENTLY_RATED_NOT_HELPFUL."""
        server = await _create_community_server()
        _admin_user, headers = await _create_admin_user_and_headers(server.id)
        note, _req = await _create_note_with_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == note.id))
            updated_note = result.scalar_one()
            assert updated_note.status == "CURRENTLY_RATED_NOT_HELPFUL"

    @pytest.mark.asyncio
    async def test_dismiss_sets_force_published_true(self):
        """Dismissing a note sets force_published=True (admin override flag)."""
        server = await _create_community_server()
        _admin_user, headers = await _create_admin_user_and_headers(server.id)
        note, _req = await _create_note_with_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == note.id))
            updated_note = result.scalar_one()
            assert updated_note.force_published is True


class TestDismissRequestStatus:
    """Test that dismiss sets associated request to COMPLETED."""

    @pytest.mark.asyncio
    async def test_dismiss_sets_request_to_completed(self):
        """Dismissing a note with an associated request sets request.status to COMPLETED."""
        server = await _create_community_server()
        _admin_user, headers = await _create_admin_user_and_headers(server.id)
        note, associated_request = await _create_note_with_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            result = await session.execute(
                select(Request).where(Request.request_id == associated_request.request_id)
            )
            updated_request = result.scalar_one()
            assert updated_request.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_dismiss_without_request_succeeds(self):
        """Dismissing a note with no associated request still succeeds."""
        server = await _create_community_server()
        _admin_user, headers = await _create_admin_user_and_headers(server.id)
        note = await _create_note_without_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == note.id))
            updated_note = result.scalar_one()
            assert updated_note.status == "CURRENTLY_RATED_NOT_HELPFUL"
            assert updated_note.force_published is True

    @pytest.mark.asyncio
    async def test_dismiss_atomicity(self):
        """Both note status and request status are updated in the same transaction."""
        server = await _create_community_server()
        _admin_user, headers = await _create_admin_user_and_headers(server.id)
        note, associated_request = await _create_note_with_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code == 200

        async with get_session_maker()() as session:
            note_result = await session.execute(select(Note).where(Note.id == note.id))
            updated_note = note_result.scalar_one()

            req_result = await session.execute(
                select(Request).where(Request.request_id == associated_request.request_id)
            )
            updated_request = req_result.scalar_one()

            assert updated_note.force_published is True
            assert updated_note.status == "CURRENTLY_RATED_NOT_HELPFUL"
            assert updated_request.status == "COMPLETED"


class TestDismissAuthorization:
    """Test that dismiss requires admin authorization."""

    @pytest.mark.asyncio
    async def test_dismiss_requires_admin_auth(self):
        """Non-admin users receive 403 when attempting to dismiss a note."""
        server = await _create_community_server()
        headers = await _create_non_admin_user_headers()
        note, _req = await _create_note_with_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code == 403, (
                f"Expected 403 for non-admin, got {response.status_code}: {response.text}"
            )

    @pytest.mark.asyncio
    async def test_dismiss_requires_auth_token(self):
        """Unauthenticated requests are rejected."""
        server = await _create_community_server()
        note, _req = await _create_note_with_request(server.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{note.id}/dismiss")
            assert response.status_code in (401, 403), (
                f"Expected 401 or 403 for unauthenticated request, got {response.status_code}: {response.text}"
            )
            assert response.status_code != 200, "Unauthenticated request must not succeed"


class TestDismissNotFound:
    """Test that dismiss returns 404 for non-existent notes."""

    @pytest.mark.asyncio
    async def test_dismiss_nonexistent_note_returns_404(self):
        """Dismissing a note that does not exist returns 404."""
        server = await _create_community_server()
        _admin_user, headers = await _create_admin_user_and_headers(server.id)
        nonexistent_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as client:
            _mark_app_ready()
            response = await client.post(f"/api/v2/notes/{nonexistent_id}/dismiss")
            assert response.status_code == 404, (
                f"Expected 404 for non-existent note, got {response.status_code}: {response.text}"
            )
