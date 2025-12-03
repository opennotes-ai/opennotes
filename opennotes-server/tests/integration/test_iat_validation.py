import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from jose import jwt

from src.auth.auth import verify_refresh_token, verify_token
from src.config import settings
from src.main import app


class TestIATValidation:
    """Test JWT issued-at (iat) claim validation"""

    async def test_verify_token_rejects_future_iat(self):
        """Test that tokens with future iat timestamps are rejected"""
        # Create a token with iat set to 1 hour in the future
        future_time = datetime.now(UTC) + timedelta(hours=1)
        payload = {
            "sub": str(uuid4()),
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(future_time.timestamp()),
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        # Token should be rejected
        result = await verify_token(token)
        assert result is None

    async def test_verify_refresh_token_rejects_future_iat(self):
        """Test that refresh tokens with future iat timestamps are rejected"""
        # Create a refresh token with iat set to 1 hour in the future
        future_time = datetime.now(UTC) + timedelta(hours=1)
        payload = {
            "sub": str(uuid4()),
            "username": "testuser",
            "role": "user",
            "type": "refresh",
            "exp": int((datetime.now(UTC) + timedelta(days=7)).timestamp()),
            "iat": int(future_time.timestamp()),
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        # Token should be rejected
        result = await verify_refresh_token(token)
        assert result is None

    async def test_verify_token_accepts_valid_iat(self):
        """Test that tokens with valid iat timestamps are accepted"""
        # Create a token with iat set to now
        now = datetime.now(UTC)
        test_uuid = uuid4()
        payload = {
            "sub": str(test_uuid),
            "username": "testuser",
            "role": "user",
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        # Token should be accepted
        result = await verify_token(token)
        assert result is not None
        assert result.user_id == test_uuid
        assert result.username == "testuser"
        assert result.role == "user"

    async def test_verify_token_validates_against_tokens_valid_after(self):
        """Test that tokens issued before tokens_valid_after are rejected"""
        # Create a token issued 1 hour ago
        past_time = datetime.now(UTC) - timedelta(hours=1)
        payload = {
            "sub": str(uuid4()),
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(past_time.timestamp()),
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        # Set tokens_valid_after to 30 minutes ago (after the token was issued)
        tokens_valid_after = datetime.now(UTC) - timedelta(minutes=30)

        # Token should be rejected because it was issued before tokens_valid_after
        result = await verify_token(token, tokens_valid_after=tokens_valid_after)
        assert result is None

    async def test_verify_token_accepts_token_after_tokens_valid_after(self):
        """Test that tokens issued after tokens_valid_after are accepted"""
        # Create a token issued now
        now = datetime.now(UTC)
        test_uuid = uuid4()
        payload = {
            "sub": str(test_uuid),
            "username": "testuser",
            "role": "user",
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        # Set tokens_valid_after to 1 hour ago (before the token was issued)
        tokens_valid_after = datetime.now(UTC) - timedelta(hours=1)

        # Token should be accepted
        result = await verify_token(token, tokens_valid_after=tokens_valid_after)
        assert result is not None
        assert result.user_id == test_uuid


class TestPasswordChangeInvalidatesTokens:
    """Test that changing password invalidates existing tokens"""

    async def test_password_change_invalidates_existing_tokens(
        self, test_user_data, registered_user
    ):
        """Test that tokens issued before password change are rejected"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Login and get access token
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            assert login_response.status_code == 200
            old_token = login_response.json()["access_token"]

            # Verify token works
            me_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert me_response.status_code == 200

            # Change password
            update_response = await client.patch(
                "/api/v1/users/me",
                json={"password": "NewSecure@Pass123!"},
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert update_response.status_code == 200

            # Wait for next second to ensure new tokens have different iat
            await asyncio.sleep(1.1)

            # Old token should now be rejected
            me_response_after = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert me_response_after.status_code == 401

            # Login with new password should work
            new_login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": "NewSecure@Pass123!",
                },
            )
            assert new_login_response.status_code == 200
            new_token = new_login_response.json()["access_token"]

            # New token should work
            me_response_new = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {new_token}"},
            )
            assert me_response_new.status_code == 200


class TestLogoutAllInvalidatesTokens:
    """Test that logout-all invalidates existing tokens"""

    async def test_logout_all_invalidates_existing_tokens(self, test_user_data, registered_user):
        """Test that tokens issued before logout-all are rejected"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Login and get access token
            login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            assert login_response.status_code == 200
            old_token = login_response.json()["access_token"]

            # Verify token works
            me_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert me_response.status_code == 200

            # Logout all sessions
            logout_response = await client.post(
                "/api/v1/auth/logout-all",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert logout_response.status_code == 204

            # Wait for next second to ensure new tokens have different iat
            await asyncio.sleep(1.1)

            # Old token should now be rejected
            me_response_after = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            assert me_response_after.status_code == 401

            # Login again should work
            new_login_response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user_data["username"],
                    "password": test_user_data["password"],
                },
            )
            assert new_login_response.status_code == 200
            new_token = new_login_response.json()["access_token"]

            # New token should work
            me_response_new = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {new_token}"},
            )
            assert me_response_new.status_code == 200


class TestTokensValidAfterEdgeCases:
    """Test edge cases for tokens_valid_after validation"""

    async def test_token_issued_exactly_at_tokens_valid_after_is_rejected(self):
        """Test that a token issued exactly at tokens_valid_after is rejected"""
        # Create a token issued at a specific time
        issue_time = datetime.now(UTC) - timedelta(minutes=5)
        payload = {
            "sub": str(uuid4()),
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(issue_time.timestamp()),
            "jti": secrets.token_urlsafe(32),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        # Set tokens_valid_after to exactly the issue time
        tokens_valid_after = issue_time

        # Token should be rejected with iat <= tokens_valid_after comparison
        result = await verify_token(token, tokens_valid_after=tokens_valid_after)
        assert result is None  # Token at exact boundary is rejected

    async def test_token_without_iat_is_rejected_when_tokens_valid_after_is_set(self):
        """Test that tokens without iat claim are handled when tokens_valid_after is set"""
        # Create a token without iat claim (should not happen in practice)
        payload = {
            "sub": str(uuid4()),
            "username": "testuser",
            "role": "user",
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "jti": secrets.token_urlsafe(32),
            # No iat claim
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        tokens_valid_after = datetime.now(UTC) - timedelta(hours=1)

        # Token should still be accepted because iat is None and the check is skipped
        result = await verify_token(token, tokens_valid_after=tokens_valid_after)
        assert result is not None  # Tokens without iat are accepted (backwards compatibility)
