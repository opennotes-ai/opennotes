from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from starlette.testclient import TestClient

pytestmark = pytest.mark.unit


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/v1/profile/auth/register/email")
    async def register_email(
        email: Annotated[str, Query(min_length=1)],
        password: Annotated[str, Query(min_length=1)],
        display_name: Annotated[str, Query(min_length=1, max_length=255)],
    ) -> dict:
        return {"ok": True}

    @app.post("/api/v1/profile/auth/verify-email")
    async def verify_email(
        token: Annotated[str, Query(min_length=1)],
    ) -> dict:
        return {"ok": True}

    @app.post("/api/v1/profile/auth/resend-verification")
    async def resend_verification_email(
        email: Annotated[str, Query(min_length=1)],
    ) -> dict:
        return {"ok": True}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


class TestRegisterEmailQueryValidation:
    def test_empty_display_name_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/profile/auth/register/email"
            "?email=test@test.com&password=secret123&display_name="
        )
        assert response.status_code == 422

    def test_empty_email_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/profile/auth/register/email?email=&password=secret123&display_name=testuser"
        )
        assert response.status_code == 422

    def test_empty_password_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/profile/auth/register/email"
            "?email=test@test.com&password=&display_name=testuser"
        )
        assert response.status_code == 422

    def test_missing_display_name_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/profile/auth/register/email?email=test@test.com&password=secret123"
        )
        assert response.status_code == 422

    def test_display_name_exceeds_max_length_returns_422(self, client: TestClient):
        long_name = "a" * 256
        response = client.post(
            f"/api/v1/profile/auth/register/email"
            f"?email=test@test.com&password=secret123&display_name={long_name}"
        )
        assert response.status_code == 422

    def test_valid_params_returns_200(self, client: TestClient):
        response = client.post(
            "/api/v1/profile/auth/register/email"
            "?email=test@test.com&password=secret123&display_name=testuser"
        )
        assert response.status_code == 200


class TestVerifyEmailQueryValidation:
    def test_empty_token_returns_422(self, client: TestClient):
        response = client.post("/api/v1/profile/auth/verify-email?token=")
        assert response.status_code == 422

    def test_missing_token_returns_422(self, client: TestClient):
        response = client.post("/api/v1/profile/auth/verify-email")
        assert response.status_code == 422

    def test_valid_token_returns_200(self, client: TestClient):
        response = client.post("/api/v1/profile/auth/verify-email?token=abc123")
        assert response.status_code == 200


class TestResendVerificationQueryValidation:
    def test_empty_email_returns_422(self, client: TestClient):
        response = client.post("/api/v1/profile/auth/resend-verification?email=")
        assert response.status_code == 422

    def test_missing_email_returns_422(self, client: TestClient):
        response = client.post("/api/v1/profile/auth/resend-verification")
        assert response.status_code == 422

    def test_valid_email_returns_200(self, client: TestClient):
        response = client.post("/api/v1/profile/auth/resend-verification?email=test@test.com")
        assert response.status_code == 200
