"""
Integration tests for profile-based authentication endpoints.

Tests authentication flows in profile_router.py including:
- Discord registration and login
- Email/password registration and login
- JWT token generation and validation
- Profile retrieval and updates via profile auth

Note: Profile GET/PATCH operations use v2 JSON:API endpoints (/api/v2/profiles/me)
while authentication endpoints remain on v1 (no v2 equivalent exists).
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.profile_auth import verify_profile_token

# Import CommunityServer to ensure it's registered before profile_models relationships are resolved
from src.llm_config.models import CommunityServer  # noqa: F401
from src.main import app
from src.users.profile_schemas import AuthProvider
from tests.conftest import create_valid_oauth_state, verify_email_for_testing


def extract_profile_attributes(response_json: dict[str, Any]) -> dict[str, Any]:
    """Extract profile attributes from JSON:API response format."""
    return response_json["data"]["attributes"]


def extract_profile_id(response_json: dict[str, Any]) -> str:
    """Extract profile ID from JSON:API response format."""
    return response_json["data"]["id"]


def build_profile_patch_request(profile_id: str, **attributes: Any) -> dict[str, Any]:
    """Build a JSON:API PATCH request body for profile updates."""
    return {
        "data": {
            "type": "profiles",
            "id": profile_id,
            "attributes": attributes,
        }
    }


pytestmark = pytest.mark.asyncio


# Mock Discord OAuth verification for tests
def mock_verify_discord_user(code: str, **kwargs):
    """
    Mock Discord OAuth verification based on the authorization code.

    The code is used to determine which test user to return.
    Format: "test_<discord_id>_<username>"

    Special markers in code:
    - "no_avatar" in code: Returns user with avatar=None
    - Otherwise: Returns avatar="abc123"
    """
    # Extract discord_id from the code (format: test_<discord_id>_<username>)
    parts = code.split("_")
    if len(parts) >= 3:
        discord_id = parts[1]
        username = "_".join(parts[2:])
    else:
        discord_id = "123456789"
        username = "testuser"

    # Return None for avatar if "no_avatar" marker is in code
    avatar = None if "no_avatar" in code else "abc123"

    user_data = {
        "id": discord_id,
        "username": username,
        "discriminator": "0",
        "avatar": avatar,
    }

    token_data = {
        "access_token": f"mock_discord_token_{discord_id}",
        "token_type": "Bearer",
        "refresh_token": f"mock_refresh_token_{discord_id}",
        "expires_in": 604800,
        "scope": "identify",
    }

    return user_data, token_data


# ============================================================================
# Discord Authentication Tests
# ============================================================================


class TestDiscordRegistration:
    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_register_discord_new_user_success(self, mock_verify):
        """Test successful Discord user registration"""
        mock_verify.return_value = mock_verify_discord_user("test_new_discord_123_discord_user")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            state = await create_valid_oauth_state()
            response = await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_new_discord_123_discord_user",
                    "state": state,
                    "display_name": "discord_user",
                    "avatar_url": "https://cdn.discord.com/avatar.png",
                },
            )

            assert response.status_code == 201
            data = response.json()

            assert data["display_name"] == "discord_user"
            assert data["avatar_url"] == "https://cdn.discord.com/avatar.png"
            assert data["is_human"] is True
            assert "id" in data
            assert "created_at" in data

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_register_discord_duplicate_account(self, mock_verify):
        """Test that registering duplicate Discord account fails"""
        mock_verify.return_value = mock_verify_discord_user("test_duplicate_discord_456_first_user")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First registration
            state1 = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_duplicate_discord_456_first_user",
                    "state": state1,
                    "display_name": "first_user",
                },
            )

            # Attempt duplicate registration (same discord_id)
            state2 = await create_valid_oauth_state()
            response = await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_duplicate_discord_456_first_user",
                    "state": state2,
                    "display_name": "second_user",
                },
            )

            assert response.status_code == 400
            assert "already registered" in response.json()["detail"].lower()

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_register_discord_without_avatar(self, mock_verify):
        """Test Discord registration without avatar URL"""
        mock_verify.return_value = mock_verify_discord_user("test_no_avatar_789_minimal_user")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            state = await create_valid_oauth_state()
            response = await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_no_avatar_789_minimal_user",
                    "state": state,
                    "display_name": "minimal_user",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["display_name"] == "minimal_user"
            assert data["avatar_url"] is None


class TestDiscordLogin:
    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_login_discord_success(self, mock_verify):
        """Test successful Discord login"""
        mock_verify.return_value = mock_verify_discord_user(
            "test_login_discord_999_discord_login_user"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First register a user
            state1 = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_login_discord_999_discord_login_user",
                    "state": state1,
                    "display_name": "discord_login_user",
                },
            )

            # Login
            state2 = await create_valid_oauth_state()
            response = await client.post(
                "/api/v1/profile/auth/login/discord",
                json={"code": "test_login_discord_999_discord_login_user", "state": state2},
            )

            assert response.status_code == 200
            data = response.json()

            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"
            assert "expires_in" in data

            # Verify token contains correct claims
            token_data = await verify_profile_token(data["access_token"])
            assert token_data is not None
            assert token_data.display_name == "discord_login_user"
            assert token_data.provider == AuthProvider.DISCORD.value

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_login_discord_nonexistent_account(self, mock_verify):
        """Test login with non-existent Discord account fails"""
        mock_verify.return_value = mock_verify_discord_user(
            "test_nonexistent_discord_123_nonexistent"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            state = await create_valid_oauth_state()
            response = await client.post(
                "/api/v1/profile/auth/login/discord",
                json={"code": "test_nonexistent_discord_123_nonexistent", "state": state},
            )

            assert response.status_code == 401
            assert "not found" in response.json()["detail"].lower()

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_login_discord_token_validity(self, mock_verify):
        """Test that generated Discord token can be used for authenticated requests"""
        mock_verify.return_value = mock_verify_discord_user(
            "test_token_discord_111_token_test_user"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register user
            state1 = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_token_discord_111_token_test_user",
                    "state": state1,
                    "display_name": "token_test_user",
                },
            )

            # Login
            state2 = await create_valid_oauth_state()
            login_response = await client.post(
                "/api/v1/profile/auth/login/discord",
                json={"code": "test_token_discord_111_token_test_user", "state": state2},
            )
            token = login_response.json()["access_token"]

            # Use token to access protected endpoint (v2 JSON:API)
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert profile_response.status_code == 200
            attrs = extract_profile_attributes(profile_response.json())
            assert attrs["display_name"] == "token_test_user"


# ============================================================================
# Email Authentication Tests
# ============================================================================


class TestEmailRegistration:
    async def test_register_email_new_user_success(self):
        """Test successful email/password user registration"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "newuser@example.com",
                    "password": "secure_password_123",
                    "display_name": "email_user",
                },
            )

            assert response.status_code == 201
            data = response.json()

            assert data["display_name"] == "email_user"
            assert data["is_human"] is True
            assert "id" in data
            assert "created_at" in data

    async def test_register_email_duplicate_email(self):
        """Test that registering duplicate email fails"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First registration
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "duplicate@example.com",
                    "password": "TestPassword123!",
                    "display_name": "first_email_user",
                },
            )

            # Attempt duplicate registration
            response = await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "duplicate@example.com",
                    "password": "different_password",
                    "display_name": "second_email_user",
                },
            )

            assert response.status_code == 400
            assert "already registered" in response.json()["detail"].lower()

    async def test_register_email_duplicate_display_name(self):
        """Test that registering duplicate display name fails"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First registration
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "user1@example.com",
                    "password": "TestPassword123!",
                    "display_name": "taken_name",
                },
            )

            # Attempt with same display name
            response = await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "user2@example.com",
                    "password": "password456",
                    "display_name": "taken_name",
                },
            )

            assert response.status_code == 400
            assert "already taken" in response.json()["detail"].lower()


class TestEmailLogin:
    async def test_login_email_success(self):
        """Test successful email/password login"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "login@example.com",
                    "password": "my_password_123",
                    "display_name": "login_test_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("login@example.com")

            # Login using OAuth2PasswordRequestForm format
            response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "login@example.com",  # OAuth2 uses 'username' field
                    "password": "my_password_123",
                },
            )

            assert response.status_code == 200
            data = response.json()

            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"

            # Verify token
            token_data = await verify_profile_token(data["access_token"])
            assert token_data is not None
            assert token_data.display_name == "login_test_user"
            assert token_data.provider == AuthProvider.EMAIL.value

    async def test_login_email_wrong_password(self):
        """Test login with incorrect password fails"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "wrong_password@example.com",
                    "password": "correct_password",
                    "display_name": "password_test_user",
                },
            )

            # Attempt login with wrong password
            response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "wrong_password@example.com",
                    "password": "wrong_password",
                },
            )

            assert response.status_code == 401
            assert "incorrect" in response.json()["detail"].lower()

    async def test_login_email_nonexistent_account(self):
        """Test login with non-existent email fails"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "nonexistent@example.com",
                    "password": "any_password",
                },
            )

            assert response.status_code == 401
            assert "incorrect" in response.json()["detail"].lower()

    async def test_login_email_token_validity(self):
        """Test that generated email token can be used for authenticated requests"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "token_test@example.com",
                    "password": "token_password",
                    "display_name": "email_token_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("token_test@example.com")

            # Login
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "token_test@example.com",
                    "password": "token_password",
                },
            )
            token = login_response.json()["access_token"]

            # Use token (v2 JSON:API)
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert profile_response.status_code == 200
            attrs = extract_profile_attributes(profile_response.json())
            assert attrs["display_name"] == "email_token_user"


# ============================================================================
# Profile Endpoint Tests (via profile auth)
# ============================================================================


class TestGetCurrentProfile:
    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_get_current_profile_success(self, mock_verify):
        """Test getting current profile with valid token"""
        mock_verify.return_value = mock_verify_discord_user(
            "test_current_profile_discord_current_profile_user"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            state1 = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_current_profile_discord_current_profile_user",
                    "state": state1,
                    "display_name": "current_profile_user",
                    "avatar_url": "https://example.com/avatar.png",
                },
            )

            # Login
            state2 = await create_valid_oauth_state()
            login_response = await client.post(
                "/api/v1/profile/auth/login/discord",
                json={"code": "test_current_profile_discord_current_profile_user", "state": state2},
            )
            token = login_response.json()["access_token"]

            # Get profile (v2 JSON:API)
            response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200
            attrs = extract_profile_attributes(response.json())

            assert attrs["display_name"] == "current_profile_user"
            assert attrs["avatar_url"] == "https://example.com/avatar.png"

    async def test_get_current_profile_without_auth(self):
        """Test that unauthenticated request fails (v2 JSON:API)"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/profiles/me")

            assert response.status_code == 401


class TestUpdateCurrentProfile:
    async def test_update_current_profile_success(self):
        """Test updating current profile"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "update@example.com",
                    "password": "TestPassword123!",
                    "display_name": "update_test_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("update@example.com")

            # Login
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "update@example.com",
                    "password": "TestPassword123!",
                },
            )
            token = login_response.json()["access_token"]

            # First get the profile to obtain the ID for the JSON:API request
            get_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            profile_id = extract_profile_id(get_response.json())

            # Update profile (v2 JSON:API)
            response = await client.patch(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
                json=build_profile_patch_request(
                    profile_id,
                    display_name="updated_name",
                    bio="New bio text",
                ),
            )

            assert response.status_code == 200
            attrs = extract_profile_attributes(response.json())

            assert attrs["display_name"] == "updated_name"
            assert attrs["bio"] == "New bio text"

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_update_profile_duplicate_display_name(self, mock_verify):
        """Test that updating to an existing display name fails"""
        mock_verify.return_value = mock_verify_discord_user("test_discord_existing_existing_name")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create first profile
            state = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_discord_existing_existing_name",
                    "state": state,
                    "display_name": "existing_name",
                },
            )

            # Create second profile
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "another@example.com",
                    "password": "TestPassword123!",
                    "display_name": "another_name",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("another@example.com")

            # Login with second profile
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "another@example.com",
                    "password": "TestPassword123!",
                },
            )
            token = login_response.json()["access_token"]

            # First get the profile to obtain the ID for the JSON:API request
            get_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            profile_id = extract_profile_id(get_response.json())

            # Try to update to existing name (v2 JSON:API returns 409 Conflict)
            response = await client.patch(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
                json=build_profile_patch_request(profile_id, display_name="existing_name"),
            )

            assert response.status_code == 409
            errors = response.json().get("errors", [])
            assert len(errors) > 0
            assert "already" in errors[0].get("detail", "").lower()

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_update_profile_same_display_name(self, mock_verify):
        """Test that updating to same display name is allowed"""
        mock_verify.return_value = mock_verify_discord_user("test_same_name_discord_same_name_user")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            state1 = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_same_name_discord_same_name_user",
                    "state": state1,
                    "display_name": "same_name_user",
                },
            )

            # Login
            state2 = await create_valid_oauth_state()
            login_response = await client.post(
                "/api/v1/profile/auth/login/discord",
                json={"code": "test_same_name_discord_same_name_user", "state": state2},
            )
            token = login_response.json()["access_token"]

            # First get the profile to obtain the ID for the JSON:API request
            get_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            profile_id = extract_profile_id(get_response.json())

            # Update with same name (v2 JSON:API)
            response = await client.patch(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
                json=build_profile_patch_request(
                    profile_id, display_name="same_name_user"
                ),  # Same as current
            )

            assert response.status_code == 200

    async def test_update_profile_without_auth(self):
        """Test that unauthenticated update fails (v2 JSON:API)"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/api/v2/profiles/me",
                json=build_profile_patch_request("dummy-id", bio="Hacker bio"),
            )

            assert response.status_code == 401


# ============================================================================
# Token Validation Tests
# ============================================================================


class TestTokenValidation:
    async def test_malformed_token_rejected(self):
        """Test that malformed tokens are rejected (v2 JSON:API)"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": "Bearer invalid.token.here"},
            )

            assert response.status_code == 401

    async def test_missing_bearer_prefix(self):
        """Test that token without Bearer prefix is rejected (v2 JSON:API)"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": "some_token"},
            )

            assert response.status_code == 401


# ============================================================================
# Security Tests
# ============================================================================


class TestSecurityEdgeCases:
    async def test_password_hashing_verification(self):
        """Test that passwords are properly hashed and verified"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "hash_test@example.com",
                    "password": "plain_text_password",
                    "display_name": "hash_test_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("hash_test@example.com")

            # Verify we cannot login with wrong password
            wrong_password_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "hash_test@example.com",
                    "password": "wrong_password",
                },
            )
            assert wrong_password_response.status_code == 401

            # Verify correct password works
            correct_password_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "hash_test@example.com",
                    "password": "plain_text_password",
                },
            )
            assert correct_password_response.status_code == 200

    async def test_credentials_not_exposed_in_responses(self):
        """Test that credentials are never exposed in API responses"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register email user
            register_response = await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "exposure_test@example.com",
                    "password": "secret_password",
                    "display_name": "exposure_test_user",
                },
            )

            # Verify credentials not in registration response
            data = register_response.json()
            assert "credentials" not in data
            assert "hashed_password" not in data
            assert "password" not in data

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("exposure_test@example.com")

            # Login and check profile endpoint
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "exposure_test@example.com",
                    "password": "secret_password",
                },
            )
            token = login_response.json()["access_token"]

            # Get profile via v2 JSON:API endpoint
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Verify credentials not in profile response (check both root and attributes)
            profile_json = profile_response.json()
            profile_attrs = extract_profile_attributes(profile_json)
            assert "credentials" not in profile_json
            assert "credentials" not in profile_attrs
            assert "hashed_password" not in profile_attrs
            assert "password" not in profile_attrs


# ============================================================================
# Token Revocation Tests
# ============================================================================


class TestTokenRevocation:
    async def test_revoke_token_success(self):
        """Test successful token revocation returns 204"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "revoke_test@example.com",
                    "password": "revoke_password",
                    "display_name": "revoke_test_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("revoke_test@example.com")

            # Login
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "revoke_test@example.com",
                    "password": "revoke_password",
                },
            )
            token = login_response.json()["access_token"]

            # Verify token works before revocation (v2 JSON:API)
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert profile_response.status_code == 200

            # Revoke the token (remains on v1 - no v2 equivalent)
            revoke_response = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert revoke_response.status_code == 204

    async def test_revoked_token_cannot_be_used(self):
        """Test that revoked token cannot be used for authentication"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "revoke_usage_test@example.com",
                    "password": "revoke_password",
                    "display_name": "revoke_usage_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("revoke_usage_test@example.com")

            # Login
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "revoke_usage_test@example.com",
                    "password": "revoke_password",
                },
            )
            token = login_response.json()["access_token"]

            # Revoke the token (v1 - no v2 equivalent)
            await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Attempt to use the revoked token (v2 JSON:API)
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert profile_response.status_code == 401

    async def test_revoke_without_authorization_header(self):
        """Test revocation without Authorization header fails with 401"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/revoke",
            )

            assert response.status_code == 401
            assert "not authenticated" in response.json()["detail"].lower()

    async def test_revoke_with_invalid_header_format(self):
        """Test revocation with invalid Authorization header format fails"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": "InvalidToken without Bearer"},
            )

            assert response.status_code == 401
            assert "not authenticated" in response.json()["detail"].lower()

    async def test_revoke_with_malformed_token(self):
        """Test revocation with malformed token fails with 401 (token verification fails before revocation)"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": "Bearer malformed.token.here"},
            )

            assert response.status_code == 401
            assert "could not validate credentials" in response.json()["detail"].lower()

    @patch("src.users.profile_router.verify_discord_user", new_callable=AsyncMock)
    async def test_revoke_discord_token_success(self, mock_verify):
        """Test successful revocation of Discord-authenticated token"""
        mock_verify.return_value = mock_verify_discord_user(
            "test_revoke_discord_discord_revoke_user"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register with Discord
            state1 = await create_valid_oauth_state()
            await client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "test_revoke_discord_discord_revoke_user",
                    "state": state1,
                    "display_name": "discord_revoke_user",
                },
            )

            # Login with Discord
            state2 = await create_valid_oauth_state()
            login_response = await client.post(
                "/api/v1/profile/auth/login/discord",
                json={"code": "test_revoke_discord_discord_revoke_user", "state": state2},
            )
            token = login_response.json()["access_token"]

            # Verify token works (v2 JSON:API)
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert profile_response.status_code == 200

            # Revoke the token (v1 - no v2 equivalent)
            revoke_response = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert revoke_response.status_code == 204

            # Verify revoked token cannot be used (v2 JSON:API)
            profile_response = await client.get(
                "/api/v2/profiles/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert profile_response.status_code == 401

    async def test_revoke_token_without_bearer_prefix(self):
        """Test revocation with missing Bearer prefix fails"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": "some_token_without_bearer"},
            )

            assert response.status_code == 401
            assert "not authenticated" in response.json()["detail"].lower()

    async def test_multiple_revocations_same_token(self):
        """Test that a revoked token cannot be used again (returns 401 on second attempt)"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Register
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "idempotent_revoke@example.com",
                    "password": "revoke_password",
                    "display_name": "idempotent_revoke_user",
                },
            )

            # Verify email for testing (bypass email verification flow)
            await verify_email_for_testing("idempotent_revoke@example.com")

            # Login
            login_response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "idempotent_revoke@example.com",
                    "password": "revoke_password",
                },
            )
            token = login_response.json()["access_token"]

            # First revocation should succeed
            revoke_response_1 = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert revoke_response_1.status_code == 204

            # Second attempt with revoked token fails authentication (401)
            # since the token is blacklisted and can't be used for any authenticated endpoint
            revoke_response_2 = await client.post(
                "/api/v1/profile/auth/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert revoke_response_2.status_code == 401
