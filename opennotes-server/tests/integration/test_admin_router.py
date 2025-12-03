"""
Integration tests for the admin router endpoints.

These tests verify that:
1. Service accounts can grant/revoke Open Notes admin status
2. Non-service account users are rejected with 403
3. Profile not found returns 404
4. The bypass_admin_check parameter works correctly for service account operations

Task: task-728 - Fix admin endpoint broken by security fix
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.main import app


class TestAdminRouterFixtures:
    """Fixtures for admin router testing scenarios."""

    @pytest.fixture
    async def regular_user_with_profile(self, db):
        """
        Create a regular user with a profile for testing admin status changes.
        """
        from src.users.models import User
        from src.users.profile_crud import create_profile_with_identity
        from src.users.profile_schemas import (
            AuthProvider,
            UserProfileCreate,
        )

        user = User(
            id=uuid4(),
            username="regular_user_admin_test",
            email="regular_admin@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_regular_admin_test",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Regular User for Admin Test",
            avatar_url=None,
            bio="Test user for admin router tests",
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

        await db.commit()
        await db.refresh(user)
        await db.refresh(profile)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
        }

    @pytest.fixture
    async def service_account_user(self, db):
        """
        Create a service account user.

        Service accounts are identified by:
        - is_service_account=True flag
        - Email ending with @opennotes.local
        - Username ending with -service
        """
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="admin-bot-service",
            email="admin-bot@opennotes.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=True,
            discord_id="discord_admin_bot_service",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return {"user": user}

    @pytest.fixture
    async def non_service_account_user(self, db):
        """
        Create a regular user (NOT a service account).
        """
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="regular_human_user",
            email="human@example.com",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=False,
            discord_id="discord_human_user",
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
    def service_account_headers(self, service_account_user):
        """Auth headers for service account."""
        return self._create_auth_headers(service_account_user)

    @pytest.fixture
    def non_service_account_headers(self, non_service_account_user):
        """Auth headers for non-service account user."""
        return self._create_auth_headers(non_service_account_user)


class TestSetOpennotesAdminStatus(TestAdminRouterFixtures):
    """Tests for the PATCH /api/v1/admin/profiles/{profile_id}/opennotes-admin endpoint."""

    @pytest.mark.asyncio
    async def test_service_account_can_grant_admin_status(
        self,
        service_account_headers,
        regular_user_with_profile,
    ):
        """Service account can grant Open Notes admin status to a profile."""
        profile = regular_user_with_profile["profile"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=true",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_opennotes_admin"] is True
            assert data["id"] == str(profile.id)

    @pytest.mark.asyncio
    async def test_service_account_can_revoke_admin_status(
        self,
        db,
        service_account_headers,
        regular_user_with_profile,
    ):
        """Service account can revoke Open Notes admin status from a profile."""
        profile = regular_user_with_profile["profile"]

        profile.is_opennotes_admin = True
        await db.commit()
        await db.refresh(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=false",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_opennotes_admin"] is False
            assert data["id"] == str(profile.id)

    @pytest.mark.asyncio
    async def test_non_service_account_cannot_grant_admin_status(
        self,
        non_service_account_headers,
        regular_user_with_profile,
    ):
        """Non-service account user is rejected with 403."""
        profile = regular_user_with_profile["profile"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=true",
                headers=non_service_account_headers,
            )

            assert response.status_code == 403
            assert "service accounts" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_profile_not_found_returns_404(
        self,
        service_account_headers,
    ):
        """Request with non-existent profile ID returns 404."""
        non_existent_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{non_existent_id}/opennotes-admin?is_admin=true",
                headers=service_account_headers,
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        regular_user_with_profile,
    ):
        """Request without auth token returns 401."""
        profile = regular_user_with_profile["profile"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=true",
            )

            assert response.status_code == 401


class TestGetOpennotesAdminStatus(TestAdminRouterFixtures):
    """Tests for the GET /api/v1/admin/profiles/{profile_id}/opennotes-admin endpoint."""

    @pytest.mark.asyncio
    async def test_service_account_can_get_admin_status(
        self,
        service_account_headers,
        regular_user_with_profile,
    ):
        """Service account can check Open Notes admin status of a profile."""
        profile = regular_user_with_profile["profile"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_opennotes_admin"] is False

    @pytest.mark.asyncio
    async def test_service_account_can_get_admin_status_when_true(
        self,
        db,
        service_account_headers,
        regular_user_with_profile,
    ):
        """Service account can check Open Notes admin status when it's true."""
        profile = regular_user_with_profile["profile"]

        profile.is_opennotes_admin = True
        await db.commit()
        await db.refresh(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_opennotes_admin"] is True

    @pytest.mark.asyncio
    async def test_non_service_account_cannot_get_admin_status(
        self,
        non_service_account_headers,
        regular_user_with_profile,
    ):
        """Non-service account user is rejected with 403."""
        profile = regular_user_with_profile["profile"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin",
                headers=non_service_account_headers,
            )

            assert response.status_code == 403
            assert "service accounts" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_profile_not_found_returns_404(
        self,
        service_account_headers,
    ):
        """GET request with non-existent profile ID returns 404."""
        non_existent_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/admin/profiles/{non_existent_id}/opennotes-admin",
                headers=service_account_headers,
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestBypassAdminCheckIntegration(TestAdminRouterFixtures):
    """
    Integration tests verifying bypass_admin_check works correctly.

    These tests ensure that the fix for task-728 (bypass_admin_check parameter)
    allows service accounts to update admin fields without having a UserProfile
    with is_opennotes_admin=True.
    """

    @pytest.mark.asyncio
    async def test_service_account_can_toggle_admin_status_multiple_times(
        self,
        service_account_headers,
        regular_user_with_profile,
    ):
        """Service account can toggle admin status on and off multiple times."""
        profile = regular_user_with_profile["profile"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=true",
                headers=service_account_headers,
            )
            assert response.status_code == 200
            assert response.json()["is_opennotes_admin"] is True

            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=false",
                headers=service_account_headers,
            )
            assert response.status_code == 200
            assert response.json()["is_opennotes_admin"] is False

            response = await client.patch(
                f"/api/v1/admin/profiles/{profile.id}/opennotes-admin?is_admin=true",
                headers=service_account_headers,
            )
            assert response.status_code == 200
            assert response.json()["is_opennotes_admin"] is True

    @pytest.mark.asyncio
    async def test_admin_status_change_persists_in_database(
        self,
        service_account_headers,
        regular_user_with_profile,
    ):
        """Verify that admin status changes are persisted to the database."""
        from src.database import get_session_maker
        from src.users.profile_crud import get_profile_by_id

        profile = regular_user_with_profile["profile"]
        profile_id = profile.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/admin/profiles/{profile_id}/opennotes-admin?is_admin=true",
                headers=service_account_headers,
            )
            assert response.status_code == 200

        async with get_session_maker()() as fresh_db:
            refreshed_profile = await get_profile_by_id(fresh_db, profile_id)
            assert refreshed_profile is not None
            assert refreshed_profile.is_opennotes_admin is True
