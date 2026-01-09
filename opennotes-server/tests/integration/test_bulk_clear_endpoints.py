"""Tests for bulk clear endpoints for community server admins.

These endpoints allow community server admins to clear out:
- Old note requests (all or older than X days)
- Unpublished notes (all or older than X days)

Reference: task-952
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note, Request
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile


@pytest.fixture
async def clear_test_community_server():
    """Create a test community server for clear endpoint tests."""
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            platform="discord",
            platform_community_server_id=f"test_guild_clear_{uuid4().hex[:8]}",
            name="Test Guild for Clear Endpoints",
            is_active=True,
        )
        db.add(community_server)
        await db.commit()
        await db.refresh(community_server)
        return community_server


@pytest.fixture
async def clear_test_admin_user(clear_test_community_server):
    """Create an admin user for the test community."""
    async with get_session_maker()() as db:
        discord_id = f"discord_{uuid4().hex[:8]}"
        user = User(
            email=f"admin_{uuid4().hex[:8]}@example.com",
            username=f"clearadmin_{uuid4().hex[:8]}",
            discord_id=discord_id,
            hashed_password="hashed_password",
            is_active=True,
            role="user",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        profile = UserProfile(
            display_name="Clear Test Admin",
            is_human=True,
            is_active=True,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=discord_id,
        )
        db.add(identity)

        member = CommunityMember(
            community_id=clear_test_community_server.id,
            profile_id=profile.id,
            role="admin",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        db.add(member)
        await db.commit()

        return {"user": user, "profile": profile}


@pytest.fixture
async def clear_test_regular_user(clear_test_community_server):
    """Create a regular (non-admin) user for the test community."""
    async with get_session_maker()() as db:
        discord_id = f"discord_{uuid4().hex[:8]}"
        user = User(
            email=f"regular_{uuid4().hex[:8]}@example.com",
            username=f"clearregular_{uuid4().hex[:8]}",
            discord_id=discord_id,
            hashed_password="hashed_password",
            is_active=True,
            role="user",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        profile = UserProfile(
            display_name="Clear Test Regular",
            is_human=True,
            is_active=True,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=discord_id,
        )
        db.add(identity)

        member = CommunityMember(
            community_id=clear_test_community_server.id,
            profile_id=profile.id,
            role="member",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        db.add(member)
        await db.commit()

        return {"user": user, "profile": profile}


@pytest.fixture
def admin_auth_headers(clear_test_admin_user):
    """Generate auth headers for admin user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(clear_test_admin_user["user"].id),
        "username": clear_test_admin_user["user"].username,
        "role": clear_test_admin_user["user"].role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def regular_auth_headers(clear_test_regular_user):
    """Generate auth headers for regular user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(clear_test_regular_user["user"].id),
        "username": clear_test_regular_user["user"].username,
        "role": clear_test_regular_user["user"].role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def sample_requests(clear_test_community_server, clear_test_admin_user):
    """Create sample requests with various ages."""
    async with get_session_maker()() as db:
        # Use naive datetime to match column type (timestamp without timezone)
        now = datetime.now(UTC).replace(tzinfo=None)
        requests = []

        # Recent request (1 day old)
        req1 = Request(
            request_id=f"req_recent_{uuid4().hex[:8]}",
            community_server_id=clear_test_community_server.id,
            requested_by="user1",
            requested_at=now - timedelta(days=1),
            status="PENDING",
        )
        requests.append(req1)

        # Old request (40 days old)
        req2 = Request(
            request_id=f"req_old_{uuid4().hex[:8]}",
            community_server_id=clear_test_community_server.id,
            requested_by="user2",
            requested_at=now - timedelta(days=40),
            status="PENDING",
        )
        requests.append(req2)

        # Very old request (100 days old)
        req3 = Request(
            request_id=f"req_very_old_{uuid4().hex[:8]}",
            community_server_id=clear_test_community_server.id,
            requested_by="user3",
            requested_at=now - timedelta(days=100),
            status="COMPLETED",
        )
        requests.append(req3)

        for req in requests:
            db.add(req)
        await db.commit()

        for req in requests:
            await db.refresh(req)

        return requests


@pytest.fixture
async def sample_notes(clear_test_community_server, clear_test_admin_user):
    """Create sample notes with various statuses and ages."""
    async with get_session_maker()() as db:
        # Use naive datetime to match column type (timestamp without timezone)
        now = datetime.now(UTC).replace(tzinfo=None)
        notes = []

        # Recent unpublished note (1 day old)
        note1 = Note(
            community_server_id=clear_test_community_server.id,
            author_participant_id="author1",
            author_profile_id=clear_test_admin_user["profile"].id,
            summary="Recent unpublished note",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            force_published=False,
        )
        notes.append(note1)

        # Old unpublished note (40 days old)
        note2 = Note(
            community_server_id=clear_test_community_server.id,
            author_participant_id="author2",
            author_profile_id=clear_test_admin_user["profile"].id,
            summary="Old unpublished note",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            force_published=False,
        )
        notes.append(note2)

        # Published note (should NOT be deleted)
        note3 = Note(
            community_server_id=clear_test_community_server.id,
            author_participant_id="author3",
            author_profile_id=clear_test_admin_user["profile"].id,
            summary="Published helpful note",
            classification="NOT_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            force_published=False,
        )
        notes.append(note3)

        # Force-published note (should NOT be deleted)
        note4 = Note(
            community_server_id=clear_test_community_server.id,
            author_participant_id="author4",
            author_profile_id=clear_test_admin_user["profile"].id,
            summary="Force-published note",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            force_published=True,
        )
        notes.append(note4)

        for note in notes:
            db.add(note)
        await db.commit()

        for note in notes:
            await db.refresh(note)

        # Manually update created_at for note2 to simulate old note
        await db.execute(
            Note.__table__.update()
            .where(Note.id == note2.id)
            .values(created_at=now - timedelta(days=40))
        )
        await db.commit()

        return notes


class TestClearRequestsEndpoint:
    """Tests for DELETE /api/v2/community-servers/{id}/clear-requests endpoint."""

    @pytest.mark.asyncio
    async def test_clear_all_requests_as_admin(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_requests,
    ):
        """Admin can clear all requests for their community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-requests",
                headers=admin_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["deleted_count"] == 3
            assert "requests" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_clear_requests_older_than_days(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_requests,
    ):
        """Admin can clear requests older than specified days."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-requests",
                headers=admin_auth_headers,
                params={"mode": "30"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["deleted_count"] == 2

        async with get_session_maker()() as db:
            result = await db.execute(
                select(Request).where(Request.community_server_id == clear_test_community_server.id)
            )
            remaining = result.scalars().all()
            assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_clear_requests_requires_admin(
        self,
        clear_test_community_server,
        regular_auth_headers,
        sample_requests,
    ):
        """Non-admin users cannot clear requests."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-requests",
                headers=regular_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_clear_requests_requires_auth(
        self,
        clear_test_community_server,
        sample_requests,
    ):
        """Unauthenticated users cannot clear requests."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-requests",
                params={"mode": "all"},
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_clear_requests_invalid_mode(
        self,
        clear_test_community_server,
        admin_auth_headers,
    ):
        """Invalid mode parameter returns 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-requests",
                headers=admin_auth_headers,
                params={"mode": "invalid"},
            )

            assert response.status_code == 422


class TestClearNotesEndpoint:
    """Tests for DELETE /api/v2/community-servers/{id}/clear-notes endpoint."""

    @pytest.mark.asyncio
    async def test_clear_all_unpublished_notes_as_admin(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_notes,
    ):
        """Admin can clear all unpublished notes for their community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes",
                headers=admin_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["deleted_count"] == 2

        async with get_session_maker()() as db:
            result = await db.execute(
                select(Note).where(Note.community_server_id == clear_test_community_server.id)
            )
            remaining = result.scalars().all()
            assert len(remaining) == 2
            for note in remaining:
                assert note.status == "CURRENTLY_RATED_HELPFUL" or note.force_published

    @pytest.mark.asyncio
    async def test_clear_notes_older_than_days(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_notes,
    ):
        """Admin can clear unpublished notes older than specified days."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes",
                headers=admin_auth_headers,
                params={"mode": "30"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["deleted_count"] == 1

    @pytest.mark.asyncio
    async def test_clear_notes_preserves_published(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_notes,
    ):
        """Clear notes preserves published notes even with mode=all."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes",
                headers=admin_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 200

        async with get_session_maker()() as db:
            result = await db.execute(select(Note).where(Note.status == "CURRENTLY_RATED_HELPFUL"))
            published = result.scalars().all()
            assert len(published) >= 1

    @pytest.mark.asyncio
    async def test_clear_notes_preserves_force_published(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_notes,
    ):
        """Clear notes preserves force-published notes even with mode=all."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes",
                headers=admin_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 200

        async with get_session_maker()() as db:
            result = await db.execute(select(Note).where(Note.force_published == True))
            force_published = result.scalars().all()
            assert len(force_published) >= 1

    @pytest.mark.asyncio
    async def test_clear_notes_requires_admin(
        self,
        clear_test_community_server,
        regular_auth_headers,
        sample_notes,
    ):
        """Non-admin users cannot clear notes."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes",
                headers=regular_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_clear_notes_requires_auth(
        self,
        clear_test_community_server,
        sample_notes,
    ):
        """Unauthenticated users cannot clear notes."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes",
                params={"mode": "all"},
            )

            assert response.status_code == 401


class TestClearEndpointsPreview:
    """Tests for preview mode (dry run) of clear endpoints."""

    @pytest.mark.asyncio
    async def test_preview_clear_requests(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_requests,
    ):
        """Preview mode returns count without deleting."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-requests/preview",
                headers=admin_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["would_delete_count"] == 3

        async with get_session_maker()() as db:
            result = await db.execute(
                select(Request).where(Request.community_server_id == clear_test_community_server.id)
            )
            remaining = result.scalars().all()
            assert len(remaining) == 3

    @pytest.mark.asyncio
    async def test_preview_clear_notes(
        self,
        clear_test_community_server,
        admin_auth_headers,
        sample_notes,
    ):
        """Preview mode returns count of unpublished notes without deleting."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/community-servers/{clear_test_community_server.id}/clear-notes/preview",
                headers=admin_auth_headers,
                params={"mode": "all"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["would_delete_count"] == 2

        async with get_session_maker()() as db:
            result = await db.execute(
                select(Note).where(Note.community_server_id == clear_test_community_server.id)
            )
            remaining = result.scalars().all()
            assert len(remaining) == 4
