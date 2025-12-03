"""
Tests for InternalHeaderValidationMiddleware.

This middleware protects against authentication bypass attacks where external
clients could set X-Discord-* headers to impersonate users. It validates that
these headers only come from trusted internal services using a shared secret.

Security requirements (task-686):
1. Only accept Discord headers from trusted internal sources
2. Add shared secret validation for internal service calls
3. Strip client-provided X-Discord-* headers from untrusted sources
4. Verify external header spoofing is blocked
"""

import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-jwt-secret-key-for-testing-only-32-chars-min"
TEST_CREDENTIALS_ENCRYPTION_KEY = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="
TEST_INTERNAL_SERVICE_SECRET = "test-internal-service-secret-must-be-32-chars-min"


@pytest.mark.unit
def test_external_request_without_auth_strips_discord_headers(monkeypatch):
    """External requests without X-Internal-Auth should have Discord headers stripped."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "discord_user_id": request.headers.get("X-Discord-User-Id"),
            "discord_username": request.headers.get("X-Discord-Username"),
            "discord_has_manage_server": request.headers.get("X-Discord-Has-Manage-Server"),
            "guild_id": request.headers.get("X-Guild-Id"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Discord-Username": "attacker",
            "X-Discord-Has-Manage-Server": "true",
            "X-Guild-Id": "67890",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_user_id"] is None
    assert data["discord_username"] is None
    assert data["discord_has_manage_server"] is None
    assert data["guild_id"] is None


@pytest.mark.unit
def test_external_request_with_wrong_auth_strips_discord_headers(monkeypatch):
    """External requests with wrong X-Internal-Auth should have Discord headers stripped."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "discord_user_id": request.headers.get("X-Discord-User-Id"),
            "discord_username": request.headers.get("X-Discord-Username"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Discord-Username": "attacker",
            "X-Internal-Auth": "wrong-secret",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_user_id"] is None
    assert data["discord_username"] is None


@pytest.mark.unit
def test_internal_request_with_valid_auth_preserves_discord_headers(monkeypatch):
    """Internal requests with valid X-Internal-Auth should preserve Discord headers."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "discord_user_id": request.headers.get("X-Discord-User-Id"),
            "discord_username": request.headers.get("X-Discord-Username"),
            "discord_has_manage_server": request.headers.get("X-Discord-Has-Manage-Server"),
            "guild_id": request.headers.get("X-Guild-Id"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Discord-Username": "legitimate_user",
            "X-Discord-Has-Manage-Server": "true",
            "X-Guild-Id": "67890",
            "X-Internal-Auth": TEST_INTERNAL_SERVICE_SECRET,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_user_id"] == "12345"
    assert data["discord_username"] == "legitimate_user"
    assert data["discord_has_manage_server"] == "true"
    assert data["guild_id"] == "67890"


@pytest.mark.unit
def test_non_discord_headers_pass_through_without_auth(monkeypatch):
    """Non-Discord headers should pass through even without authentication."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "authorization": request.headers.get("Authorization"),
            "content_type": request.headers.get("Content-Type"),
            "x_custom_header": request.headers.get("X-Custom-Header"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
            "X-Custom-Header": "custom-value",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["authorization"] == "Bearer token123"
    assert data["content_type"] == "application/json"
    assert data["x_custom_header"] == "custom-value"


@pytest.mark.unit
def test_timing_attack_resistance_uses_constant_time_comparison(monkeypatch):
    """Verify that secret comparison uses constant-time algorithm.

    This test verifies the implementation calls secrets.compare_digest
    rather than == for comparing the secret, preventing timing attacks.
    """
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {"discord_user_id": request.headers.get("X-Discord-User-Id")}

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    compare_digest_called = False
    original_compare_digest = None

    import secrets

    original_compare_digest = secrets.compare_digest

    def tracked_compare_digest(a, b):
        nonlocal compare_digest_called
        compare_digest_called = True
        return original_compare_digest(a, b)

    monkeypatch.setattr(secrets, "compare_digest", tracked_compare_digest)
    monkeypatch.setattr(
        src.middleware.internal_auth.secrets, "compare_digest", tracked_compare_digest
    )

    client = TestClient(app)
    client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Internal-Auth": "some-secret",
        },
    )

    assert compare_digest_called, (
        "secrets.compare_digest should be used for constant-time comparison"
    )


@pytest.mark.unit
def test_all_discord_header_variants_are_stripped(monkeypatch):
    """All X-Discord-* header variants should be stripped from untrusted requests."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        discord_headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower().startswith("x-discord-") or key.lower() == "x-guild-id"
        }
        return {"discord_headers": discord_headers}

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Discord-Username": "attacker",
            "X-Discord-Display-Name": "Attacker Display Name",
            "X-Discord-Avatar-Url": "https://evil.com/avatar.png",
            "X-Discord-Has-Manage-Server": "true",
            "X-Discord-Unknown-Header": "should-be-stripped",
            "X-Guild-Id": "67890",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_headers"] == {}


@pytest.mark.unit
def test_health_endpoints_are_not_affected(monkeypatch):
    """Health endpoints should work regardless of header validation."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/health")
    async def health_endpoint():
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics_endpoint():
        return {"metrics": "data"}

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200

    response = client.get("/metrics")
    assert response.status_code == 200


@pytest.mark.unit
def test_case_insensitive_header_matching(monkeypatch):
    """Header matching should be case-insensitive per HTTP spec."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "discord_user_id": request.headers.get("X-Discord-User-Id"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)

    response = client.get(
        "/test",
        headers={
            "x-discord-user-id": "12345",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_user_id"] is None


@pytest.mark.unit
def test_middleware_without_internal_secret_configured_strips_all(monkeypatch):
    """When INTERNAL_SERVICE_SECRET is not set, all Discord headers should be stripped."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET="",
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "discord_user_id": request.headers.get("X-Discord-User-Id"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Internal-Auth": "any-secret",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_user_id"] is None


@pytest.mark.unit
def test_x_internal_auth_header_is_stripped(monkeypatch):
    """X-Internal-Auth header should be stripped after validation (don't leak to app)."""
    from src import config

    test_settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=TEST_JWT_SECRET_KEY,
        CREDENTIALS_ENCRYPTION_KEY=TEST_CREDENTIALS_ENCRYPTION_KEY,
        ENCRYPTION_MASTER_KEY=TEST_ENCRYPTION_MASTER_KEY,
        INTERNAL_SERVICE_SECRET=TEST_INTERNAL_SERVICE_SECRET,
    )
    monkeypatch.setattr(config, "settings", test_settings)

    from src.middleware.internal_auth import InternalHeaderValidationMiddleware

    app = FastAPI()
    app.add_middleware(InternalHeaderValidationMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "internal_auth": request.headers.get("X-Internal-Auth"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Internal-Auth": TEST_INTERNAL_SERVICE_SECRET,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["internal_auth"] is None
