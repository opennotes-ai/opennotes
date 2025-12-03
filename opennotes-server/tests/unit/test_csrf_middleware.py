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
def test_csrf_middleware_disabled_in_development(monkeypatch):
    """CSRF protection should be disabled in development environment."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    # Patch the settings in the middleware module
    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"message": "test"}

    client = TestClient(app)

    # Should succeed without CSRF token in development
    response = client.post("/test")
    assert response.status_code == 200


@pytest.mark.unit
def test_csrf_middleware_enabled_in_production(monkeypatch):
    """CSRF protection should be enabled in production environment."""
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

    # Patch the settings in the middleware module
    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()

    @app.post("/test")
    async def test_endpoint():
        return {"message": "test"}

    app.add_middleware(CSRFMiddleware)

    client = TestClient(app, raise_server_exceptions=False)

    # Should fail without CSRF token in production
    response = client.post("/test")
    assert response.status_code == 403
    assert "CSRF token validation failed" in response.json()["detail"]


@pytest.mark.unit
def test_csrf_token_set_on_get_request(monkeypatch):
    """CSRF token cookie should be set on GET requests."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    client = TestClient(app)

    response = client.get("/test")
    assert response.status_code == 200

    # Check CSRF cookie is set
    assert "csrf_token" in response.cookies
    assert len(response.cookies["csrf_token"]) > 0


@pytest.mark.unit
def test_csrf_validation_with_valid_token(monkeypatch):
    """POST request should succeed with valid CSRF token."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/get-token")
    async def get_token():
        return {"message": "token set"}

    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}

    client = TestClient(app)

    # First, get CSRF token
    response = client.get("/get-token")
    assert response.status_code == 200
    csrf_token = response.cookies["csrf_token"]

    # Now make POST with valid token
    response = client.post(
        "/test", cookies={"csrf_token": csrf_token}, headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "success"


@pytest.mark.unit
def test_csrf_validation_fails_without_header(monkeypatch):
    """POST request should fail without X-CSRF-Token header."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()

    @app.get("/get-token")
    async def get_token():
        return {"message": "token set"}

    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}

    app.add_middleware(CSRFMiddleware)

    client = TestClient(app, raise_server_exceptions=False)

    # Get CSRF token
    response = client.get("/get-token")
    csrf_token = response.cookies["csrf_token"]

    # POST with cookie but no header
    response = client.post("/test", cookies={"csrf_token": csrf_token})
    assert response.status_code == 403


@pytest.mark.unit
def test_csrf_validation_fails_with_mismatched_token(monkeypatch):
    """POST request should fail with mismatched CSRF tokens."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()

    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}

    app.add_middleware(CSRFMiddleware)

    client = TestClient(app, raise_server_exceptions=False)

    # POST with mismatched tokens
    response = client.post(
        "/test", cookies={"csrf_token": "cookie-token"}, headers={"X-CSRF-Token": "different-token"}
    )
    assert response.status_code == 403


@pytest.mark.unit
def test_csrf_exempt_health_endpoints(monkeypatch):
    """Health check endpoints should be exempt from CSRF protection."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/health")
    async def health_post():
        return {"status": "ok"}

    client = TestClient(app)

    # Health endpoint should work without CSRF token
    response = client.post("/health")
    assert response.status_code == 200


@pytest.mark.unit
def test_csrf_exempt_metrics_endpoints(monkeypatch):
    """Metrics endpoints should be exempt from CSRF protection."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/metrics")
    async def metrics():
        return {"metrics": "data"}

    client = TestClient(app)

    # Metrics endpoint should work without CSRF token
    response = client.get("/metrics")
    assert response.status_code == 200


@pytest.mark.unit
def test_csrf_exempt_bearer_token_auth(monkeypatch):
    """Requests with Bearer token authentication should be exempt from CSRF protection."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}

    client = TestClient(app)

    # POST with Bearer token should work without CSRF token
    response = client.post("/test", headers={"Authorization": "Bearer fake-jwt-token"})
    assert response.status_code == 200


@pytest.mark.unit
def test_csrf_protects_all_state_changing_methods(monkeypatch):
    """CSRF protection should apply to POST, PUT, PATCH, DELETE methods."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()

    @app.post("/test")
    async def test_post():
        return {"method": "post"}

    @app.put("/test")
    async def test_put():
        return {"method": "put"}

    @app.patch("/test")
    async def test_patch():
        return {"method": "patch"}

    @app.delete("/test")
    async def test_delete():
        return {"method": "delete"}

    @app.get("/test")
    async def test_get():
        return {"method": "get"}

    app.add_middleware(CSRFMiddleware)

    client = TestClient(app, raise_server_exceptions=False)

    # All state-changing methods should fail without CSRF token
    assert client.post("/test").status_code == 403
    assert client.put("/test").status_code == 403
    assert client.patch("/test").status_code == 403
    assert client.delete("/test").status_code == 403

    # GET should succeed (read-only operation)
    assert client.get("/test").status_code == 200


@pytest.mark.unit
def test_csrf_cookie_security_attributes(monkeypatch):
    """CSRF cookie should have appropriate security attributes."""
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

    import src.middleware.csrf
    from src.middleware.csrf import CSRFMiddleware

    monkeypatch.setattr(src.middleware.csrf, "settings", test_settings)

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    client = TestClient(app)

    response = client.get("/test")
    assert response.status_code == 200

    # Check cookie attributes in Set-Cookie header
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "csrf_token=" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "SameSite=Lax" in set_cookie_header
    assert "Path=/" in set_cookie_header
    assert "Max-Age=" in set_cookie_header

    # Secure flag should be present in production
    if test_settings.ENVIRONMENT == "production":
        assert "Secure" in set_cookie_header
