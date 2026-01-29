"""
Tests for AuthenticatedUserContextMiddleware.

This module tests that user context is correctly extracted from JWT tokens
and set as OpenTelemetry span attributes and baggage.

Created for task-1035: Add user information to Google Cloud Trace spans.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from jose import jwt
from starlette.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-jwt-secret-key-for-testing-only-32-chars-min"
TEST_JWT_ALGORITHM = "HS256"
TEST_CREDENTIALS_ENCRYPTION_KEY = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="


def create_test_jwt(user_id: str, username: str, role: str) -> str:
    """Create a valid JWT token for testing."""
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    return jwt.encode(payload, TEST_JWT_SECRET_KEY, algorithm=TEST_JWT_ALGORITHM)


@pytest.mark.unit
def test_user_context_extracted_from_jwt(monkeypatch):
    """User ID, username, and role should be extracted from valid JWT."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        JWT_ALGORITHM=TEST_JWT_ALGORITHM,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.user_context import AuthenticatedUserContextMiddleware

    app = FastAPI()
    app.add_middleware(AuthenticatedUserContextMiddleware)

    user_id = str(uuid4())
    username = "testuser"
    role = "admin"
    token = create_test_jwt(user_id, username, role)

    captured_attributes = {}

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_span = MagicMock()

    def capture_attribute(key, value):
        captured_attributes[key] = value

    mock_span.set_attribute = capture_attribute

    with (
        patch("src.middleware.user_context.trace.get_current_span", return_value=mock_span),
        patch("src.middleware.user_context.baggage.set_baggage") as mock_baggage,
    ):
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert captured_attributes.get("enduser.id") == user_id, (
        f"enduser.id mismatch. Expected: {user_id}, Got: {captured_attributes.get('enduser.id')}. "
        f"Captured keys: {list(captured_attributes.keys())}. "
        f"All captured: {captured_attributes}"
    )
    assert captured_attributes.get("user.username") == username
    assert captured_attributes.get("enduser.role") == role

    baggage_calls = [call[0] for call in mock_baggage.call_args_list]
    assert any(call[0] == "enduser.id" and call[1] == user_id for call in baggage_calls)


@pytest.mark.unit
def test_no_user_context_without_auth_header(monkeypatch):
    """No user context should be set when Authorization header is missing."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        JWT_ALGORITHM=TEST_JWT_ALGORITHM,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.user_context import AuthenticatedUserContextMiddleware

    app = FastAPI()
    app.add_middleware(AuthenticatedUserContextMiddleware)

    captured_attributes = {}

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_span = MagicMock()

    def capture_attribute(key, value):
        captured_attributes[key] = value

    mock_span.set_attribute = capture_attribute

    with patch("src.middleware.user_context.trace.get_current_span", return_value=mock_span):
        client = TestClient(app)
        response = client.get("/test")

    assert response.status_code == 200
    assert "enduser.id" not in captured_attributes
    assert "user.username" not in captured_attributes
    assert "enduser.role" not in captured_attributes


@pytest.mark.unit
def test_invalid_jwt_does_not_crash(monkeypatch):
    """Invalid JWT should not crash the middleware, just skip setting attributes."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        JWT_ALGORITHM=TEST_JWT_ALGORITHM,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.user_context import AuthenticatedUserContextMiddleware

    app = FastAPI()
    app.add_middleware(AuthenticatedUserContextMiddleware)

    captured_attributes = {}

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_span = MagicMock()

    def capture_attribute(key, value):
        captured_attributes[key] = value

    mock_span.set_attribute = capture_attribute

    with patch("src.middleware.user_context.trace.get_current_span", return_value=mock_span):
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 200
    assert "enduser.id" not in captured_attributes


@pytest.mark.unit
def test_non_bearer_auth_header_ignored(monkeypatch):
    """Non-Bearer Authorization headers should be ignored."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        JWT_ALGORITHM=TEST_JWT_ALGORITHM,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.user_context import AuthenticatedUserContextMiddleware

    app = FastAPI()
    app.add_middleware(AuthenticatedUserContextMiddleware)

    captured_attributes = {}

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_span = MagicMock()

    def capture_attribute(key, value):
        captured_attributes[key] = value

    mock_span.set_attribute = capture_attribute

    with patch("src.middleware.user_context.trace.get_current_span", return_value=mock_span):
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 200
    assert "enduser.id" not in captured_attributes
