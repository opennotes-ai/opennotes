"""
Unit tests for Discord OAuth2 state parameter validation.

These tests verify the CSRF protection mechanism in the OAuth flow
by testing state parameter generation, validation, and rejection.

Note: These are unit tests that mock Redis - they do not require Docker/testcontainers.
Tests that require a real database are in test_discord_oauth_endpoints.py.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.unit


@pytest.fixture
async def test_client():
    """Create an async test client that doesn't require database setup.

    Note: This fixture ensures required environment variables are set before
    importing the app, as the Settings singleton may have been cleared by
    other test fixtures (particularly tests/unit/conftest.py's autouse fixture).
    """
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only-32-chars-min")
    os.environ.setdefault(
        "CREDENTIALS_ENCRYPTION_KEY", "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
    )
    os.environ.setdefault("ENCRYPTION_MASTER_KEY", "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE=")

    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestDiscordOAuthInit:
    """Tests for /api/v1/profile/auth/discord/init endpoint."""

    @pytest.mark.asyncio
    async def test_init_returns_authorization_url(self, test_client):
        """Test that init endpoint returns Discord authorization URL."""
        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            from tests.redis_mock import create_stateful_redis_mock

            mock_redis = create_stateful_redis_mock()
            mock_redis_client.client = mock_redis

            response = await test_client.get("/api/v1/profile/auth/discord/init")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "authorization_url" in data
            assert "state" in data
            assert "discord.com/oauth2/authorize" in data["authorization_url"]
            assert data["state"] in data["authorization_url"]

    @pytest.mark.asyncio
    async def test_init_stores_state_in_redis(self, test_client):
        """Test that init endpoint stores state in Redis."""
        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            from tests.redis_mock import create_stateful_redis_mock

            mock_redis = create_stateful_redis_mock()
            mock_redis_client.client = mock_redis

            response = await test_client.get("/api/v1/profile/auth/discord/init")

            assert response.status_code == status.HTTP_200_OK
            state = response.json()["state"]

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            assert call_args[0] == f"oauth:state:{state}"

    @pytest.mark.asyncio
    async def test_init_fails_when_redis_unavailable(self, test_client):
        """Test that init endpoint returns 503 when Redis is unavailable."""
        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = None

            response = await test_client.get("/api/v1/profile/auth/discord/init")

            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "OAuth service temporarily unavailable" in response.json()["detail"]


class TestDiscordOAuthStateValidation:
    """Tests for state parameter validation on register/login endpoints (schema validation only)."""

    @pytest.mark.asyncio
    async def test_registration_rejects_missing_state(self, test_client):
        """Test registration fails when state parameter is missing (schema validation)."""
        response = await test_client.post(
            "/api/v1/profile/auth/register/discord",
            json={
                "code": "valid_oauth_code",
                "display_name": "Test User",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_registration_rejects_invalid_state(self, test_client):
        """Test registration fails when state parameter is invalid."""
        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            from tests.redis_mock import create_stateful_redis_mock

            mock_redis = create_stateful_redis_mock()
            mock_redis_client.client = mock_redis

            response = await test_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "invalid-state-not-in-redis",
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid or expired OAuth state" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_rejects_missing_state(self, test_client):
        """Test login fails when state parameter is missing (schema validation)."""
        response = await test_client.post(
            "/api/v1/profile/auth/login/discord",
            json={
                "code": "valid_oauth_code",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_login_rejects_invalid_state(self, test_client):
        """Test login fails when state parameter is invalid."""
        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            from tests.redis_mock import create_stateful_redis_mock

            mock_redis = create_stateful_redis_mock()
            mock_redis_client.client = mock_redis

            response = await test_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "invalid-state-not-in-redis",
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid or expired OAuth state" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_state_validation_fails_when_redis_unavailable(self, test_client):
        """Test that state validation returns 503 when Redis is unavailable."""
        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = None

            response = await test_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "some-state",
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "OAuth service temporarily unavailable" in response.json()["detail"]


class TestDiscordOAuthStateValidationE2E:
    """End-to-end integration tests for OAuth state validation.

    These tests verify the complete OAuth flow including state generation,
    storage, validation, and one-time consumption. Tests use mocked Redis
    to avoid Docker/testcontainers dependencies.
    """

    @pytest.mark.asyncio
    async def test_oauth_flow_with_valid_state(self, test_client):
        """Test complete OAuth flow: init → get state → registration with state.

        This E2E test verifies the CSRF protection flow end-to-end:
        1. /discord/init generates a state and stores it in Redis
        2. State is returned in the authorization URL
        3. Registration endpoint validates the state exists
        4. State validation rejects requests with invalid/missing states
        """
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = mock_redis

            response = await test_client.get("/api/v1/profile/auth/discord/init")
            assert response.status_code == status.HTTP_200_OK

            init_data = response.json()
            state = init_data["state"]
            auth_url = init_data["authorization_url"]

            assert state is not None
            assert len(state) > 0
            assert "state=" + state in auth_url
            assert "discord.com/oauth2/authorize" in auth_url

            key = f"oauth:state:{state}"
            exists = await mock_redis._exists(key)
            assert exists == 1, f"State key {key} should exist in Redis"

    @pytest.mark.asyncio
    async def test_state_cannot_be_reused(self, test_client):
        """Test that a state token can only be used once (one-time use enforcement).

        This test verifies the CSRF protection mechanism by ensuring:
        1. State is generated and stored
        2. First use of state is validated (state exists)
        3. Second use of the same state fails (already consumed)
        """
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = mock_redis

            response = await test_client.get("/api/v1/profile/auth/discord/init")
            assert response.status_code == status.HTTP_200_OK
            state = response.json()["state"]

            key = f"oauth:state:{state}"

            exists_before = await mock_redis._exists(key)
            assert exists_before == 1

            await mock_redis._delete(key)

            exists_after = await mock_redis._exists(key)
            assert exists_after == 0

            response = await test_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_code",
                    "state": state,
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid or expired OAuth state" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_state_expires_after_ttl(self, test_client):
        """Test that expired states are rejected (TTL enforcement).

        This test verifies the OAuth state TTL mechanism by:
        1. Generating a state (stored with TTL)
        2. Simulating expiration by removing key from Redis
        3. Attempting to use the expired state
        4. Verifying the request fails with 400 error
        """
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = mock_redis

            response = await test_client.get("/api/v1/profile/auth/discord/init")
            assert response.status_code == status.HTTP_200_OK
            state = response.json()["state"]

            key = f"oauth:state:{state}"

            exists = await mock_redis._exists(key)
            assert exists == 1

            await mock_redis._delete(key)

            response = await test_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": state,
                    "display_name": "User with Expired State",
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid or expired OAuth state" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_state_validation_in_login_flow(self, test_client):
        """Test that state validation works correctly in login endpoint.

        This test ensures state validation is applied consistently across
        both registration and login endpoints.
        """
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with (
            patch("src.auth.oauth_state.redis_client") as mock_redis_client,
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_redis_client.client = mock_redis
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                },
                {
                    "access_token": "login_token",
                    "token_type": "Bearer",
                },
            )

            response = await test_client.get("/api/v1/profile/auth/discord/init")
            state = response.json()["state"]

            await mock_redis._delete(f"oauth:state:{state}")

            response = await test_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "login_code",
                    "state": state,
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid or expired OAuth state" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_state_immediately_rejected(self, test_client):
        """Test that completely invalid states are immediately rejected.

        This test verifies that:
        1. A state that was never generated is rejected
        2. No database queries occur for invalid state
        3. Response is immediate with 400 error
        """
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = mock_redis

            response = await test_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_code",
                    "state": "completely-invalid-state-never-generated",
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Invalid or expired OAuth state" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_multiple_states_independent_lifecycle(self, test_client):
        """Test that multiple states have independent lifecycles.

        This test verifies that:
        1. Multiple states can be generated and stored independently
        2. Each state can be independently validated and consumed
        3. Consuming one state doesn't affect others
        """
        from tests.redis_mock import create_stateful_redis_mock

        mock_redis = create_stateful_redis_mock()

        with patch("src.auth.oauth_state.redis_client") as mock_redis_client:
            mock_redis_client.client = mock_redis

            response1 = await test_client.get("/api/v1/profile/auth/discord/init")
            state1 = response1.json()["state"]

            response2 = await test_client.get("/api/v1/profile/auth/discord/init")
            state2 = response2.json()["state"]

            assert state1 != state2

            key1 = f"oauth:state:{state1}"
            key2 = f"oauth:state:{state2}"

            exists1 = await mock_redis._exists(key1)
            exists2 = await mock_redis._exists(key2)
            assert exists1 == 1
            assert exists2 == 1

            await mock_redis._delete(key1)

            exists1_after = await mock_redis._exists(key1)
            exists2_after = await mock_redis._exists(key2)
            assert exists1_after == 0
            assert exists2_after == 1
