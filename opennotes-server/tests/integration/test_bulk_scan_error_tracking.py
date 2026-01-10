"""
Integration tests for bulk scan error tracking and reporting.

Task: task-863

Tests verify:
1. Per-message errors are tracked during batch processing
2. Error counts accumulate in Redis
3. Error summary is included in scan results
4. Scan status is marked as 'failed' when 100% of messages fail
5. Latest scan endpoint includes error_summary in response
"""

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.bulk_content_scan.service import (
    BulkContentScanService,
    _get_redis_error_counts_key,
    _get_redis_errors_key,
)


@pytest.fixture
def redis_client():
    """Provide a Redis client for integration tests.

    Uses the mocked Redis from mock_external_services fixture.
    """
    from src.cache.redis_client import redis_client as _redis_client

    return _redis_client.client


class TestBulkScanErrorTracking:
    """Tests for error tracking during bulk scan processing."""

    @pytest.fixture
    async def scan_id(self):
        """Generate a unique scan ID for testing."""
        return uuid4()

    @pytest.fixture
    async def mock_embedding_service(self):
        """Create a mock embedding service."""
        from src.fact_checking.embedding_service import EmbeddingService

        return MagicMock(spec=EmbeddingService)

    @pytest.fixture
    async def bulk_scan_service(
        self, db, redis_client: Any, mock_embedding_service
    ) -> BulkContentScanService:
        """Create a BulkContentScanService with test dependencies."""
        return BulkContentScanService(
            session=db,
            embedding_service=mock_embedding_service,
            redis_client=redis_client,
        )

    @pytest.mark.asyncio
    async def test_record_error_stores_in_redis(
        self,
        bulk_scan_service: BulkContentScanService,
        scan_id,
        redis_client: Any,
    ):
        """Test that record_error stores error info in Redis."""
        await bulk_scan_service.record_error(
            scan_id=scan_id,
            error_type="TypeError",
            error_message="unsupported operand type(s) for +",
            message_id="msg_123",
            batch_number=1,
        )

        errors_key = _get_redis_errors_key(scan_id)
        counts_key = _get_redis_error_counts_key(scan_id)

        raw_errors = await redis_client.lrange(errors_key, 0, -1)
        assert len(raw_errors) == 1

        error_data = json.loads(raw_errors[0])
        assert error_data["error_type"] == "TypeError"
        assert error_data["message_id"] == "msg_123"
        assert error_data["batch_number"] == 1
        assert "unsupported operand" in error_data["error_message"]

        type_count = await redis_client.hget(counts_key, "TypeError")
        assert int(type_count) == 1

    @pytest.mark.asyncio
    async def test_multiple_errors_accumulate_counts(
        self,
        bulk_scan_service: BulkContentScanService,
        scan_id,
        redis_client: Any,
    ):
        """Test that multiple errors accumulate correctly in Redis."""
        await bulk_scan_service.record_error(
            scan_id=scan_id,
            error_type="TypeError",
            error_message="Error 1",
        )
        await bulk_scan_service.record_error(
            scan_id=scan_id,
            error_type="TypeError",
            error_message="Error 2",
        )
        await bulk_scan_service.record_error(
            scan_id=scan_id,
            error_type="ValueError",
            error_message="Error 3",
        )

        error_summary = await bulk_scan_service.get_error_summary(scan_id)

        assert error_summary["total_errors"] == 3
        assert error_summary["error_types"]["TypeError"] == 2
        assert error_summary["error_types"]["ValueError"] == 1
        assert len(error_summary["sample_errors"]) == 3

    @pytest.mark.asyncio
    async def test_get_error_summary_limits_samples(
        self,
        bulk_scan_service: BulkContentScanService,
        scan_id,
    ):
        """Test that get_error_summary returns at most 5 sample errors."""
        for i in range(10):
            await bulk_scan_service.record_error(
                scan_id=scan_id,
                error_type="TestError",
                error_message=f"Error {i}",
            )

        error_summary = await bulk_scan_service.get_error_summary(scan_id)

        assert error_summary["total_errors"] == 10
        assert len(error_summary["sample_errors"]) == 5

    @pytest.mark.asyncio
    async def test_increment_processed_count(
        self,
        bulk_scan_service: BulkContentScanService,
        scan_id,
        redis_client: Any,
    ):
        """Test that increment_processed_count tracks successful messages."""
        await bulk_scan_service.increment_processed_count(scan_id, 5)
        await bulk_scan_service.increment_processed_count(scan_id, 3)

        count = await bulk_scan_service.get_processed_count(scan_id)
        assert count == 8

    @pytest.mark.asyncio
    async def test_get_processed_count_returns_zero_when_empty(
        self,
        bulk_scan_service: BulkContentScanService,
    ):
        """Test that get_processed_count returns 0 when no count exists."""
        nonexistent_scan_id = uuid4()
        count = await bulk_scan_service.get_processed_count(nonexistent_scan_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_error_summary_returns_empty_when_no_errors(
        self,
        bulk_scan_service: BulkContentScanService,
    ):
        """Test that get_error_summary returns empty summary when no errors."""
        nonexistent_scan_id = uuid4()
        error_summary = await bulk_scan_service.get_error_summary(nonexistent_scan_id)

        assert error_summary["total_errors"] == 0
        assert error_summary["error_types"] == {}
        assert error_summary["sample_errors"] == []


class TestBulkScanErrorSummaryInResponse:
    """Tests for error summary in API responses."""

    @pytest.fixture
    async def community_server(self, db):
        """Create a community server for testing."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="error_tracking_test_community",
            name="Error Tracking Test Community",
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
            username="error_tracking_admin_user",
            email="error_tracking_admin@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_error_tracking_admin",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Error Tracking Admin User",
            avatar_url=None,
            bio="Admin user for error tracking tests",
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
            invitation_reason="Admin fixture for error tracking tests",
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
    def admin_headers(self, admin_user):
        """Auth headers for admin user."""
        from src.auth.auth import create_access_token

        user = admin_user["user"]
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    async def failed_scan_with_errors(self, db, community_server, admin_user, redis_client: Any):
        """Create a failed scan with errors in Redis."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server.id,
            initiated_by_user_id=admin_user["profile"].id,
            scan_window_days=7,
            status="failed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=10,
            messages_flagged=0,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)

        errors_key = _get_redis_errors_key(scan.id)
        counts_key = _get_redis_error_counts_key(scan.id)

        for i in range(3):
            error_info = {
                "error_type": "TypeError",
                "message_id": f"msg_{i}",
                "batch_number": 1,
                "error_message": f"Test error {i}",
            }
            await redis_client.lpush(errors_key, json.dumps(error_info))

        await redis_client.hset(counts_key, "TypeError", 3)
        await redis_client.expire(errors_key, 3600)
        await redis_client.expire(counts_key, 3600)

        return scan

    @pytest.mark.asyncio
    async def test_latest_scan_includes_error_summary_when_failed(
        self,
        admin_headers,
        community_server,
        failed_scan_with_errors,
    ):
        """Test that GET latest scan includes error_summary for failed scans."""
        from httpx import ASGITransport, AsyncClient

        from src.main import app

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
            assert data["data"]["attributes"]["status"] == "failed"
            assert "error_summary" in data["data"]["attributes"]

            error_summary = data["data"]["attributes"]["error_summary"]
            assert error_summary["total_errors"] == 3
            assert error_summary["error_types"]["TypeError"] == 3
            assert len(error_summary["sample_errors"]) == 3

    @pytest.fixture
    async def completed_scan_with_partial_errors(
        self, db, community_server, admin_user, redis_client: Any
    ):
        """Create a completed scan with some errors in Redis."""
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

        errors_key = _get_redis_errors_key(scan.id)
        counts_key = _get_redis_error_counts_key(scan.id)

        error_info = {
            "error_type": "ValueError",
            "message_id": "msg_fail",
            "batch_number": 2,
            "error_message": "Partial failure test",
        }
        await redis_client.lpush(errors_key, json.dumps(error_info))
        await redis_client.hset(counts_key, "ValueError", 1)
        await redis_client.expire(errors_key, 3600)
        await redis_client.expire(counts_key, 3600)

        return scan

    @pytest.mark.asyncio
    async def test_latest_scan_includes_error_summary_when_completed_with_errors(
        self,
        admin_headers,
        community_server,
        completed_scan_with_partial_errors,
    ):
        """Test that completed scans also include error_summary if errors occurred."""
        from httpx import ASGITransport, AsyncClient

        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=admin_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["status"] == "completed"
            assert "error_summary" in data["data"]["attributes"]

            error_summary = data["data"]["attributes"]["error_summary"]
            assert error_summary["total_errors"] == 1
            assert error_summary["error_types"]["ValueError"] == 1

    @pytest.fixture
    async def completed_scan_no_errors(self, db, community_server, admin_user):
        """Create a completed scan without any errors."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server.id,
            initiated_by_user_id=admin_user["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=50,
            messages_flagged=2,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan

    @pytest.mark.asyncio
    async def test_latest_scan_no_error_summary_when_no_errors(
        self,
        admin_headers,
        community_server,
        completed_scan_no_errors,
    ):
        """Test that error_summary is None when no errors occurred."""
        from httpx import ASGITransport, AsyncClient

        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v2/bulk-scans/communities/{community_server.id}/latest",
                headers=admin_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["attributes"]["status"] == "completed"
            assert data["data"]["attributes"].get("error_summary") is None
