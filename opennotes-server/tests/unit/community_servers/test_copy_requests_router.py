from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid4()
    user.discord_id = "123456789"
    user.email = None
    user.username = "testadmin"
    user.full_name = "Test Admin"
    return user


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def app_with_router(mock_user, mock_session):
    from src.auth.dependencies import require_superuser_or_service_account
    from src.community_servers.copy_requests_router import router
    from src.database import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api/v2")

    def override_require_superuser():
        return mock_user

    async def override_get_db():
        return mock_session

    app.dependency_overrides[require_superuser_or_service_account] = override_require_superuser
    app.dependency_overrides[get_db] = override_get_db

    return app


@pytest.fixture
def client(app_with_router):
    return TestClient(app_with_router)


def _make_jsonapi_payload(source_id: str) -> dict:
    return {
        "data": {
            "type": "copy-requests",
            "attributes": {
                "source_community_server_id": source_id,
            },
        }
    }


class TestCopyRequestsEndpoint:
    def test_returns_202_with_jsonapi_response(self, client, mock_session):
        target_id = uuid4()
        source_id = uuid4()
        batch_job_id = uuid4()

        mock_target = MagicMock()
        mock_source = MagicMock()

        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = mock_target
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = mock_source

        mock_session.execute = AsyncMock(side_effect=[target_result, source_result])

        with patch(
            "src.community_servers.copy_requests_router.dispatch_copy_requests",
            new=AsyncMock(return_value=batch_job_id),
        ):
            response = client.post(
                f"/api/v2/community-servers/{target_id}/copy-requests",
                json=_make_jsonapi_payload(str(source_id)),
            )

        assert response.status_code == 202
        data = response.json()
        assert data["data"]["type"] == "batch-jobs"
        assert data["data"]["id"] == str(batch_job_id)
        assert data["data"]["attributes"]["job_type"] == "copy:requests"
        assert data["data"]["attributes"]["status"] == "pending"
        assert response.headers["content-type"] == "application/vnd.api+json"

    def test_returns_404_when_target_not_found(self, client, mock_session):
        target_id = uuid4()
        source_id = uuid4()

        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(return_value=target_result)

        response = client.post(
            f"/api/v2/community-servers/{target_id}/copy-requests",
            json=_make_jsonapi_payload(str(source_id)),
        )

        assert response.status_code == 404
        assert "target" in response.json()["detail"].lower()

    def test_returns_404_when_source_not_found(self, client, mock_session):
        target_id = uuid4()
        source_id = uuid4()

        mock_target = MagicMock()

        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = mock_target
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[target_result, source_result])

        response = client.post(
            f"/api/v2/community-servers/{target_id}/copy-requests",
            json=_make_jsonapi_payload(str(source_id)),
        )

        assert response.status_code == 404
        assert "source" in response.json()["detail"].lower()

    def test_returns_422_for_invalid_uuid(self, client):
        response = client.post(
            "/api/v2/community-servers/not-a-uuid/copy-requests",
            json=_make_jsonapi_payload(str(uuid4())),
        )
        assert response.status_code == 422

    def test_returns_422_for_missing_payload(self, client):
        target_id = uuid4()
        response = client.post(
            f"/api/v2/community-servers/{target_id}/copy-requests",
            json={},
        )
        assert response.status_code == 422

    def test_admin_only_rejects_non_admin(self, mock_session):
        from src.auth.dependencies import require_superuser_or_service_account
        from src.community_servers.copy_requests_router import router
        from src.database import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/v2")

        def override_require_superuser():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )

        async def override_get_db():
            return mock_session

        app.dependency_overrides[require_superuser_or_service_account] = override_require_superuser
        app.dependency_overrides[get_db] = override_get_db

        non_admin_client = TestClient(app)
        target_id = uuid4()
        source_id = uuid4()

        response = non_admin_client.post(
            f"/api/v2/community-servers/{target_id}/copy-requests",
            json=_make_jsonapi_payload(str(source_id)),
        )

        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()
