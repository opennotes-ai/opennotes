"""
Integration tests for authorization enforcement across API endpoints.

These tests verify that:
1. Cross-community access is properly prevented
2. Resource ownership is enforced on mutation endpoints
3. Admin override allows community admins to modify resources
4. Service accounts can access all resources

Task: task-713 AC #5
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.main import app
from src.notes.schemas import HelpfulnessLevel, NoteClassification


class TestAuthorizationFixtures:
    """Fixtures for authorization testing scenarios."""

    @pytest.fixture
    async def community_a(self, db):
        """Create Community A for authorization tests."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id="auth_test_community_a",
            name="Authorization Test Community A",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.fixture
    async def community_b(self, db):
        """Create Community B for authorization tests."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id="auth_test_community_b",
            name="Authorization Test Community B",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.fixture
    async def user_a_in_community_a(self, db, community_a):
        """
        Create User A with profile and membership in Community A.

        This user:
        - Has a user account (User model)
        - Has a profile (UserProfile model)
        - Has an identity (UserIdentity model)
        - Is a member of Community A (CommunityMember model)
        """
        from src.users.models import User
        from src.users.profile_crud import create_community_member, create_profile_with_identity
        from src.users.profile_schemas import (
            AuthProvider,
            CommunityMemberCreate,
            CommunityRole,
            UserProfileCreate,
        )

        user = User(
            id=uuid4(),
            username="user_a_auth_test",
            email="user_a_auth@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_user_a_auth",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="User A Auth Test",
            avatar_url=None,
            bio="Test user A for authorization tests",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id=user.discord_id,
            credentials=None,
        )

        member_create = CommunityMemberCreate(
            community_id=community_a.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test fixture for authorization tests",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": community_a,
        }

    @pytest.fixture
    async def user_b_in_community_b(self, db, community_b):
        """
        Create User B with profile and membership in Community B.

        This user is in a DIFFERENT community than User A.
        """
        from src.users.models import User
        from src.users.profile_crud import create_community_member, create_profile_with_identity
        from src.users.profile_schemas import (
            AuthProvider,
            CommunityMemberCreate,
            CommunityRole,
            UserProfileCreate,
        )

        user = User(
            id=uuid4(),
            username="user_b_auth_test",
            email="user_b_auth@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_user_b_auth",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="User B Auth Test",
            avatar_url=None,
            bio="Test user B for authorization tests",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id=user.discord_id,
            credentials=None,
        )

        member_create = CommunityMemberCreate(
            community_id=community_b.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test fixture for authorization tests",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": community_b,
        }

    @pytest.fixture
    async def admin_user_in_community_a(self, db, community_a):
        """
        Create an admin user with admin role in Community A.

        This user can modify any resource in Community A.
        """
        from src.users.models import User
        from src.users.profile_crud import create_community_member, create_profile_with_identity
        from src.users.profile_schemas import (
            AuthProvider,
            CommunityMemberCreate,
            CommunityRole,
            UserProfileCreate,
        )

        user = User(
            id=uuid4(),
            username="admin_a_auth_test",
            email="admin_a_auth@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_admin_a_auth",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Admin A Auth Test",
            avatar_url=None,
            bio="Admin user for Community A authorization tests",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id=user.discord_id,
            credentials=None,
        )

        member_create = CommunityMemberCreate(
            community_id=community_a.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Admin fixture for authorization tests",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": community_a,
        }

    @pytest.fixture
    async def service_account_user(self, db):
        """
        Create a service account user.

        Service accounts can access all resources in any community.
        """
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="bot-service",
            email="bot@opennotes.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=True,
            discord_id="discord_bot_service",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return {"user": user}

    def _create_auth_headers(self, user_data):
        """Create auth headers for a user."""
        user = user_data["user"]
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    def user_a_headers(self, user_a_in_community_a):
        """Auth headers for User A."""
        return self._create_auth_headers(user_a_in_community_a)

    @pytest.fixture
    def user_b_headers(self, user_b_in_community_b):
        """Auth headers for User B."""
        return self._create_auth_headers(user_b_in_community_b)

    @pytest.fixture
    def admin_headers(self, admin_user_in_community_a):
        """Auth headers for Admin in Community A."""
        return self._create_auth_headers(admin_user_in_community_a)

    @pytest.fixture
    def service_account_headers(self, service_account_user):
        """Auth headers for service account."""
        return self._create_auth_headers(service_account_user)

    @pytest.fixture
    async def note_in_community_a(self, db, community_a, user_a_in_community_a):
        """Create a note in Community A owned by User A."""
        from src.notes.message_archive_models import ContentType, MessageArchive
        from src.notes.models import Note, Request

        message_archive = MessageArchive(
            id=uuid4(),
            content_type=ContentType.TEXT,
            content_text="Test note content in Community A",
            platform_message_id=str(int(datetime.now(UTC).timestamp() * 1000000)),
            platform_channel_id="auth_test_channel_a",
            platform_author_id=user_a_in_community_a["user"].discord_id,
        )
        db.add(message_archive)
        await db.flush()

        request = Request(
            id=uuid4(),
            request_id=f"auth_test_request_{uuid4().hex[:8]}",
            requested_by=user_a_in_community_a["user"].discord_id,
            message_archive_id=message_archive.id,
            community_server_id=community_a.id,
            status="PENDING",
        )
        db.add(request)
        await db.flush()

        note = Note(
            id=uuid4(),
            request_id=request.request_id,
            classification=NoteClassification.NOT_MISLEADING,
            summary="Test note in Community A for authorization tests",
            author_participant_id=user_a_in_community_a["user"].discord_id,
            author_profile_id=user_a_in_community_a["profile"].id,
            community_server_id=community_a.id,
            status="NEEDS_MORE_RATINGS",
        )
        db.add(note)
        await db.commit()
        await db.refresh(note)
        return note

    @pytest.fixture
    async def note_in_community_b(self, db, community_b, user_b_in_community_b):
        """Create a note in Community B owned by User B."""
        from src.notes.message_archive_models import ContentType, MessageArchive
        from src.notes.models import Note, Request

        message_archive = MessageArchive(
            id=uuid4(),
            content_type=ContentType.TEXT,
            content_text="Test note content in Community B",
            platform_message_id=str(int(datetime.now(UTC).timestamp() * 1000000) + 1),
            platform_channel_id="auth_test_channel_b",
            platform_author_id=user_b_in_community_b["user"].discord_id,
        )
        db.add(message_archive)
        await db.flush()

        request = Request(
            id=uuid4(),
            request_id=f"auth_test_request_b_{uuid4().hex[:8]}",
            requested_by=user_b_in_community_b["user"].discord_id,
            message_archive_id=message_archive.id,
            community_server_id=community_b.id,
            status="PENDING",
        )
        db.add(request)
        await db.flush()

        note = Note(
            id=uuid4(),
            request_id=request.request_id,
            classification=NoteClassification.MISINFORMED_OR_POTENTIALLY_MISLEADING,
            summary="Test note in Community B for authorization tests",
            author_participant_id=user_b_in_community_b["user"].discord_id,
            author_profile_id=user_b_in_community_b["profile"].id,
            community_server_id=community_b.id,
            status="NEEDS_MORE_RATINGS",
        )
        db.add(note)
        await db.commit()
        await db.refresh(note)
        return note

    @pytest.fixture
    async def rating_in_community_a(self, db, note_in_community_a, user_a_in_community_a):
        """Create a rating for the note in Community A by User A."""
        from src.notes.models import Rating

        rating = Rating(
            id=uuid4(),
            note_id=note_in_community_a.id,
            rater_participant_id=user_a_in_community_a["user"].discord_id,
            rater_profile_id=user_a_in_community_a["profile"].id,
            helpfulness_level=HelpfulnessLevel.HELPFUL,
        )
        db.add(rating)
        await db.commit()
        await db.refresh(rating)
        return rating

    @pytest.fixture
    async def request_in_community_a(self, db, community_a, user_a_in_community_a):
        """Create a request in Community A by User A."""
        from src.notes.message_archive_models import ContentType, MessageArchive
        from src.notes.models import Request

        message_archive = MessageArchive(
            id=uuid4(),
            content_type=ContentType.TEXT,
            content_text="Test message for authorization tests",
            platform_message_id="auth_test_msg_001",
            platform_channel_id="auth_test_channel",
            platform_author_id=user_a_in_community_a["user"].discord_id,
        )
        db.add(message_archive)
        await db.flush()

        request = Request(
            id=uuid4(),
            request_id="auth_test_request_001",
            requested_by=user_a_in_community_a["user"].discord_id,
            message_archive_id=message_archive.id,
            community_server_id=community_a.id,
            status="PENDING",
        )
        db.add(request)
        await db.commit()
        await db.refresh(request)
        return request


class TestCrossCommunityAccessPrevention(TestAuthorizationFixtures):
    """Tests that users cannot access resources in communities they are not members of."""

    @pytest.mark.asyncio
    async def test_user_cannot_get_notes_from_other_community(
        self,
        user_b_headers,
        community_a,
        note_in_community_a,
    ):
        """User B (in Community B) cannot list notes from Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/notes?filter[community_server_id]={community_a.id}",
                headers=user_b_headers,
            )

            assert response.status_code == 403
            assert "not a member" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_get_note_by_id_from_other_community(
        self,
        user_b_headers,
        note_in_community_a,
    ):
        """User B (in Community B) cannot get a specific note from Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=user_b_headers,
            )

            assert response.status_code == 403
            assert "not a member" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_get_requests_from_other_community(
        self,
        user_b_headers,
        community_a,
        request_in_community_a,
    ):
        """User B (in Community B) cannot list requests from Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/requests?filter[community_server_id]={community_a.id}",
                headers=user_b_headers,
            )

            assert response.status_code == 403
            assert "not a member" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_get_request_by_id_from_other_community(
        self,
        user_b_headers,
        request_in_community_a,
    ):
        """User B (in Community B) cannot get a specific request from Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/requests/{request_in_community_a.request_id}",
                headers=user_b_headers,
            )

            assert response.status_code == 403
            assert "not a member" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_get_ratings_from_other_community(
        self,
        user_b_headers,
        note_in_community_a,
        rating_in_community_a,
    ):
        """User B (in Community B) cannot get ratings for a note in Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/notes/{note_in_community_a.id}/ratings",
                headers=user_b_headers,
            )

            assert response.status_code == 403
            assert "not a member" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_with_no_communities_gets_empty_list(
        self,
        db,
    ):
        """User with no community memberships gets empty list of notes."""
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="orphan_user_auth_test",
            email="orphan_auth@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_orphan_auth",
        )
        db.add(user)
        await db.commit()

        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        headers = {"Authorization": f"Bearer {access_token}"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v2/notes",
                headers=headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["meta"]["count"] == 0


class TestOwnershipEnforcement(TestAuthorizationFixtures):
    """Tests that users cannot modify resources they don't own."""

    @pytest.mark.asyncio
    async def test_user_cannot_patch_note_they_dont_own(
        self,
        user_b_headers,
        note_in_community_a,
        user_b_in_community_b,
        db,
        community_a,
    ):
        """User B cannot PATCH a note owned by User A even if given access to the community."""
        from src.users.profile_crud import create_community_member
        from src.users.profile_schemas import CommunityMemberCreate, CommunityRole

        member_create = CommunityMemberCreate(
            community_id=community_a.id,
            profile_id=user_b_in_community_b["profile"].id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test fixture for ownership test",
        )
        await create_community_member(db, member_create)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=user_b_headers,
                json={
                    "data": {
                        "type": "notes",
                        "id": str(note_in_community_a.id),
                        "attributes": {"summary": "Unauthorized update attempt"},
                    }
                },
            )

            assert response.status_code == 403
            assert "do not have permission" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_delete_note_they_dont_own(
        self,
        user_b_headers,
        note_in_community_a,
        user_b_in_community_b,
        db,
        community_a,
    ):
        """User B cannot DELETE a note owned by User A even if given access to the community."""
        from src.users.profile_crud import create_community_member
        from src.users.profile_schemas import CommunityMemberCreate, CommunityRole

        member_create = CommunityMemberCreate(
            community_id=community_a.id,
            profile_id=user_b_in_community_b["profile"].id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test fixture for ownership test",
        )
        await create_community_member(db, member_create)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=user_b_headers,
            )

            assert response.status_code == 403
            assert "do not have permission" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_put_rating_they_dont_own(
        self,
        user_b_headers,
        rating_in_community_a,
        user_b_in_community_b,
        db,
        community_a,
    ):
        """User B cannot PUT (update) a rating owned by User A even if in the community."""
        from src.users.profile_crud import create_community_member
        from src.users.profile_schemas import CommunityMemberCreate, CommunityRole

        member_create = CommunityMemberCreate(
            community_id=community_a.id,
            profile_id=user_b_in_community_b["profile"].id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test fixture for ownership test",
        )
        await create_community_member(db, member_create)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/v2/ratings/{rating_in_community_a.id}",
                headers=user_b_headers,
                json={
                    "data": {
                        "type": "ratings",
                        "id": str(rating_in_community_a.id),
                        "attributes": {"helpfulness_level": HelpfulnessLevel.NOT_HELPFUL},
                    }
                },
            )

            assert response.status_code == 403
            error_response = response.json()
            assert "errors" in error_response
            assert error_response["errors"][0]["status"] == "403"
            assert "do not have permission" in error_response["errors"][0]["detail"].lower()

    @pytest.mark.asyncio
    async def test_user_cannot_patch_request_they_dont_own(
        self,
        user_b_headers,
        request_in_community_a,
        user_b_in_community_b,
        db,
        community_a,
    ):
        """User B cannot PATCH a request owned by User A even if in the community."""
        from src.users.profile_crud import create_community_member
        from src.users.profile_schemas import CommunityMemberCreate, CommunityRole

        member_create = CommunityMemberCreate(
            community_id=community_a.id,
            profile_id=user_b_in_community_b["profile"].id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Test fixture for ownership test",
        )
        await create_community_member(db, member_create)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/requests/{request_in_community_a.request_id}",
                headers=user_b_headers,
                json={
                    "data": {
                        "type": "requests",
                        "id": request_in_community_a.request_id,
                        "attributes": {"status": "IN_PROGRESS"},
                    }
                },
            )

            assert response.status_code == 403
            assert "do not have permission" in response.json()["detail"].lower()


class TestPositiveAuthorizationSuccess(TestAuthorizationFixtures):
    """Tests that authorized users CAN access/modify resources."""

    @pytest.mark.asyncio
    async def test_owner_can_get_their_own_note(
        self,
        user_a_headers,
        note_in_community_a,
    ):
        """User A can GET their own note in their community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=user_a_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == str(note_in_community_a.id)

    @pytest.mark.asyncio
    async def test_owner_can_patch_their_own_note(
        self,
        user_a_headers,
        note_in_community_a,
    ):
        """User A can PATCH their own note."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=user_a_headers,
                json={
                    "data": {
                        "type": "notes",
                        "id": str(note_in_community_a.id),
                        "attributes": {"summary": "Updated by owner"},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["summary"] == "Updated by owner"

    @pytest.mark.asyncio
    async def test_owner_can_delete_their_own_note(
        self,
        user_a_headers,
        note_in_community_a,
    ):
        """User A can DELETE their own note."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=user_a_headers,
            )

            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_owner_can_update_their_own_rating(
        self,
        user_a_headers,
        rating_in_community_a,
    ):
        """User A can PUT (update) their own rating."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/v2/ratings/{rating_in_community_a.id}",
                headers=user_a_headers,
                json={
                    "data": {
                        "type": "ratings",
                        "id": str(rating_in_community_a.id),
                        "attributes": {"helpfulness_level": HelpfulnessLevel.NOT_HELPFUL},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["helpfulness_level"] == HelpfulnessLevel.NOT_HELPFUL

    @pytest.mark.asyncio
    async def test_owner_can_patch_their_own_request(
        self,
        user_a_headers,
        request_in_community_a,
    ):
        """User A can PATCH their own request."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/requests/{request_in_community_a.request_id}",
                headers=user_a_headers,
                json={
                    "data": {
                        "type": "requests",
                        "id": request_in_community_a.request_id,
                        "attributes": {"status": "IN_PROGRESS"},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_admin_can_patch_any_note_in_community(
        self,
        admin_headers,
        note_in_community_a,
    ):
        """Admin in Community A can PATCH any note in that community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=admin_headers,
                json={
                    "data": {
                        "type": "notes",
                        "id": str(note_in_community_a.id),
                        "attributes": {"summary": "Updated by admin"},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["summary"] == "Updated by admin"

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_note_in_community(
        self,
        admin_headers,
        note_in_community_a,
    ):
        """Admin in Community A can DELETE any note in that community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=admin_headers,
            )

            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_admin_can_update_any_rating_in_community(
        self,
        admin_headers,
        rating_in_community_a,
    ):
        """Admin in Community A can PUT any rating in that community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/v2/ratings/{rating_in_community_a.id}",
                headers=admin_headers,
                json={
                    "data": {
                        "type": "ratings",
                        "id": str(rating_in_community_a.id),
                        "attributes": {"helpfulness_level": HelpfulnessLevel.SOMEWHAT_HELPFUL},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert (
                data["data"]["attributes"]["helpfulness_level"] == HelpfulnessLevel.SOMEWHAT_HELPFUL
            )

    @pytest.mark.asyncio
    async def test_admin_can_patch_any_request_in_community(
        self,
        admin_headers,
        request_in_community_a,
    ):
        """Admin in Community A can PATCH any request in that community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/requests/{request_in_community_a.request_id}",
                headers=admin_headers,
                json={
                    "data": {
                        "type": "requests",
                        "id": request_in_community_a.request_id,
                        "attributes": {"status": "COMPLETED"},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["status"] == "COMPLETED"


class TestServiceAccountBypass(TestAuthorizationFixtures):
    """Tests that service accounts can access all resources."""

    @pytest.mark.asyncio
    async def test_service_account_can_access_any_community_notes(
        self,
        service_account_headers,
        note_in_community_a,
        note_in_community_b,
    ):
        """Service account can list notes from any community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v2/notes",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["meta"]["count"] >= 2

    @pytest.mark.asyncio
    async def test_service_account_can_get_note_from_any_community(
        self,
        service_account_headers,
        note_in_community_a,
    ):
        """Service account can GET a note from any community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == str(note_in_community_a.id)

    @pytest.mark.asyncio
    async def test_service_account_can_patch_any_note(
        self,
        service_account_headers,
        note_in_community_a,
    ):
        """Service account can PATCH any note regardless of ownership."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=service_account_headers,
                json={
                    "data": {
                        "type": "notes",
                        "id": str(note_in_community_a.id),
                        "attributes": {"summary": "Updated by service account"},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["summary"] == "Updated by service account"

    @pytest.mark.asyncio
    async def test_service_account_can_delete_any_note(
        self,
        service_account_headers,
        note_in_community_a,
    ):
        """Service account can DELETE any note regardless of ownership."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v2/notes/{note_in_community_a.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_service_account_can_update_any_rating(
        self,
        service_account_headers,
        rating_in_community_a,
    ):
        """Service account can PUT any rating regardless of ownership."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/v2/ratings/{rating_in_community_a.id}",
                headers=service_account_headers,
                json={
                    "data": {
                        "type": "ratings",
                        "id": str(rating_in_community_a.id),
                        "attributes": {"helpfulness_level": HelpfulnessLevel.HELPFUL},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["helpfulness_level"] == HelpfulnessLevel.HELPFUL

    @pytest.mark.asyncio
    async def test_service_account_can_patch_any_request(
        self,
        service_account_headers,
        request_in_community_a,
    ):
        """Service account can PATCH any request regardless of ownership."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/requests/{request_in_community_a.request_id}",
                headers=service_account_headers,
                json={
                    "data": {
                        "type": "requests",
                        "id": request_in_community_a.request_id,
                        "attributes": {"status": "IN_PROGRESS"},
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_service_account_can_access_requests_from_any_community(
        self,
        service_account_headers,
        request_in_community_a,
    ):
        """Service account can GET a request from any community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/requests/{request_in_community_a.request_id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["request_id"] == request_in_community_a.request_id


class TestAdminCannotAccessOtherCommunities(TestAuthorizationFixtures):
    """Tests that admin privileges are scoped to their community only."""

    @pytest.mark.asyncio
    async def test_admin_in_community_a_cannot_patch_note_in_community_b(
        self,
        admin_headers,
        note_in_community_b,
    ):
        """Admin in Community A cannot PATCH a note in Community B."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/notes/{note_in_community_b.id}",
                headers=admin_headers,
                json={
                    "data": {
                        "type": "notes",
                        "id": str(note_in_community_b.id),
                        "attributes": {"summary": "Unauthorized admin update"},
                    }
                },
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_in_community_a_cannot_get_note_in_community_b(
        self,
        admin_headers,
        note_in_community_b,
    ):
        """Admin in Community A cannot GET a note in Community B."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/notes/{note_in_community_b.id}",
                headers=admin_headers,
            )

            assert response.status_code == 403
            assert "not a member" in response.json()["detail"].lower()
