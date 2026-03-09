"""Unit tests for JSON:API notes endpoint input validation."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid4()
    user.role = "admin"
    user.is_superuser = False
    user.is_active = True
    user.api_keys = []
    return user


@pytest.fixture
def app_with_notes_router(mock_user):
    from src.auth.dependencies import get_current_user_or_api_key
    from src.database import get_db
    from src.notes.notes_jsonapi_router import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v2")

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        return MagicMock()

    test_app.dependency_overrides[get_current_user_or_api_key] = override_get_current_user
    test_app.dependency_overrides[get_db] = override_get_db

    return test_app


@pytest.fixture
def client(app_with_notes_router):
    return TestClient(app_with_notes_router, raise_server_exceptions=False)


class TestRaterIdNotInValidation:
    def test_invalid_uuid_returns_400(self, client):
        response = client.get("/api/v2/notes?filter[rater_id__not_in]=not-a-uuid")
        assert response.status_code == 400
        assert "valid UUIDs" in response.json()["detail"]

    def test_discord_snowflake_returns_400(self, client):
        response = client.get("/api/v2/notes?filter[rater_id__not_in]=123456789012345678")
        assert response.status_code == 400
        assert "valid UUIDs" in response.json()["detail"]

    def test_mixed_valid_and_invalid_returns_400(self, client):
        valid_uuid = str(uuid4())
        response = client.get(f"/api/v2/notes?filter[rater_id__not_in]={valid_uuid},not-a-uuid")
        assert response.status_code == 400
        assert "valid UUIDs" in response.json()["detail"]

    def test_valid_uuid_does_not_return_400(self, client):
        valid_uuid = str(uuid4())
        response = client.get(f"/api/v2/notes?filter[rater_id__not_in]={valid_uuid}")
        assert response.status_code != 400
