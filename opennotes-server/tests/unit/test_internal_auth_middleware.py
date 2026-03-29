import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-jwt-secret-key-for-testing-only-32-chars-min"
TEST_CREDENTIALS_ENCRYPTION_KEY = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="
TEST_INTERNAL_SERVICE_SECRET = "test-internal-service-secret-must-be-32-chars-min"


@pytest.mark.unit
def test_external_request_without_auth_strips_platform_headers(monkeypatch):
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
            "platform_type": request.headers.get("X-Platform-Type"),
            "platform_user_id": request.headers.get("X-Platform-User-Id"),
            "platform_scope": request.headers.get("X-Platform-Scope"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Platform-Type": "discord",
            "X-Platform-User-Id": "12345",
            "X-Platform-Scope": "*",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_type"] is None
    assert data["platform_user_id"] is None
    assert data["platform_scope"] is None


@pytest.mark.unit
def test_external_request_with_wrong_auth_strips_platform_headers(monkeypatch):
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
            "platform_type": request.headers.get("X-Platform-Type"),
            "platform_user_id": request.headers.get("X-Platform-User-Id"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Platform-Type": "discord",
            "X-Platform-User-Id": "12345",
            "X-Internal-Auth": "wrong-secret",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_type"] is None
    assert data["platform_user_id"] is None


@pytest.mark.unit
def test_internal_request_with_valid_auth_preserves_platform_headers(monkeypatch):
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
            "platform_type": request.headers.get("X-Platform-Type"),
            "platform_user_id": request.headers.get("X-Platform-User-Id"),
            "platform_scope": request.headers.get("X-Platform-Scope"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Platform-Type": "discord",
            "X-Platform-User-Id": "12345",
            "X-Platform-Scope": "*",
            "X-Internal-Auth": TEST_INTERNAL_SERVICE_SECRET,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_type"] == "discord"
    assert data["platform_user_id"] == "12345"
    assert data["platform_scope"] == "*"


@pytest.mark.unit
def test_non_platform_headers_pass_through_without_auth(monkeypatch):
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
        return {"platform_type": request.headers.get("X-Platform-Type")}

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    compare_digest_called = False

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
            "X-Platform-Type": "discord",
            "X-Internal-Auth": "some-secret",
        },
    )

    assert compare_digest_called, (
        "secrets.compare_digest should be used for constant-time comparison"
    )


@pytest.mark.unit
def test_all_platform_header_variants_are_stripped(monkeypatch):
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
        platform_headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower().startswith("x-platform-")
        }
        return {"platform_headers": platform_headers}

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Platform-Type": "discord",
            "X-Platform-User-Id": "12345",
            "X-Platform-Username": "attacker",
            "X-Platform-Scope": "*",
            "X-Platform-Unknown-Header": "should-be-stripped",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_headers"] == {}


@pytest.mark.unit
def test_platform_claims_header_is_allowed_through(monkeypatch):
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
            "platform_claims": request.headers.get("X-Platform-Claims"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Platform-Claims": "some.jwt.token",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_claims"] == "some.jwt.token"


@pytest.mark.unit
def test_old_discord_headers_no_longer_protected(monkeypatch):
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
            "guild_id": request.headers.get("X-Guild-Id"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Discord-User-Id": "12345",
            "X-Guild-Id": "67890",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["discord_user_id"] == "12345"
    assert data["guild_id"] == "67890"


@pytest.mark.unit
def test_health_endpoints_are_not_affected(monkeypatch):
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
            "platform_type": request.headers.get("X-Platform-Type"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)

    response = client.get(
        "/test",
        headers={
            "x-platform-type": "discord",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_type"] is None


@pytest.mark.unit
def test_middleware_without_internal_secret_configured_strips_all(monkeypatch):
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
            "platform_type": request.headers.get("X-Platform-Type"),
        }

    import src.middleware.internal_auth

    monkeypatch.setattr(src.middleware.internal_auth, "settings", test_settings)

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={
            "X-Platform-Type": "discord",
            "X-Internal-Auth": "any-secret",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform_type"] is None


@pytest.mark.unit
def test_x_internal_auth_header_is_stripped(monkeypatch):
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
            "X-Platform-Type": "discord",
            "X-Internal-Auth": TEST_INTERNAL_SERVICE_SECRET,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["internal_auth"] is None


@pytest.mark.unit
class TestHeaderProtection:
    def test_platform_headers_are_protected(self) -> None:
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"x-platform-type") is True
        assert _is_protected_header(b"X-Platform-Type") is True
        assert _is_protected_header(b"x-platform-user-id") is True
        assert _is_protected_header(b"x-platform-scope") is True

    def test_platform_claims_header_is_allowed(self) -> None:
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"x-platform-claims") is False
        assert _is_protected_header(b"X-Platform-Claims") is False

    def test_regular_headers_are_not_protected(self) -> None:
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"content-type") is False
        assert _is_protected_header(b"authorization") is False
        assert _is_protected_header(b"x-request-id") is False

    def test_old_discord_headers_are_not_protected(self) -> None:
        from src.middleware.internal_auth import _is_protected_header

        assert _is_protected_header(b"x-discord-user-id") is False
        assert _is_protected_header(b"x-discord-has-manage-server") is False
        assert _is_protected_header(b"x-guild-id") is False
