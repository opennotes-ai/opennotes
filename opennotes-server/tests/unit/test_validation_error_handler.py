import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from src.middleware.validation_error_handler import (
    SENSITIVE_KEYS,
    _sanitize_loc,
    sanitized_validation_exception_handler,
)


def _build_app() -> FastAPI:
    app = FastAPI()

    class RegisterBody(BaseModel):
        username: str = Field(..., min_length=3)
        email: str
        password: str = Field(..., min_length=8)

    class TokenBody(BaseModel):
        refresh_token: str
        api_key: str

    @app.post("/register")
    async def register(body: RegisterBody) -> dict:
        return {"ok": True}

    @app.post("/token")
    async def token(body: TokenBody) -> dict:
        return {"ok": True}

    app.add_exception_handler(RequestValidationError, sanitized_validation_exception_handler)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


@pytest.mark.unit
class TestSanitizedValidationErrors:
    def test_sensitive_field_redacted_in_loc(self, client: TestClient):
        response = client.post("/register", json={})
        assert response.status_code == 422
        body = response.json()
        all_locs = [tuple(e["loc"]) for e in body["detail"]]
        for loc in all_locs:
            for part in loc:
                assert part != "password", "password field name must be redacted"

    def test_non_sensitive_fields_visible_in_loc(self, client: TestClient):
        response = client.post("/register", json={})
        assert response.status_code == 422
        body = response.json()
        flat_parts = [part for e in body["detail"] for part in e["loc"]]
        assert "username" in flat_parts or "email" in flat_parts

    def test_no_input_key_in_error_details(self, client: TestClient):
        response = client.post("/register", json={"password": "short"})
        assert response.status_code == 422
        body = response.json()
        for error in body["detail"]:
            assert "input" not in error, "input field must be excluded to prevent value leakage"

    def test_replacement_string_used(self, client: TestClient):
        response = client.post("/register", json={})
        assert response.status_code == 422
        body = response.json()
        flat_parts = [part for e in body["detail"] for part in e["loc"]]
        assert "********" in flat_parts

    def test_multiple_sensitive_fields_redacted(self, client: TestClient):
        response = client.post("/token", json={})
        assert response.status_code == 422
        body = response.json()
        flat_parts = [part for e in body["detail"] for part in e["loc"]]
        assert "refresh_token" not in flat_parts
        assert "api_key" not in flat_parts

    def test_error_structure_has_type_loc_msg(self, client: TestClient):
        response = client.post("/register", json={})
        assert response.status_code == 422
        body = response.json()
        for error in body["detail"]:
            assert "type" in error
            assert "loc" in error
            assert "msg" in error

    def test_valid_request_passes_through(self, client: TestClient):
        response = client.post(
            "/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 200


@pytest.mark.unit
class TestSanitizeLoc:
    def test_redacts_sensitive_key(self):
        assert _sanitize_loc(["body", "password"]) == ["body", "********"]

    def test_preserves_non_sensitive_key(self):
        assert _sanitize_loc(["body", "username"]) == ["body", "username"]

    def test_preserves_integer_indices(self):
        assert _sanitize_loc(["body", 0, "password"]) == ["body", 0, "********"]

    def test_case_insensitive(self):
        assert _sanitize_loc(["body", "Password"]) == ["body", "********"]
        assert _sanitize_loc(["body", "API_KEY"]) == ["body", "********"]

    def test_empty_loc(self):
        assert _sanitize_loc([]) == []

    def test_nested_sensitive_path(self):
        assert _sanitize_loc(["body", "nested", "hashed_password"]) == [
            "body",
            "nested",
            "********",
        ]

    def test_all_sensitive_keys_covered(self):
        for key in SENSITIVE_KEYS:
            result = _sanitize_loc(["body", key])
            assert result == ["body", "********"], f"{key} was not redacted"
