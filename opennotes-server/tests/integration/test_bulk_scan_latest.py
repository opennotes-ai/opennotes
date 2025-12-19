"""
Integration tests for GET /api/v2/bulk-scans/communities/{community_server_id}/latest endpoint.

Task: task-855 (AC#1)

Tests verify:
1. Returns the most recent scan for a community with full results
2. Includes scan status, counts, and flagged messages when completed
3. Returns 404 when no scans exist
4. Requires admin access (403 for regular members)
5. Service accounts have access
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.main import app


class TestLatestScanFixtures:
    """Fixtures for latest scan endpoint tests."""

    @pytest.fixture
    async def community_server(self, db):
        """Create a community server for testing."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id="latest_scan_test_community",
            name="Latest Scan Test Community",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.fixture
    async def other_community(self, db):
        """Create another community server for cross-community tests."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id="latest_scan_other_community",
            name="Latest Scan Other Community",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.fixture
    async def admin_user(self, db, community_server):
        """Create an admin user with admin role in the community."""
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
            username="latest_scan_admin_user",
            email="latest_scan_admin@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_latest_scan_admin",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Latest Scan Admin User",
            avatar_url=None,
            bio="Admin user for latest scan tests",
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
            community_id=community_server.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Admin fixture for latest scan tests",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": community_server,
        }

    @pytest.fixture
    async def regular_user(self, db, community_server):
        """Create a regular (non-admin) user with membership in the community."""
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
            username="latest_scan_regular_user",
            email="latest_scan_regular@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_latest_scan_regular",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Latest Scan Regular User",
            avatar_url=None,
            bio="Regular user for latest scan tests",
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
            community_id=community_server.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Regular user fixture for latest scan tests",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": community_server,
        }

    @pytest.fixture
    async def other_community_admin(self, db, other_community):
        """Create an admin user in the other community."""
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
            username="latest_scan_other_admin",
            email="latest_scan_other_admin@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_latest_scan_other_admin",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Latest Scan Other Admin",
            avatar_url=None,
            bio="Admin user in other community for latest scan tests",
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
            community_id=other_community.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Admin fixture for other community",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": other_community,
        }

    @pytest.fixture
    async def service_account(self, db):
        """Create a service account user."""
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="latest-scan-service",
            email="latest-scan-service@opennotes.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=True,
            discord_id="discord_latest_scan_service",
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
    def admin_headers(self, admin_user):
        """Auth headers for admin user."""
        return self._create_auth_headers(admin_user)

    @pytest.fixture
    def regular_user_headers(self, regular_user):
        """Auth headers for regular user."""
        return self._create_auth_headers(regular_user)

    @pytest.fixture
    def other_admin_headers(self, other_community_admin):
        """Auth headers for admin in other community."""
        return self._create_auth_headers(other_community_admin)

    @pytest.fixture
    def service_account_headers(self, service_account):
        """Auth headers for service account."""
        return self._create_auth_headers(service_account)

    @pytest.fixture
    async def completed_scan(self, db, community_server, admin_user):
        """Create a completed scan with flagged messages."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server.id,
            initiated_by_user_id=admin_user["profile"].id,
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

    @pytest.fixture
    async def pending_scan(self, db, community_server, admin_user):
        """Create a pending scan (more recent than completed)."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server.id,
            initiated_by_user_id=admin_user["profile"].id,
            scan_window_days=14,
            status="pending",
            initiated_at=datetime.now(UTC) + timedelta(minutes=5),
            completed_at=None,
            messages_scanned=0,
            messages_flagged=0,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan

    @pytest.fixture
    async def older_scan(self, db, community_server, admin_user):
        """Create an older scan (not the most recent)."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server.id,
            initiated_by_user_id=admin_user["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC) - timedelta(days=7),
            completed_at=datetime.now(UTC) - timedelta(days=7),
            messages_scanned=50,
            messages_flagged=2,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan


class TestGetLatestScan(TestLatestScanFixtures):
    """Tests for GET /api/v2/bulk-scans/communities/{community_server_id}/latest endpoint."""

    @pytest.mark.asyncio
    async def test_get_latest_scan_returns_most_recent(
        self,
        admin_headers,
        community_server,
        completed_scan,
        older_scan,
    ):
        """
        Should return the most recent scan, not older ones.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=admin_headers,
            )

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )
            data = response.json()
            assert data["data"]["id"] == str(completed_scan.id)
            assert data["data"]["attributes"]["status"] == "completed"
            assert data["data"]["attributes"]["messages_scanned"] == 100
            assert data["data"]["attributes"]["messages_flagged"] == 5

    @pytest.mark.asyncio
    async def test_get_latest_scan_returns_pending_when_most_recent(
        self,
        admin_headers,
        community_server,
        completed_scan,
        pending_scan,
    ):
        """
        Should return pending scan when it's the most recent.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=admin_headers,
            )

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )
            data = response.json()
            assert data["data"]["id"] == str(pending_scan.id)
            assert data["data"]["attributes"]["status"] == "pending"
            assert data["data"]["attributes"]["messages_scanned"] == 0
            assert data["data"]["attributes"]["messages_flagged"] == 0

    @pytest.mark.asyncio
    async def test_get_latest_scan_returns_404_when_no_scans(
        self,
        admin_headers,
        community_server,
    ):
        """
        Should return 404 when no scans exist for the community.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=admin_headers,
            )

            assert response.status_code == 404, (
                f"Expected 404, got {response.status_code}: {response.text}"
            )
            data = response.json()
            assert "errors" in data

    @pytest.mark.asyncio
    async def test_get_latest_scan_regular_member_denied(
        self,
        regular_user_headers,
        community_server,
        completed_scan,
    ):
        """
        Regular members should receive 403 Forbidden.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=regular_user_headers,
            )

            assert response.status_code == 403, (
                f"Expected 403, got {response.status_code}: {response.text}"
            )

    @pytest.mark.asyncio
    async def test_get_latest_scan_other_community_admin_denied(
        self,
        other_admin_headers,
        community_server,
        completed_scan,
    ):
        """
        Admin from a different community should receive 403 Forbidden.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=other_admin_headers,
            )

            assert response.status_code == 403, (
                f"Expected 403, got {response.status_code}: {response.text}"
            )

    @pytest.mark.asyncio
    async def test_get_latest_scan_service_account_allowed(
        self,
        service_account_headers,
        community_server,
        completed_scan,
    ):
        """
        Service accounts should have access to any community's latest scan.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=service_account_headers,
            )

            assert response.status_code != 403, (
                f"Service account should not receive 403: {response.text}"
            )
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

    @pytest.mark.asyncio
    async def test_get_latest_scan_includes_timestamps(
        self,
        admin_headers,
        community_server,
        completed_scan,
    ):
        """
        Response should include initiated_at and completed_at timestamps.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=admin_headers,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert "initiated_at" in attrs
            assert "completed_at" in attrs
            assert attrs["initiated_at"] is not None
            assert attrs["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_get_latest_scan_returns_404_for_nonexistent_community(
        self,
        admin_headers,
    ):
        """
        Should return 403/404 for a community that doesn't exist.
        """
        fake_community_id = uuid4()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{fake_community_id}/latest",
                headers=admin_headers,
            )

            assert response.status_code in (403, 404), (
                f"Expected 403 or 404 for nonexistent community, got {response.status_code}"
            )
