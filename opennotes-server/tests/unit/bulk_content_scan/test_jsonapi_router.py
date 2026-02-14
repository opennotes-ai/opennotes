"""Tests for Bulk Content Scan JSON:API v2 router."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pendulum
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SAMPLE_FACT_CHECK_ID = UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def mock_flagged_messages():
    """Create mock flagged messages for testing."""
    from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch

    return [
        FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test message 1",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
            matches=[
                SimilarityMatch(
                    score=0.85,
                    matched_claim="Test claim 1",
                    matched_source="https://example.com/1",
                    fact_check_item_id=SAMPLE_FACT_CHECK_ID,
                )
            ],
        ),
        FlaggedMessage(
            message_id="msg_2",
            channel_id="ch_1",
            content="Test message 2",
            author_id="user_2",
            timestamp=pendulum.now("UTC"),
            matches=[
                SimilarityMatch(
                    score=0.75,
                    matched_claim="Test claim 2",
                    matched_source="https://example.com/2",
                    fact_check_item_id=SAMPLE_FACT_CHECK_ID,
                )
            ],
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
    mock_scan_log.initiated_at = pendulum.now("UTC")
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
def mock_session():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_community_member():
    """Create a mock community member for authorization."""
    from unittest.mock import MagicMock

    member = MagicMock()
    member.profile_id = uuid4()
    member.community_id = uuid4()
    member.role = "admin"
    member.is_active = True
    member.banned_at = None
    return member


@pytest.fixture
def app_with_router(mock_service, mock_user, mock_session, mock_community_member):
    """Create a FastAPI app with the bulk content scan JSON:API router."""
    from src.bulk_content_scan.jsonapi_router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v2")

    async def override_get_service():
        return mock_service

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        return mock_session

    from src.auth.dependencies import get_current_user_or_api_key
    from src.bulk_content_scan import jsonapi_router as router_module
    from src.database import get_db

    app.dependency_overrides[router_module.get_bulk_scan_service] = override_get_service
    app.dependency_overrides[get_current_user_or_api_key] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    return app


@pytest.fixture
def client(app_with_router):
    """Create a test client."""
    return TestClient(app_with_router)


class TestInitiateScanEndpoint:
    """Test POST /bulk-scans endpoint."""

    def test_initiate_scan_returns_201_with_jsonapi_format(
        self, client, mock_service, mock_community_member
    ):
        """POST /bulk-scans returns JSON:API formatted response."""
        community_server_id = str(uuid4())
        mock_profile_id = uuid4()

        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.get_profile_id_from_user",
                new=AsyncMock(return_value=mock_profile_id),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.dispatch_content_scan_workflow",
                new=AsyncMock(return_value="mock-workflow-id"),
            ),
        ):
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

    def test_initiate_scan_includes_status_in_attributes(
        self, client, mock_service, mock_community_member
    ):
        """Response attributes should include status."""
        mock_profile_id = uuid4()

        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.get_profile_id_from_user",
                new=AsyncMock(return_value=mock_profile_id),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.dispatch_content_scan_workflow",
                new=AsyncMock(return_value="mock-workflow-id"),
            ),
        ):
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

    def test_get_scan_returns_200_with_jsonapi_format(
        self, client, mock_service, mock_community_member
    ):
        """GET returns JSON:API formatted response with included flagged messages."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
            response = client.get(f"/api/v2/bulk-scans/{scan_id}")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "bulk-scans"
        assert "included" in data
        assert "jsonapi" in data
        mock_service.get_scan.assert_called_once()

    def test_get_scan_includes_flagged_messages(self, client, mock_service, mock_community_member):
        """Response should include flagged messages as related resources."""
        scan_id = mock_service.get_scan.return_value.id

        with patch(
            "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
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

    def test_check_recent_scan_returns_200_with_jsonapi_format(self, client, mock_community_member):
        """Should return JSON:API formatted response."""
        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.has_recent_scan",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
        ):
            response = client.get(f"/api/v2/bulk-scans/communities/{uuid4()}/recent")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "bulk-scan-status"
        assert data["data"]["attributes"]["has_recent_scan"] is True

    def test_check_recent_scan_returns_false(self, client, mock_community_member):
        """Should return false when no recent scan exists."""
        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.has_recent_scan",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
        ):
            response = client.get(f"/api/v2/bulk-scans/communities/{uuid4()}/recent")

        data = response.json()
        assert data["data"]["attributes"]["has_recent_scan"] is False


class TestCreateNoteRequestsEndpoint:
    """Test POST /bulk-scans/{scan_id}/note-requests endpoint."""

    def test_create_note_requests_returns_201_with_jsonapi_format(
        self, client, mock_service, mock_community_member
    ):
        """POST creates note requests with JSON:API response."""
        scan_id = mock_service.get_scan.return_value.id

        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.create_note_requests_from_flagged_messages",
                new=AsyncMock(return_value=["req_1", "req_2"]),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
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

    def test_create_note_requests_includes_created_count(
        self, client, mock_service, mock_community_member
    ):
        """Response should include count and IDs of created requests."""
        scan_id = mock_service.get_scan.return_value.id

        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.create_note_requests_from_flagged_messages",
                new=AsyncMock(return_value=["req_1", "req_2", "req_3"]),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
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

    def test_create_note_requests_returns_400_for_no_flagged_results(
        self, client, mock_service, mock_community_member
    ):
        """Should return 400 in JSON:API error format."""
        scan_id = mock_service.get_scan.return_value.id
        mock_service.get_flagged_results = AsyncMock(return_value=[])

        with patch(
            "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
            new=AsyncMock(return_value=mock_community_member),
        ):
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


class TestGenerateExplanationEndpoint:
    """Test POST /bulk-scans/explanations endpoint."""

    def test_generate_explanation_returns_201_with_jsonapi_format(
        self, client, mock_community_member
    ):
        """POST /bulk-scans/explanations returns JSON:API formatted response."""
        fact_check_id = SAMPLE_FACT_CHECK_ID
        community_server_id = uuid4()

        mock_fact_check_item = MagicMock()
        mock_fact_check_item.id = fact_check_id
        mock_fact_check_item.title = "Vaccine Claim"
        mock_fact_check_item.content = "This claim is false"
        mock_fact_check_item.rating = "false"
        mock_fact_check_item.source_url = "https://snopes.com/fact-check/123"

        mock_ai_note_writer = AsyncMock()
        mock_ai_note_writer.generate_scan_explanation = AsyncMock(
            return_value="This message contains a claim that has been debunked by fact-checkers."
        )

        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.get_fact_check_item_by_id",
                new=AsyncMock(return_value=mock_fact_check_item),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.get_ai_note_writer",
                return_value=mock_ai_note_writer,
            ),
        ):
            response = client.post(
                "/api/v2/bulk-scans/explanations",
                json={
                    "data": {
                        "type": "scan-explanations",
                        "attributes": {
                            "original_message": "COVID vaccines contain microchips",
                            "fact_check_item_id": str(fact_check_id),
                            "community_server_id": str(community_server_id),
                        },
                    },
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "scan-explanations"
        assert "explanation" in data["data"]["attributes"]
        assert "debunked" in data["data"]["attributes"]["explanation"]

    def test_generate_explanation_returns_404_for_missing_fact_check_item(
        self, client, mock_community_member
    ):
        """Should return 404 if fact_check_item_id not found."""
        community_server_id = uuid4()

        with (
            patch(
                "src.bulk_content_scan.jsonapi_router.verify_scan_admin_access",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.bulk_content_scan.jsonapi_router.get_fact_check_item_by_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            response = client.post(
                "/api/v2/bulk-scans/explanations",
                json={
                    "data": {
                        "type": "scan-explanations",
                        "attributes": {
                            "original_message": "Test message",
                            "fact_check_item_id": str(uuid4()),
                            "community_server_id": str(community_server_id),
                        },
                    },
                },
            )

        assert response.status_code == 404
        assert "errors" in response.json()
