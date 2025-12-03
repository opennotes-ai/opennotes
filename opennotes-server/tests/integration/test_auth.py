import asyncio

from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.main import app

# Database setup is handled by conftest.py fixtures


class TestUserRegistration:
    async def test_register_new_user(self, test_user_data):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/register", json=test_user_data)

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["username"] == test_user_data["username"]
            assert data["email"] == test_user_data["email"]
            assert data["full_name"] == test_user_data["full_name"]
            assert data["role"] == "user"
            assert data["is_active"] is True
            assert data["is_superuser"] is False
            assert "id" in data
            assert "created_at" in data

    async def test_register_duplicate_username(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            duplicate_data = test_user_data.copy()
            duplicate_data["email"] = "another@example.com"

            response = await client.post("/api/v1/auth/register", json=duplicate_data)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "username already registered" in response.json()["detail"].lower()

    async def test_register_duplicate_email(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            duplicate_data = test_user_data.copy()
            duplicate_data["username"] = "anotheruser"

            response = await client.post("/api/v1/auth/register", json=duplicate_data)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "email already registered" in response.json()["detail"].lower()

    async def test_register_invalid_email(self, test_user_data):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid_data = test_user_data.copy()
            invalid_data["email"] = "not-an-email"

            response = await client.post("/api/v1/auth/register", json=invalid_data)

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_register_short_password(self, test_user_data):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid_data = test_user_data.copy()
            invalid_data["password"] = "short"

            response = await client.post("/api/v1/auth/register", json=invalid_data)

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUserLogin:
    async def test_login_success(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"
            assert "expires_in" in data

    async def test_login_wrong_password(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": "wrongpassword",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_login_nonexistent_user(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": "nonexistent",
                    "password": "TestPassword123!",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestProtectedEndpoints:
    async def test_access_protected_endpoint_without_token(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/users/me")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_access_protected_endpoint_with_valid_token(
        self, test_user_data, registered_user
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["username"] == test_user_data["username"]
            assert data["email"] == test_user_data["email"]

    async def test_access_protected_endpoint_with_invalid_token(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": "Bearer invalid_token"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTokenRefresh:
    async def test_refresh_token_success(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            refresh_token = login_response.json()["refresh_token"]

            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    async def test_refresh_with_invalid_token(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid_token"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAPIKeys:
    async def test_create_api_key(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Test API Key", "expires_in_days": 30},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert "key" in data
            assert data["name"] == "Test API Key"
            assert len(data["key"]) > 20

    async def test_api_key_authentication_on_protected_endpoint(
        self, test_user_data, registered_user
    ):
        """Test that API keys can be used to access endpoints with flexible auth"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First create an API key using JWT
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            jwt_token = login_response.json()["access_token"]

            # Create API key
            create_response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Auth Test Key", "expires_in_days": 7},
                headers={"Authorization": f"Bearer {jwt_token}"},
            )
            api_key = create_response.json()["key"]

            # Test API key works on notes endpoint (uses get_current_user_or_api_key)
            # GET /api/v2/notes requires authentication but accepts both JWT and API keys
            response = await client.get(
                "/api/v2/notes?page[number]=1&page[size]=10",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            # Should succeed with 200 OK (empty list since no notes exist)
            # JSON:API response format with data array
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "data" in data
            assert isinstance(data["data"], list)
            assert "jsonapi" in data

    async def test_api_key_authentication_invalid_key(self):
        """Test that invalid API keys are rejected"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": "Bearer invalid_api_key_12345"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_list_api_keys(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Test API Key 1"},
                headers={"Authorization": f"Bearer {token}"},
            )

            await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Test API Key 2"},
                headers={"Authorization": f"Bearer {token}"},
            )

            response = await client.get(
                "/api/v1/users/me/api-keys",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data) == 2
            assert all(key["key"] == "***" for key in data)

    async def test_revoke_api_key(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            create_response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "Test API Key"},
                headers={"Authorization": f"Bearer {token}"},
            )
            api_key_id = create_response.json()["id"]

            response = await client.delete(
                f"/api/v1/users/me/api-keys/{api_key_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_204_NO_CONTENT


class TestUserUpdate:
    async def test_update_user_profile(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token = login_response.json()["access_token"]

            response = await client.patch(
                "/api/v1/users/me",
                json={"full_name": "Updated Name"},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["full_name"] == "Updated Name"


class TestIATValidation:
    """Tests for JWT iat (issued at) claim validation"""

    async def test_reject_future_tokens(self, test_user_data, registered_user):
        """Tokens with future iat timestamps should be rejected"""
        from datetime import UTC, datetime, timedelta

        from jose import jwt

        from src.config import settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create a token with future iat
            future_time = datetime.now(UTC) + timedelta(hours=1)
            payload = {
                "sub": str(registered_user["id"]),
                "username": registered_user["username"],
                "role": registered_user["role"],
                "exp": int((datetime.now(UTC) + timedelta(hours=2)).timestamp()),
                "iat": int(future_time.timestamp()),  # Future iat
                "jti": "test_jti",
            }

            token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

            # Attempt to use the token
            response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Should be rejected
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # TODO: Add test for password_change_invalidates_old_tokens once bcrypt token length issue is fixed
    # Currently hits: ValueError: Password too long (max 72 bytes in UTF-8) in create_refresh_token
    # This is a pre-existing issue where JWT refresh tokens exceed bcrypt's 72-byte limit


class TestTokenRevocation:
    async def test_revoke_current_access_token(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            access_token = login_response.json()["access_token"]

            revoke_response = await client.post(
                "/api/v1/auth/revoke-token",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            assert revoke_response.status_code == status.HTTP_204_NO_CONTENT

            profile_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            assert profile_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_revoke_token_without_authorization_header(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            _login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )

            revoke_response = await client.post(
                "/api/v1/auth/revoke-token",
            )

            assert revoke_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_revoke_all_user_tokens(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login1_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token1 = login1_response.json()["access_token"]

            # Wait for next second to ensure tokens have different iat
            await asyncio.sleep(1.1)

            login2_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            token2 = login2_response.json()["access_token"]

            revoke_response = await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {token1}"},
            )

            assert revoke_response.status_code == status.HTTP_204_NO_CONTENT

            profile1_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {token1}"},
            )
            assert profile1_response.status_code == status.HTTP_401_UNAUTHORIZED

            profile2_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {token2}"},
            )
            assert profile2_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_logout_revokes_both_access_and_refresh_tokens(
        self, test_user_data, registered_user
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            access_token = login_response.json()["access_token"]
            refresh_token = login_response.json()["refresh_token"]

            logout_response = await client.post(
                "/api/v1/auth/logout",
                params={"refresh_token": refresh_token},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            assert logout_response.status_code == status.HTTP_204_NO_CONTENT

            profile_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert profile_response.status_code == status.HTTP_401_UNAUTHORIZED

            refresh_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
            assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_revoked_token_cannot_access_protected_endpoints(
        self, test_user_data, registered_user
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            access_token = login_response.json()["access_token"]

            await client.post(
                "/api/v1/auth/revoke-token",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            profile_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert profile_response.status_code == status.HTTP_401_UNAUTHORIZED

            notes_response = await client.get(
                "/api/v2/notes?page[number]=1&page[size]=10",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert notes_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_expired_token_not_added_to_redis(self, test_user_data, registered_user):
        from datetime import UTC, datetime, timedelta

        from jose import jwt

        from src.config import settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            past_time = datetime.now(UTC) - timedelta(hours=2)
            payload = {
                "sub": str(registered_user["id"]),
                "username": registered_user["username"],
                "role": registered_user["role"],
                "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
                "iat": int(past_time.timestamp()),
                "jti": "expired_token_jti",
            }

            expired_token = jwt.encode(
                payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
            )

            revoke_response = await client.post(
                "/api/v1/auth/revoke-token",
                headers={"Authorization": f"Bearer {expired_token}"},
            )

            assert revoke_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_new_token_after_revoke_all_works(self, test_user_data, registered_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login1_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            old_token = login1_response.json()["access_token"]

            revoke_response = await client.post(
                "/api/v1/auth/revoke-all-tokens",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert revoke_response.status_code == status.HTTP_204_NO_CONTENT

            await asyncio.sleep(1.1)

            login2_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            new_token = login2_response.json()["access_token"]

            profile_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {new_token}"},
            )
            assert profile_response.status_code == status.HTTP_200_OK
            assert profile_response.json()["username"] == test_user_data["username"]
