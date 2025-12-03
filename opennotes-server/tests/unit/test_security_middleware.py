import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-jwt-secret-key-for-testing-only-32-chars-min"
TEST_CREDENTIALS_ENCRYPTION_KEY = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="
TEST_INTERNAL_SERVICE_SECRET = "test-internal-service-secret-must-be-32-chars-min"


@pytest.mark.unit
def test_security_headers_middleware():
    from src.middleware.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "geolocation=(), microphone=(), camera=()"


@pytest.mark.unit
def test_csp_header_present():
    from src.middleware.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200

    csp_header = response.headers.get("Content-Security-Policy")
    csp_report_only_header = response.headers.get("Content-Security-Policy-Report-Only")

    assert csp_header is not None or csp_report_only_header is not None

    csp_value = csp_header or csp_report_only_header
    assert "default-src 'none'" in csp_value
    assert "frame-ancestors 'none'" in csp_value
    assert "base-uri 'self'" in csp_value
    assert "form-action 'self'" in csp_value


@pytest.mark.unit
def test_cross_origin_headers_present():
    from src.middleware.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200
    assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.unit
def test_csp_production_mode(monkeypatch):
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    # Import middleware AFTER patching settings
    from src.middleware.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    # Also patch the settings in the middleware module
    import src.middleware.security

    monkeypatch.setattr(src.middleware.security, "settings", test_settings)

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert "Content-Security-Policy-Report-Only" not in response.headers


@pytest.mark.unit
def test_csp_development_mode(monkeypatch):
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    # Import middleware AFTER patching settings
    from src.middleware.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    # Also patch the settings in the middleware module
    import src.middleware.security

    monkeypatch.setattr(src.middleware.security, "settings", test_settings)

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200
    assert "Content-Security-Policy-Report-Only" in response.headers
    assert "Content-Security-Policy" not in response.headers
