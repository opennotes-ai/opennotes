from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
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
        community_server_id = "guild-123"
        mock_community = MagicMock()
        mock_community.id = uuid4()

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.get_community_server_by_platform_id",
                new=AsyncMock(return_value=mock_community),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(return_value=f"score-community-{mock_community.id}"),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 202
        data = response.json()
        assert "workflow_id" in data
        assert data["workflow_id"] == f"score-community-{mock_community.id}"
        assert "message" in data

    def test_returns_404_for_unknown_community(self, client, mock_community_member):
        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.get_community_server_by_platform_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            response = client.post("/api/v2/community-servers/nonexistent-guild/score")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_409_when_scoring_already_in_progress(self, client, mock_community_member):
        mock_community = MagicMock()
        mock_community.id = uuid4()

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.get_community_server_by_platform_id",
                new=AsyncMock(return_value=mock_community),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(side_effect=Exception("Workflow already exists for this ID")),
            ),
        ):
            response = client.post("/api/v2/community-servers/guild-123/score")

        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"].lower()

    def test_returns_409_on_duplicate_error(self, client, mock_community_member):
        mock_community = MagicMock()
        mock_community.id = uuid4()

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.get_community_server_by_platform_id",
                new=AsyncMock(return_value=mock_community),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(side_effect=Exception("Duplicate workflow entry detected")),
            ),
        ):
            response = client.post("/api/v2/community-servers/guild-123/score")

        assert response.status_code == 409

    def test_reraises_unexpected_errors(self, app_with_router, mock_community_member):
        mock_community = MagicMock()
        mock_community.id = uuid4()

        no_raise_client = TestClient(app_with_router, raise_server_exceptions=False)

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.get_community_server_by_platform_id",
                new=AsyncMock(return_value=mock_community),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(side_effect=RuntimeError("Database connection failed")),
            ),
        ):
            response = no_raise_client.post("/api/v2/community-servers/guild-123/score")

        assert response.status_code == 500

    def test_response_contains_message_with_community_id(self, client, mock_community_member):
        community_server_id = "my-guild-456"
        mock_community = MagicMock()
        mock_community.id = uuid4()

        with (
            patch(
                "src.community_servers.scoring_router.verify_community_admin",
                new=AsyncMock(return_value=mock_community_member),
            ),
            patch(
                "src.community_servers.scoring_router.get_community_server_by_platform_id",
                new=AsyncMock(return_value=mock_community),
            ),
            patch(
                "src.community_servers.scoring_router.dispatch_community_scoring",
                new=AsyncMock(return_value="wf-123"),
            ),
        ):
            response = client.post(f"/api/v2/community-servers/{community_server_id}/score")

        assert response.status_code == 202
        assert community_server_id in response.json()["message"]
