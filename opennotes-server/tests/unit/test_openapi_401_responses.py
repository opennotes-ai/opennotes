from src.main import app


def test_authenticated_endpoints_document_401():
    schema = app.openapi()
    paths = schema["paths"]

    auth_endpoints = [
        ("/api/v2/notes", "get"),
        ("/api/v2/notes", "post"),
        ("/api/v2/profiles/me", "get"),
        ("/api/v1/batch-jobs", "get"),
        ("/api/v1/config/rating-thresholds", "get"),
        ("/api/v2/ratings", "post"),
        ("/api/v2/scoring/status", "get"),
        ("/api/v2/stats/notes", "get"),
        ("/api/v1/auth/logout", "post"),
        ("/api/v1/profile/me", "get"),
        ("/api/v2/user-profiles/lookup", "get"),
        ("/api/v1/admin/fusion-weights", "get"),
    ]
    for path, method in auth_endpoints:
        assert path in paths, f"Path {path} not found in OpenAPI schema"
        assert method in paths[path], f"{method.upper()} {path} not found in OpenAPI schema"
        responses = paths[path][method]["responses"]
        assert "401" in responses, f"{method.upper()} {path} missing 401 response"


def test_unauthenticated_endpoints_do_not_document_401():
    schema = app.openapi()
    paths = schema["paths"]

    unauth_endpoints = [
        ("/api/v1/auth/register", "post"),
        ("/api/v1/auth/login", "post"),
        ("/api/v1/auth/refresh", "post"),
        ("/api/v1/profile/auth/register/discord", "post"),
        ("/api/v1/profile/auth/login/discord", "post"),
        ("/api/v1/profile/auth/login/email", "post"),
    ]
    for path, method in unauth_endpoints:
        assert path in paths, f"Path {path} not found in OpenAPI schema"
        assert method in paths[path], f"{method.upper()} {path} not found in OpenAPI schema"
        responses = paths[path][method]["responses"]
        assert "401" not in responses, f"{method.upper()} {path} should NOT have 401 response"
