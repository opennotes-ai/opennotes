"""Tests for Bulk Content Scan JSON:API v2 router."""

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
            message_id="msg_1",
            channel_id="ch_1",
            content="Test message 1",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            match_score=0.85,
            matched_claim="Test claim 1",
            matched_source="https://example.com/1",
        ),
        FlaggedMessage(
            message_id="msg_2",
            channel_id="ch_1",
            content="Test message 2",
            author_id="user_2",
            timestamp=datetime.now(UTC),
            match_score=0.75,
            matched_claim="Test claim 2",
            matched_source="https://example.com/2",
        ),
    ]


@pytest.fixture
def mock_service(mock_flagged_messages):
    """Create a mock BulkContentScanService."""
    from src.bulk_content_scan.models import BulkContentScanLog

    service = AsyncMock()

    mock_scan_log = MagicMock(spec=BulkContentScanLog)
    mock_scan_log.id = uuid4()
    mock_scan_log.community_server_id = uuid4()
    mock_scan_log.status = "pending"
    mock_scan_log.initiated_at = datetime.now(UTC)
    mock_scan_log.completed_at = None
    mock_scan_log.messages_scanned = 0
    mock_scan_log.messages_flagged = 0

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
def app_with_router(mock_service, mock_user):
    """Create a FastAPI app with the bulk content scan JSON:API router."""
    from src.bulk_content_scan.jsonapi_router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v2")

    async def override_get_service():
        return mock_service

    async def override_get_current_user():
        return mock_user

    from src.bulk_content_scan import jsonapi_router as router_module

    app.dependency_overrides[router_module.get_bulk_scan_service] = override_get_service
    app.dependency_overrides[router_module.get_current_user_or_api_key] = override_get_current_user

    return app


@pytest.fixture
def client(app_with_router):
    """Create a test client."""
    return TestClient(app_with_router)


class TestInitiateScanEndpoint:
    """Test POST /bulk-scans endpoint."""

    def test_initiate_scan_returns_201_with_jsonapi_format(self, client, mock_service):
        """POST /bulk-scans returns JSON:API formatted response."""
        community_server_id = str(uuid4())

        response = client.post(
            "/api/v2/bulk-scans",
            json={
                "data": {
                    "type": "bulk-scans",
                    "attributes": {
                        "community_server_id": community_server_id,
                        "scan_window_days": 7,
                    },
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "bulk-scans"
        assert "id" in data["data"]
        assert "attributes" in data["data"]
        assert "jsonapi" in data
        mock_service.initiate_scan.assert_called_once()

    def test_initiate_scan_includes_status_in_attributes(self, client, mock_service):
        """Response attributes should include status."""
        response = client.post(
            "/api/v2/bulk-scans",
            json={
                "data": {
                    "type": "bulk-scans",
                    "attributes": {
                        "community_server_id": str(uuid4()),
                        "scan_window_days": 7,
                    },
                },
            },
        )

        attrs = response.json()["data"]["attributes"]
        assert "status" in attrs
        assert "initiated_at" in attrs

    def test_initiate_scan_validates_window_days(self, client):
        """Scan window days must be within valid range."""
        response = client.post(
            "/api/v2/bulk-scans",
            json={
                "data": {
                    "type": "bulk-scans",
                    "attributes": {
                        "community_server_id": str(uuid4()),
                        "scan_window_days": 0,
                    },
                },
            },
        )

        assert response.status_code == 422


class TestGetScanResultsEndpoint:
    """Test GET /bulk-scans/{scan_id} endpoint."""

    def test_get_scan_returns_200_with_jsonapi_format(self, client, mock_service):
        """GET returns JSON:API formatted response with included flagged messages."""
        scan_id = mock_service.get_scan.return_value.id

        response = client.get(f"/api/v2/bulk-scans/{scan_id}")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "bulk-scans"
        assert "included" in data
        assert "jsonapi" in data
        mock_service.get_scan.assert_called_once()

    def test_get_scan_includes_flagged_messages(self, client, mock_service):
        """Response should include flagged messages as related resources."""
        scan_id = mock_service.get_scan.return_value.id

        response = client.get(f"/api/v2/bulk-scans/{scan_id}")

        data = response.json()
        assert len(data["included"]) == 2
        for item in data["included"]:
            assert item["type"] == "flagged-messages"
            assert "id" in item
            assert "attributes" in item

    def test_get_scan_returns_404_with_jsonapi_error(self, client, mock_service):
        """Should return 404 in JSON:API error format."""
        mock_service.get_scan = AsyncMock(return_value=None)

        response = client.get(f"/api/v2/bulk-scans/{uuid4()}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data
        assert data["errors"][0]["status"] == "404"


class TestCheckRecentScanEndpoint:
    """Test GET /bulk-scans/communities/{community_server_id}/recent endpoint."""

    def test_check_recent_scan_returns_200_with_jsonapi_format(self, client):
        """Should return JSON:API formatted response."""
        with patch(
            "src.bulk_content_scan.jsonapi_router.has_recent_scan",
            new=AsyncMock(return_value=True),
        ):
            response = client.get(f"/api/v2/bulk-scans/communities/{uuid4()}/recent")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "bulk-scan-status"
        assert data["data"]["attributes"]["has_recent_scan"] is True

    def test_check_recent_scan_returns_false(self, client):
        """Should return false when no recent scan exists."""
        with patch(
            "src.bulk_content_scan.jsonapi_router.has_recent_scan",
            new=AsyncMock(return_value=False),
        ):
            response = client.get(f"/api/v2/bulk-scans/communities/{uuid4()}/recent")

        data = response.json()
        assert data["data"]["attributes"]["has_recent_scan"] is False


class TestCreateNoteRequestsEndpoint:
    """Test POST /bulk-scans/{scan_id}/note-requests endpoint."""

    def test_create_note_requests_returns_201_with_jsonapi_format(self, client, mock_service):
        """POST creates note requests with JSON:API response."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.jsonapi_router.create_note_requests_for_messages",
            new=AsyncMock(return_value=["req_1", "req_2"]),
        ):
            response = client.post(
                f"/api/v2/bulk-scans/{scan_id}/note-requests",
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_1", "msg_2"],
                            "generate_ai_notes": False,
                        },
                    },
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "note-request-batches"

    def test_create_note_requests_includes_created_count(self, client, mock_service):
        """Response should include count and IDs of created requests."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.jsonapi_router.create_note_requests_for_messages",
            new=AsyncMock(return_value=["req_1", "req_2", "req_3"]),
        ):
            response = client.post(
                f"/api/v2/bulk-scans/{scan_id}/note-requests",
                json={
                    "data": {
                        "type": "note-requests",
                        "attributes": {
                            "message_ids": ["msg_1", "msg_2", "msg_3"],
                        },
                    },
                },
            )

        attrs = response.json()["data"]["attributes"]
        assert attrs["created_count"] == 3
        assert len(attrs["request_ids"]) == 3

    def test_create_note_requests_requires_message_ids(self, client, mock_service):
        """Should validate that message_ids is not empty."""
        scan_id = mock_service.get_scan.return_value.id

        response = client.post(
            f"/api/v2/bulk-scans/{scan_id}/note-requests",
            json={
                "data": {
                    "type": "note-requests",
                    "attributes": {
                        "message_ids": [],
                    },
                },
            },
        )

        assert response.status_code == 422

    def test_create_note_requests_returns_404_for_missing_scan(self, client, mock_service):
        """Should return 404 in JSON:API error format."""
        mock_service.get_scan = AsyncMock(return_value=None)

        response = client.post(
            f"/api/v2/bulk-scans/{uuid4()}/note-requests",
            json={
                "data": {
                    "type": "note-requests",
                    "attributes": {
                        "message_ids": ["msg_1"],
                    },
                },
            },
        )

        assert response.status_code == 404
        assert "errors" in response.json()

    def test_create_note_requests_returns_400_for_no_flagged_results(self, client, mock_service):
        """Should return 400 in JSON:API error format."""
        scan_id = mock_service.get_scan.return_value.id
        mock_service.get_flagged_results = AsyncMock(return_value=[])

        response = client.post(
            f"/api/v2/bulk-scans/{scan_id}/note-requests",
            json={
                "data": {
                    "type": "note-requests",
                    "attributes": {
                        "message_ids": ["msg_1"],
                    },
                },
            },
        )

        assert response.status_code == 400
        assert "errors" in response.json()
