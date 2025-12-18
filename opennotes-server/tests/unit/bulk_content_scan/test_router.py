"""Tests for Bulk Content Scan REST API router (router.py)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_flagged_messages():
    """Create mock flagged messages for testing."""
    from src.bulk_content_scan.schemas import FlaggedMessage

    return [
        FlaggedMessage(
            message_id=f"msg_{i}",
            channel_id="ch_1",
            content=f"Test message {i}",
            author_id=f"user_{i}",
            timestamp=datetime.now(UTC),
            match_score=0.85 - (i * 0.01),
            matched_claim=f"Test claim {i}",
            matched_source=f"https://example.com/{i}",
        )
        for i in range(25)
    ]


@pytest.fixture
def mock_service(mock_flagged_messages):
    """Create a mock BulkContentScanService."""
    from src.bulk_content_scan.models import BulkContentScanLog

    service = AsyncMock()

    mock_scan_log = MagicMock(spec=BulkContentScanLog)
    mock_scan_log.id = uuid4()
    mock_scan_log.community_server_id = uuid4()
    mock_scan_log.status = "completed"
    mock_scan_log.initiated_at = datetime.now(UTC)
    mock_scan_log.completed_at = datetime.now(UTC)
    mock_scan_log.messages_scanned = 100
    mock_scan_log.messages_flagged = 25

    service.initiate_scan = AsyncMock(return_value=mock_scan_log)
    service.get_scan = AsyncMock(return_value=mock_scan_log)
    service.get_flagged_results = AsyncMock(return_value=mock_flagged_messages)

    return service


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_community_member():
    """Create a mock community member for authorization."""
    member = MagicMock()
    member.profile_id = uuid4()
    member.community_id = uuid4()
    member.role = "admin"
    member.is_active = True
    member.banned_at = None
    return member


@pytest.fixture
def app_with_router(mock_service, mock_user, mock_session, mock_community_member):
    """Create a FastAPI app with the bulk content scan router."""
    from src.bulk_content_scan.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_get_service():
        return mock_service

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        return mock_session

    from src.auth.dependencies import get_current_user_or_api_key
    from src.bulk_content_scan import router as router_module
    from src.database import get_db

    app.dependency_overrides[router_module.get_bulk_scan_service] = override_get_service
    app.dependency_overrides[get_current_user_or_api_key] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    return app


@pytest.fixture
def client(app_with_router):
    """Create a test client."""
    return TestClient(app_with_router)


class TestGetScanResultsPagination:
    """Test GET /bulk-content-scan/scans/{scan_id} pagination (task-849.18)."""

    def test_get_scan_results_accepts_page_parameter(
        self, client, mock_service, mock_community_member
    ):
        """AC #3: GET /scans/{scan_id} should accept page query parameter."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page=2")

        assert response.status_code == 200

    def test_get_scan_results_accepts_page_size_parameter(
        self, client, mock_service, mock_community_member
    ):
        """AC #3: GET /scans/{scan_id} should accept page_size query parameter."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page_size=5")

        assert response.status_code == 200

    def test_get_scan_results_returns_pagination_metadata(
        self, client, mock_service, mock_community_member
    ):
        """AC #4: Response should include pagination metadata (total, page, page_size)."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data, "Response should include 'total' field"
        assert "page" in data, "Response should include 'page' field"
        assert "page_size" in data, "Response should include 'page_size' field"

    def test_get_scan_results_paginates_flagged_messages(
        self, client, mock_service, mock_community_member
    ):
        """Pagination should limit the number of returned flagged_messages."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page=1&page_size=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["flagged_messages"]) == 5

    def test_get_scan_results_page_offset_works_correctly(
        self, client, mock_service, mock_community_member
    ):
        """Page 2 should return different results than page 1."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response_page1 = client.get(
                f"/api/v1/bulk-content-scan/scans/{scan_id}?page=1&page_size=5"
            )
            response_page2 = client.get(
                f"/api/v1/bulk-content-scan/scans/{scan_id}?page=2&page_size=5"
            )

        assert response_page1.status_code == 200
        assert response_page2.status_code == 200

        data_page1 = response_page1.json()
        data_page2 = response_page2.json()

        page1_ids = [msg["message_id"] for msg in data_page1["flagged_messages"]]
        page2_ids = [msg["message_id"] for msg in data_page2["flagged_messages"]]

        assert page1_ids[0] == "msg_0", "Page 1 should start with first message"
        assert page2_ids[0] == "msg_5", "Page 2 should start with 6th message"

    def test_get_scan_results_total_count_is_correct(
        self, client, mock_service, mock_community_member
    ):
        """Total should reflect the total number of flagged messages."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page=1&page_size=5")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25

    def test_get_scan_results_last_page_has_remaining_items(
        self, client, mock_service, mock_community_member
    ):
        """Last page should return remaining items when not full page."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page=3&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["flagged_messages"]) == 5

    def test_get_scan_results_default_pagination(self, client, mock_service, mock_community_member):
        """Should have default pagination values when not specified."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] > 0

    def test_get_scan_results_empty_page_beyond_data(
        self, client, mock_service, mock_community_member
    ):
        """Page beyond data should return empty flagged_messages list."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(
                f"/api/v1/bulk-content-scan/scans/{scan_id}?page=100&page_size=10"
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["flagged_messages"]) == 0
        assert data["total"] == 25

    def test_get_scan_results_page_size_validation(
        self, client, mock_service, mock_community_member
    ):
        """Page size should have reasonable limits."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page_size=0")

        assert response.status_code == 422

    def test_get_scan_results_page_validation(self, client, mock_service, mock_community_member):
        """Page number should be at least 1."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}?page=0")

        assert response.status_code == 422
