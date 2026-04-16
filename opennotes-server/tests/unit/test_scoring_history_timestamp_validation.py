"""Tests for timestamp path parameter validation on scoring history endpoint.

Verifies that the timestamp path parameter only accepts ISO 8601 formatted
timestamps (YYYY-MM-DDTHH:MM:SSZ), preventing path traversal and injection
attacks via malformed timestamp values.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import get_current_user_or_api_key
from src.main import app


@pytest.fixture
def mock_admin_user():
    user = MagicMock()
    user.id = uuid4()
    user.discord_id = "123456789"
    user.email = None
    user.username = "testadmin"
    user.full_name = "Test Admin"
    user.platform_roles = ["platform_admin"]
    user.principal_type = "human"
    user.is_active = True
    user.banned_at = None
    return user


@pytest.fixture
def client(mock_admin_user):
    app.dependency_overrides[get_current_user_or_api_key] = lambda: mock_admin_user
    app.state.startup_complete = True
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)
    app.state.startup_complete = False


COMMUNITY_SERVER_ID = "00000000-0000-0000-0000-000000000001"
BASE_URL = f"/api/v2/community-servers/{COMMUNITY_SERVER_ID}/scoring-history"


class TestTimestampPathTraversalRejection:
    def test_invalid_timestamp_format_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/not-a-timestamp")
        assert response.status_code == 422

    def test_partial_iso_date_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/2025-01-01")
        assert response.status_code == 422

    def test_timestamp_without_z_suffix_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/2025-01-01T00:00:00")
        assert response.status_code == 422

    def test_timestamp_with_offset_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/2025-01-01T00:00:00+00:00")
        assert response.status_code == 422

    def test_dot_dot_without_slash_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/..2025-01-01T00:00:00Z")
        assert response.status_code == 422

    def test_traversal_encoded_slashes_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/..%2F..%2Fother%2F2025-01-01T00:00:00Z")
        assert response.status_code in (404, 422)

    def test_invalid_timestamp_error_message(self, client: TestClient):
        response = client.get(f"{BASE_URL}/not-a-timestamp")
        assert response.status_code == 422
        body = response.json()
        assert "errors" in body
        assert "ISO 8601" in body["errors"][0]["detail"]

    def test_valid_iso8601_timestamp_not_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/2025-01-01T00:00:00Z")
        assert response.status_code != 422

    def test_valid_timestamp_with_nonzero_time_not_rejected(self, client: TestClient):
        response = client.get(f"{BASE_URL}/2025-12-31T23:59:59Z")
        assert response.status_code != 422
