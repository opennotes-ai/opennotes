"""
Integration tests for Bulk Content Scan API authorization.

These tests verify that:
1. POST /scans endpoint requires user to be admin of target community_server
2. GET /scans/{id} endpoint verifies user has access to the scan's community
3. JSON:API endpoints have equivalent authorization checks
4. Unauthorized requests return 403 Forbidden with appropriate error message
5. Authorization tests cover both success and failure cases

Task: task-849.01
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.main import app


class TestBulkScanAuthorizationFixtures:
    """Fixtures for bulk scan authorization testing scenarios."""

    @pytest.fixture
    async def community_a(self, db):
        """Create Community A for authorization tests."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id="bulk_scan_auth_test_community_a",
            name="Bulk Scan Auth Test Community A",
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
            platform_id="bulk_scan_auth_test_community_b",
            name="Bulk Scan Auth Test Community B",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.fixture
    async def regular_user_in_community_a(self, db, community_a):
        """
        Create a regular (non-admin) user with membership in Community A.
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
            username="bulk_scan_regular_user_a",
            email="bulk_scan_regular_a@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_bulk_scan_regular_a",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Bulk Scan Regular User A",
            avatar_url=None,
            bio="Regular user in Community A for bulk scan tests",
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
            invitation_reason="Test fixture for bulk scan authorization tests",
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
    async def admin_user_in_community_a(self, db, community_a):
        """
        Create an admin user with admin role in Community A.
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
            username="bulk_scan_admin_user_a",
            email="bulk_scan_admin_a@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_bulk_scan_admin_a",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Bulk Scan Admin User A",
            avatar_url=None,
            bio="Admin user in Community A for bulk scan tests",
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
            invitation_reason="Admin fixture for bulk scan authorization tests",
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
    async def admin_user_in_community_b(self, db, community_b):
        """
        Create an admin user with admin role in Community B (different community).
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
            username="bulk_scan_admin_user_b",
            email="bulk_scan_admin_b@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_bulk_scan_admin_b",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Bulk Scan Admin User B",
            avatar_url=None,
            bio="Admin user in Community B for bulk scan tests",
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
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Admin fixture for bulk scan authorization tests",
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
    async def service_account_user(self, db):
        """
        Create a service account user.
        Service accounts can access all resources in any community.
        """
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="bulk-scan-service",
            email="bulk-scan-bot@opennotes.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=True,
            discord_id="discord_bulk_scan_bot_service",
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
    def regular_user_headers(self, regular_user_in_community_a):
        """Auth headers for regular user in Community A."""
        return self._create_auth_headers(regular_user_in_community_a)

    @pytest.fixture
    def admin_a_headers(self, admin_user_in_community_a):
        """Auth headers for Admin in Community A."""
        return self._create_auth_headers(admin_user_in_community_a)

    @pytest.fixture
    def admin_b_headers(self, admin_user_in_community_b):
        """Auth headers for Admin in Community B."""
        return self._create_auth_headers(admin_user_in_community_b)

    @pytest.fixture
    def service_account_headers(self, service_account_user):
        """Auth headers for service account."""
        return self._create_auth_headers(service_account_user)

    @pytest.fixture
    async def existing_scan_in_community_a(self, db, community_a, admin_user_in_community_a):
        """Create an existing scan in Community A for testing GET endpoints."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_a.id,
            initiated_by_user_id=admin_user_in_community_a["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=100,
            messages_flagged=5,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan


class TestJSONAPIInitiateScanAuthorization(TestBulkScanAuthorizationFixtures):
    """Tests for POST /api/v2/bulk-scans endpoint authorization (JSON:API)."""

    @pytest.mark.asyncio
    async def test_jsonapi_regular_member_cannot_initiate_scan(
        self,
        regular_user_headers,
        community_a,
    ):
        """JSON:API: Regular member cannot initiate a scan on their community."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/bulk-scans",
                headers={
                    **regular_user_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "bulk-scans",
                        "attributes": {
                            "community_server_id": str(community_a.id),
                            "scan_window_days": 7,
                            "channel_ids": [],
                        },
                    }
                },
            )

            assert response.status_code == 403
            response_data = response.json()
            assert "errors" in response_data
            assert response_data["errors"][0]["status"] == "403"

    @pytest.mark.asyncio
    async def test_jsonapi_admin_from_other_community_cannot_initiate_scan(
        self,
        admin_b_headers,
        community_a,
    ):
        """JSON:API: Admin of Community B cannot initiate a scan on Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/bulk-scans",
                headers={
                    **admin_b_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "bulk-scans",
                        "attributes": {
                            "community_server_id": str(community_a.id),
                            "scan_window_days": 7,
                            "channel_ids": [],
                        },
                    }
                },
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_jsonapi_admin_can_initiate_scan_on_own_community(
        self,
        admin_a_headers,
        community_a,
    ):
        """JSON:API: Admin of Community A can initiate a scan on Community A.

        This test verifies the authorization passes (not 403). The actual scan may
        fail for other reasons (e.g., missing Redis methods in test mocks), but
        the authorization check itself should pass.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/bulk-scans",
                headers={
                    **admin_a_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "bulk-scans",
                        "attributes": {
                            "community_server_id": str(community_a.id),
                            "scan_window_days": 7,
                            "channel_ids": [],
                        },
                    }
                },
            )

            assert response.status_code != 403, "Admin should not receive 403 Forbidden"

    @pytest.mark.asyncio
    async def test_jsonapi_service_account_can_initiate_scan_on_any_community(
        self,
        service_account_headers,
        community_a,
    ):
        """JSON:API: Service account can initiate a scan on any community.

        This test verifies the authorization passes (not 403). The actual scan may
        fail for other reasons (e.g., missing Redis methods in test mocks), but
        the authorization check itself should pass.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/bulk-scans",
                headers={
                    **service_account_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "bulk-scans",
                        "attributes": {
                            "community_server_id": str(community_a.id),
                            "scan_window_days": 7,
                            "channel_ids": [],
                        },
                    }
                },
            )

            assert response.status_code != 403, "Service account should not receive 403 Forbidden"


class TestBulkScanCreationSuccess(TestBulkScanAuthorizationFixtures):
    """
    Tests for successful bulk scan creation (201 Created).

    Task: task-852.01 (TDD RED phase)

    These tests verify that scans are ACTUALLY created successfully, not just
    that authorization passes. This catches bugs like FK violations that would
    slip through the authorization-only tests (which check != 403).

    The existing authorization tests only verify that admins don't get 403,
    but don't verify that the operation actually succeeds. This allowed a
    FK violation bug to slip through where:
    - router.py:204 and jsonapi_router.py:435 pass current_user.id (User.id)
    - But initiated_by_user_id has FK constraint to user_profiles.id

    These tests will FAIL until the fix is applied, proving we're testing
    the right thing (TDD RED phase).
    """

    @pytest.mark.asyncio
    async def test_jsonapi_admin_can_successfully_create_scan(
        self,
        admin_a_headers,
        community_a,
        db,
    ):
        """
        JSON:API: Admin successfully creates a scan (201 Created).

        This test verifies the complete success path:
        1. Request returns 201 Created (not just != 403)
        2. Response contains valid scan data
        3. Scan was actually persisted to the database

        This will fail with FK violation until the bug is fixed.
        """
        from src.bulk_content_scan.models import BulkContentScanLog

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/bulk-scans",
                headers={
                    **admin_a_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "bulk-scans",
                        "attributes": {
                            "community_server_id": str(community_a.id),
                            "scan_window_days": 7,
                            "channel_ids": [],
                        },
                    }
                },
            )

            assert response.status_code == 201, (
                f"Expected 201 Created but got {response.status_code}. Response: {response.text}"
            )

            response_data = response.json()
            assert "data" in response_data
            assert response_data["data"]["type"] == "bulk-scans"
            scan_id = response_data["data"]["id"]
            assert scan_id is not None

            from sqlalchemy import select

            result = await db.execute(
                select(BulkContentScanLog).where(BulkContentScanLog.id == scan_id)
            )
            scan = result.scalar_one_or_none()
            assert scan is not None, "Scan was not persisted to database"
            assert str(scan.community_server_id) == str(community_a.id)


class TestJSONAPIGetScanResultsAuthorization(TestBulkScanAuthorizationFixtures):
    """Tests for GET /api/v2/bulk-scans/{id} endpoint authorization (JSON:API)."""

    @pytest.mark.asyncio
    async def test_jsonapi_regular_member_cannot_get_scan_results(
        self,
        regular_user_headers,
        existing_scan_in_community_a,
    ):
        """JSON:API: Regular member cannot get scan results."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/{existing_scan_in_community_a.id}",
                headers=regular_user_headers,
            )

            assert response.status_code == 403
            response_data = response.json()
            assert "errors" in response_data
            assert response_data["errors"][0]["status"] == "403"

    @pytest.mark.asyncio
    async def test_jsonapi_admin_from_other_community_cannot_get_scan_results(
        self,
        admin_b_headers,
        existing_scan_in_community_a,
    ):
        """JSON:API: Admin of Community B cannot get scan results from Community A."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/{existing_scan_in_community_a.id}",
                headers=admin_b_headers,
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_jsonapi_admin_can_get_scan_results_from_own_community(
        self,
        admin_a_headers,
        existing_scan_in_community_a,
    ):
        """JSON:API: Admin of Community A can get scan results from Community A.

        This test verifies the authorization passes (not 403). The actual retrieval may
        fail for other reasons (e.g., missing Redis methods in test mocks), but
        the authorization check itself should pass.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/{existing_scan_in_community_a.id}",
                headers=admin_a_headers,
            )

            assert response.status_code != 403, "Admin should not receive 403 Forbidden"

    @pytest.mark.asyncio
    async def test_jsonapi_service_account_can_get_scan_results_from_any_community(
        self,
        service_account_headers,
        existing_scan_in_community_a,
    ):
        """JSON:API: Service account can get scan results from any community.

        This test verifies the authorization passes (not 403). The actual retrieval may
        fail for other reasons (e.g., missing Redis methods in test mocks), but
        the authorization check itself should pass.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/{existing_scan_in_community_a.id}",
                headers=service_account_headers,
            )

            assert response.status_code != 403, "Service account should not receive 403 Forbidden"


class TestJSONAPICreateNoteRequestsAuthorization(TestBulkScanAuthorizationFixtures):
    """Tests for POST /api/v2/bulk-scans/{id}/note-requests endpoint authorization."""

    @pytest.mark.asyncio
    async def test_jsonapi_regular_member_cannot_create_note_requests(
        self,
        regular_user_headers,
        existing_scan_in_community_a,
    ):
        """JSON:API: Regular member cannot create note requests from a scan."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v2/bulk-scans/{existing_scan_in_community_a.id}/note-requests",
                headers={
                    **regular_user_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_123"],
                            "generate_ai_notes": False,
                        },
                    }
                },
            )

            assert response.status_code == 403
            response_data = response.json()
            assert "errors" in response_data
            assert response_data["errors"][0]["status"] == "403"

    @pytest.mark.asyncio
    async def test_jsonapi_admin_from_other_community_cannot_create_note_requests(
        self,
        admin_b_headers,
        existing_scan_in_community_a,
    ):
        """JSON:API: Admin of Community B cannot create note requests from Community A's scan."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v2/bulk-scans/{existing_scan_in_community_a.id}/note-requests",
                headers={
                    **admin_b_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_123"],
                            "generate_ai_notes": False,
                        },
                    }
                },
            )

            assert response.status_code == 403


class TestNoteRequestScanOwnerAuthorization(TestBulkScanAuthorizationFixtures):
    """
    Tests for POST /api/v2/bulk-scans/{id}/note-requests owner-based authorization.

    Task: task-849.02

    Note requests should be creatable by:
    1. The user who initiated the scan (scan owner)
    2. Community admins

    Non-owner non-admins should receive 403 Forbidden.
    """

    @pytest.fixture
    async def scan_initiated_by_regular_user(self, db, community_a, regular_user_in_community_a):
        """
        Create a scan initiated by a regular (non-admin) user.
        This tests that scan owners can create note requests even without admin role.
        """
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_a.id,
            initiated_by_user_id=regular_user_in_community_a["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=50,
            messages_flagged=3,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan

    @pytest.fixture
    async def another_regular_user_in_community_a(self, db, community_a):
        """
        Create another regular (non-admin) user in Community A.
        Used to test that non-owner regular users cannot create note requests.
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
            username="bulk_scan_another_regular_user_a",
            email="bulk_scan_another_regular_a@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_bulk_scan_another_regular_a",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Bulk Scan Another Regular User A",
            avatar_url=None,
            bio="Another regular user in Community A for bulk scan tests",
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
            invitation_reason="Test fixture for bulk scan owner authorization tests",
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
    def another_regular_user_headers(self, another_regular_user_in_community_a):
        """Auth headers for another regular user in Community A."""
        return self._create_auth_headers(another_regular_user_in_community_a)

    @pytest.mark.asyncio
    async def test_scan_owner_can_create_note_requests_without_admin(
        self,
        regular_user_headers,
        scan_initiated_by_regular_user,
    ):
        """
        Scan owner (non-admin) should be able to create note requests.

        The regular user who initiated the scan should be authorized to create
        note requests for that scan, even without admin permissions.
        Authorization should pass (not 403) - actual creation may fail for
        other reasons (e.g., missing flagged results).
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v2/bulk-scans/{scan_initiated_by_regular_user.id}/note-requests",
                headers={
                    **regular_user_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_123"],
                            "generate_ai_notes": False,
                        },
                    }
                },
            )

            assert response.status_code != 403, (
                f"Scan owner should not receive 403 Forbidden. "
                f"Response: {response.status_code} - {response.text}"
            )

    @pytest.mark.asyncio
    async def test_admin_non_owner_can_create_note_requests(
        self,
        admin_a_headers,
        scan_initiated_by_regular_user,
    ):
        """
        Admin (non-owner) should be able to create note requests.

        Community admin should be authorized to create note requests for any
        scan in their community, even if they didn't initiate it.
        Authorization should pass (not 403) - actual creation may fail for
        other reasons (e.g., missing flagged results).
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v2/bulk-scans/{scan_initiated_by_regular_user.id}/note-requests",
                headers={
                    **admin_a_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_123"],
                            "generate_ai_notes": False,
                        },
                    }
                },
            )

            assert response.status_code != 403, (
                f"Admin should not receive 403 Forbidden. "
                f"Response: {response.status_code} - {response.text}"
            )

    @pytest.mark.asyncio
    async def test_non_owner_non_admin_cannot_create_note_requests(
        self,
        another_regular_user_headers,
        scan_initiated_by_regular_user,
    ):
        """
        Non-owner, non-admin user should receive 403 Forbidden.

        A regular member who did not initiate the scan and is not a community
        admin should not be able to create note requests.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v2/bulk-scans/{scan_initiated_by_regular_user.id}/note-requests",
                headers={
                    **another_regular_user_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_123"],
                            "generate_ai_notes": False,
                        },
                    }
                },
            )

            assert response.status_code == 403, (
                f"Non-owner non-admin should receive 403 Forbidden. "
                f"Response: {response.status_code} - {response.text}"
            )
            response_data = response.json()
            assert "errors" in response_data
            assert response_data["errors"][0]["status"] == "403"

    @pytest.mark.asyncio
    async def test_service_account_can_create_note_requests(
        self,
        service_account_headers,
        scan_initiated_by_regular_user,
    ):
        """
        Service accounts should be able to create note requests for any scan.

        Service accounts have unrestricted access and should be authorized
        regardless of scan ownership or community admin status.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v2/bulk-scans/{scan_initiated_by_regular_user.id}/note-requests",
                headers={
                    **service_account_headers,
                    "Content-Type": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_123"],
                            "generate_ai_notes": False,
                        },
                    }
                },
            )

            assert response.status_code != 403, (
                f"Service account should not receive 403 Forbidden. "
                f"Response: {response.status_code} - {response.text}"
            )


class TestJSONAPICheckRecentScanAuthorization(TestBulkScanAuthorizationFixtures):
    """Tests for GET /api/v2/bulk-scans/communities/{id}/recent endpoint authorization."""

    @pytest.mark.asyncio
    async def test_jsonapi_regular_member_cannot_check_recent_scan(
        self,
        regular_user_headers,
        community_a,
    ):
        """JSON:API: Regular member cannot check recent scan status (admin only operation)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_a.id}/recent",
                headers=regular_user_headers,
            )

            assert response.status_code == 403
            response_data = response.json()
            assert "errors" in response_data
            assert response_data["errors"][0]["status"] == "403"

    @pytest.mark.asyncio
    async def test_jsonapi_admin_can_check_recent_scan_for_own_community(
        self,
        admin_a_headers,
        community_a,
    ):
        """JSON:API: Admin can check recent scan status for their own community.

        This test verifies the authorization passes (not 403). The actual query may
        fail for other reasons, but the authorization check itself should pass.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_a.id}/recent",
                headers=admin_a_headers,
            )

            assert response.status_code != 403, "Admin should not receive 403 Forbidden"
