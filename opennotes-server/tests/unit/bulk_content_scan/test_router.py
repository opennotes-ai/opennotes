"""Tests for Bulk Content Scan API router."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_service():
    """Create a mock BulkContentScanService."""
    from src.bulk_content_scan.models import BulkContentScanLog

    service = AsyncMock()

    mock_scan_log = MagicMock(spec=BulkContentScanLog)
    mock_scan_log.id = uuid4()
    mock_scan_log.status = "pending"
    mock_scan_log.initiated_at = datetime.now(UTC)
    mock_scan_log.completed_at = None
    mock_scan_log.messages_scanned = 0
    mock_scan_log.messages_flagged = 0

    service.initiate_scan = AsyncMock(return_value=mock_scan_log)
    service.get_scan = AsyncMock(return_value=mock_scan_log)
    service.get_flagged_results = AsyncMock(return_value=[])

    return service


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def app_with_router(mock_service, mock_user):
    """Create a FastAPI app with the bulk content scan router."""
    from src.bulk_content_scan.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_get_service():
        return mock_service

    async def override_get_current_user():
        return mock_user

    from src.bulk_content_scan import router as router_module

    app.dependency_overrides[router_module.get_bulk_scan_service] = override_get_service
    app.dependency_overrides[router_module.get_current_user_for_bulk_scan] = (
        override_get_current_user
    )

    return app


@pytest.fixture
def client(app_with_router):
    """Create a test client."""
    return TestClient(app_with_router)


class TestInitiateScanEndpoint:
    """Test POST /bulk-content-scan/scans endpoint."""

    def test_initiate_scan_returns_201(self, client, mock_service):
        """AC #5: POST /bulk-content-scan/scans initiates scan and returns scan_id."""
        community_server_id = str(uuid4())

        response = client.post(
            "/api/v1/bulk-content-scan/scans",
            json={
                "community_server_id": community_server_id,
                "scan_window_days": 7,
                "channel_ids": ["ch_1", "ch_2"],
            },
        )

        assert response.status_code == 201
        assert "scan_id" in response.json()
        mock_service.initiate_scan.assert_called_once()

    def test_initiate_scan_returns_scan_response(self, client, mock_service):
        """Response should include scan status and metadata."""
        response = client.post(
            "/api/v1/bulk-content-scan/scans",
            json={
                "community_server_id": str(uuid4()),
                "scan_window_days": 7,
            },
        )

        data = response.json()
        assert "scan_id" in data
        assert "status" in data
        assert "initiated_at" in data

    def test_initiate_scan_validates_window_days(self, client):
        """Scan window days must be within valid range."""
        response = client.post(
            "/api/v1/bulk-content-scan/scans",
            json={
                "community_server_id": str(uuid4()),
                "scan_window_days": 0,  # Invalid
            },
        )

        assert response.status_code == 422


class TestGetScanResultsEndpoint:
    """Test GET /bulk-content-scan/scans/{scan_id} endpoint."""

    def test_get_scan_returns_200(self, client, mock_service):
        """AC #6: GET returns status and flagged results."""
        scan_id = mock_service.get_scan.return_value.id

        response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}")

        assert response.status_code == 200
        mock_service.get_scan.assert_called_once()

    def test_get_scan_returns_results_response(self, client, mock_service):
        """Response should include status and flagged messages."""
        scan_id = mock_service.get_scan.return_value.id

        response = client.get(f"/api/v1/bulk-content-scan/scans/{scan_id}")

        data = response.json()
        assert "scan_id" in data
        assert "status" in data
        assert "messages_scanned" in data
        assert "flagged_messages" in data

    def test_get_scan_returns_404_for_missing(self, client, mock_service):
        """Should return 404 for non-existent scan."""
        mock_service.get_scan = AsyncMock(return_value=None)

        response = client.get(f"/api/v1/bulk-content-scan/scans/{uuid4()}")

        assert response.status_code == 404


class TestCheckRecentScanEndpoint:
    """Test GET /bulk-content-scan/communities/{community_server_id}/has-recent-scan endpoint."""

    def test_check_recent_scan_returns_200(self, client):
        """Should return whether community has recent scan."""
        with patch(
            "src.bulk_content_scan.router.has_recent_scan",
            new=AsyncMock(return_value=True),
        ):
            response = client.get(
                f"/api/v1/bulk-content-scan/communities/{uuid4()}/has-recent-scan"
            )

        assert response.status_code == 200
        data = response.json()
        assert "has_recent_scan" in data

    def test_check_recent_scan_returns_false_when_none(self, client):
        """Should return false when no recent scan exists."""
        with patch(
            "src.bulk_content_scan.router.has_recent_scan",
            new=AsyncMock(return_value=False),
        ):
            response = client.get(
                f"/api/v1/bulk-content-scan/communities/{uuid4()}/has-recent-scan"
            )

        data = response.json()
        assert data["has_recent_scan"] is False


class TestCreateNoteRequestsEndpoint:
    """Test POST /bulk-content-scan/scans/{scan_id}/note-requests endpoint."""

    def test_create_note_requests_returns_201(self, client, mock_service):
        """AC #7: POST creates note requests for selected messages."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.create_note_requests_for_messages",
            new=AsyncMock(return_value=["req_1", "req_2"]),
        ):
            response = client.post(
                f"/api/v1/bulk-content-scan/scans/{scan_id}/note-requests",
                json={
                    "message_ids": ["msg_1", "msg_2"],
                    "generate_ai_notes": False,
                },
            )

        assert response.status_code == 201

    def test_create_note_requests_returns_count(self, client, mock_service):
        """Response should include count of created requests."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.router.create_note_requests_for_messages",
            new=AsyncMock(return_value=["req_1", "req_2", "req_3"]),
        ):
            response = client.post(
                f"/api/v1/bulk-content-scan/scans/{scan_id}/note-requests",
                json={
                    "message_ids": ["msg_1", "msg_2", "msg_3"],
                },
            )

        data = response.json()
        assert "created_count" in data
        assert data["created_count"] == 3

    def test_create_note_requests_requires_message_ids(self, client, mock_service):
        """Should validate that message_ids is not empty."""
        scan_id = mock_service.get_scan.return_value.id

        response = client.post(
            f"/api/v1/bulk-content-scan/scans/{scan_id}/note-requests",
            json={
                "message_ids": [],  # Invalid - empty
            },
        )

        assert response.status_code == 422

    def test_create_note_requests_returns_404_for_missing_scan(self, client, mock_service):
        """Should return 404 if scan doesn't exist."""
        mock_service.get_scan = AsyncMock(return_value=None)

        response = client.post(
            f"/api/v1/bulk-content-scan/scans/{uuid4()}/note-requests",
            json={
                "message_ids": ["msg_1"],
            },
        )

        assert response.status_code == 404
