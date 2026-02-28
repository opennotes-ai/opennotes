from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dbos._error import (
    DBOSConflictingWorkflowError,
    DBOSQueueDeduplicatedError,
    DBOSWorkflowConflictIDError,
)
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid4()
    user.discord_id = "123456789"
    user.email = None
    user.username = "testuser"
    user.full_name = "Test User"
    return user


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_community_member():
    member = MagicMock()
    member.profile_id = uuid4()
    member.community_id = uuid4()
    member.role = "admin"
    member.is_active = True
    member.banned_at = None
    member.profile = MagicMock()
    member.profile.is_opennotes_admin = False
    return member


@pytest.fixture
def app_with_router(mock_user, mock_session):
    from src.auth.dependencies import get_current_user_or_api_key
    from src.community_servers.scoring_router import router
    from src.database import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api/v2")

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        return mock_session

    app.dependency_overrides[get_current_user_or_api_key] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    return app


@pytest.fixture
def client(app_with_router):
    return TestClient(app_with_router)


class TestScoreCommunityServerEndpoint:
    def test_returns_202_with_workflow_id_on_success(self, client, mock_community_member):
        community_server_id = str(uuid4())

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin_by_uuid",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(return_value=f"score-community-{community_server_id}"),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 202
        data = response.json()
        assert "workflow_id" in data
        assert data["workflow_id"] == f"score-community-{community_server_id}"
        assert "message" in data

    def test_returns_404_when_verify_admin_raises_not_found(self, client):
        community_server_id = str(uuid4())

        with patch(
            "src.community_servers.scoring_router.verify_community_admin_by_uuid",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Community server {community_server_id} not found",
                )
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_422_for_invalid_uuid(self, client):
        response = client.post("/api/v2/community-servers/not-a-uuid/score")
        assert response.status_code == 422

    def test_returns_409_on_workflow_conflict_id(self, client, mock_community_member):
        community_server_id = str(uuid4())

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin_by_uuid",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(
                    side_effect=DBOSWorkflowConflictIDError("score-community-123-1709000000")
                ),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"].lower()

    def test_returns_409_on_conflicting_workflow(self, client, mock_community_member):
        community_server_id = str(uuid4())

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin_by_uuid",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(
                    side_effect=DBOSConflictingWorkflowError("score-community-123-1709000000")
                ),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 409

    def test_returns_409_on_queue_deduplicated(self, client, mock_community_member):
        community_server_id = str(uuid4())

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin_by_uuid",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(
                    side_effect=DBOSQueueDeduplicatedError(
                        "score-community-123", "community_scoring", "dedup-key"
                    )
                ),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 409

    def test_reraises_unexpected_errors(self, app_with_router, mock_community_member):
        community_server_id = str(uuid4())

        no_raise_client = TestClient(app_with_router, raise_server_exceptions=False)

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin_by_uuid",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(side_effect=RuntimeError("Database connection failed")),
            ),
        ):
            response = no_raise_client.post(
                f"/api/v2/community-servers/{community_server_id}/score"
            )

        assert response.status_code == 500

    def test_response_contains_message_with_community_id(self, client, mock_community_member):
        community_server_id = str(uuid4())

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin_by_uuid",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(return_value="wf-123"),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 202
        assert community_server_id in response.json()["message"]

    def test_returns_403_when_admin_check_fails(self, client):
        community_server_id = str(uuid4())

        with patch(
            "src.community_servers.scoring_router.verify_community_admin_by_uuid",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. User role 'member' cannot perform this action. Required: admin, moderator, Discord Manage Server permission, or Open Notes admin.",
                )
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 403
        assert "insufficient permissions" in response.json()["detail"].lower()

    def test_returns_403_detail_includes_required_roles(self, client):
        community_server_id = str(uuid4())

        with patch(
            "src.community_servers.scoring_router.verify_community_admin_by_uuid",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. User role 'member' cannot perform this action. Required: admin, moderator, Discord Manage Server permission, or Open Notes admin.",
                )
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        detail = response.json()["detail"]
        assert "admin" in detail.lower()
        assert "moderator" in detail.lower()
