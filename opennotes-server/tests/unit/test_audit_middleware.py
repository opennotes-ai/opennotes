"""
Tests for AuditMiddleware token verification logging.

This test verifies that when token verification fails in the audit middleware,
appropriate logging occurs to help track failed authentication attempts.

Security requirement (task-797.02):
- Token verification failures should be logged with appropriate detail
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-jwt-secret-key-for-testing-only-32-chars-min"
TEST_CREDENTIALS_ENCRYPTION_KEY = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="


@pytest.mark.unit
def test_token_verification_failure_is_logged(monkeypatch, caplog):
    """When token verification fails, a warning should be logged."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"status": "ok"}

    with patch("src.middleware.audit.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = None

        with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
            client = TestClient(app)
            response = client.post(
                "/test",
                headers={"Authorization": "Bearer invalid-token-here"},
                json={"data": "test"},
            )

        assert response.status_code == 200

        mock_verify.assert_called_once_with("invalid-token-here")

        assert any("Token verification failed" in record.message for record in caplog.records), (
            f"Expected 'Token verification failed' in logs, got: {[r.message for r in caplog.records]}"
        )


@pytest.mark.unit
def test_token_verification_failure_logs_request_path(monkeypatch, caplog):
    """Token verification failure log should include the request path."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.post("/api/v1/notes")
    async def test_endpoint():
        return {"status": "ok"}

    with patch("src.middleware.audit.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = None

        with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
            client = TestClient(app)
            response = client.post(
                "/api/v1/notes",
                headers={"Authorization": "Bearer bad-token"},
                json={"data": "test"},
            )

        assert response.status_code == 200

        log_found = False
        for record in caplog.records:
            if "Token verification failed" in record.message:
                log_found = True
                assert hasattr(record, "path") or "/api/v1/notes" in record.message, (
                    "Log should include request path"
                )

        assert log_found, "Expected token verification failure to be logged"


@pytest.mark.unit
def test_valid_token_does_not_log_warning(monkeypatch, caplog):
    """When token verification succeeds, no warning should be logged."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_token_data = MagicMock()
    mock_token_data.user_id = uuid4()

    with patch("src.middleware.audit.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = mock_token_data

        with patch("src.middleware.audit.call_persist_audit_log"):
            with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
                client = TestClient(app)
                response = client.post(
                    "/test",
                    headers={"Authorization": "Bearer valid-token"},
                    json={"data": "test"},
                )

            assert response.status_code == 200

            verification_failure_logs = [
                record for record in caplog.records if "Token verification failed" in record.message
            ]
            assert len(verification_failure_logs) == 0, (
                "No token verification failure warning should be logged for valid tokens"
            )


@pytest.mark.unit
def test_missing_auth_header_does_not_log_warning(monkeypatch, caplog):
    """When no auth header is present, no warning should be logged (not a failure)."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
        client = TestClient(app)
        response = client.get("/test")

    assert response.status_code == 200

    verification_failure_logs = [
        record for record in caplog.records if "Token verification failed" in record.message
    ]
    assert len(verification_failure_logs) == 0, (
        "No warning should be logged when auth header is missing (anonymous request)"
    )


@pytest.mark.unit
def test_api_key_with_bearer_token_skips_jwt_verification(monkeypatch, caplog):
    """When X-API-Key is present alongside Bearer token, skip JWT verification (GCP IAM scenario)."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"status": "ok"}

    with patch("src.middleware.audit.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = None

        with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
            client = TestClient(app)
            response = client.post(
                "/test",
                headers={
                    "Authorization": "Bearer gcp-iam-identity-token",
                    "X-API-Key": "opk_test_secretkey123",
                },
                json={"data": "test"},
            )

        assert response.status_code == 200

        mock_verify.assert_not_called()

        verification_failure_logs = [
            record for record in caplog.records if "Token verification failed" in record.message
        ]
        assert len(verification_failure_logs) == 0, (
            "No warning should be logged when X-API-Key authenticates the request"
        )


@pytest.mark.unit
def test_internal_auth_with_bearer_token_skips_jwt_verification(monkeypatch, caplog):
    """When X-Internal-Auth is present alongside Bearer token, skip JWT verification."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"status": "ok"}

    with patch("src.middleware.audit.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = None

        with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
            client = TestClient(app)
            response = client.post(
                "/test",
                headers={
                    "Authorization": "Bearer gcp-iam-identity-token",
                    "X-Internal-Auth": "some-internal-token",
                },
                json={"data": "test"},
            )

        assert response.status_code == 200

        mock_verify.assert_not_called()

        verification_failure_logs = [
            record for record in caplog.records if "Token verification failed" in record.message
        ]
        assert len(verification_failure_logs) == 0, (
            "No warning should be logged when X-Internal-Auth authenticates the request"
        )


@pytest.mark.unit
def test_bearer_only_still_verifies_and_warns(monkeypatch, caplog):
    """When only Bearer token is present (no service auth headers), JWT verification still happens."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.audit import AuditMiddleware

    app = FastAPI()
    app.add_middleware(AuditMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"status": "ok"}

    with patch("src.middleware.audit.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = None

        with caplog.at_level(logging.WARNING, logger="src.middleware.audit"):
            client = TestClient(app)
            response = client.post(
                "/test",
                headers={"Authorization": "Bearer bad-app-jwt"},
                json={"data": "test"},
            )

        assert response.status_code == 200

        mock_verify.assert_called_once_with("bad-app-jwt")

        assert any("Token verification failed" in record.message for record in caplog.records), (
            "Warning should still be logged for genuine JWT verification failures"
        )
