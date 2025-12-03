"""
Integration tests for email verification flow.

Tests the complete email verification workflow including:
- Email registration with verification token generation
- Email verification endpoint
- Resend verification email endpoint
- Login prevention for unverified emails
- Token expiration handling
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.email import email_service

pytestmark = pytest.mark.asyncio


class TestEmailRegistrationWithVerification:
    """Test email registration generates verification tokens"""

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_register_email_creates_verification_token(self, mock_send_email):
        """Test that registering with email creates verification token"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "test@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "test_user",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["display_name"] == "test_user"
            assert "id" in data

            mock_send_email.assert_called_once()
            call_args = mock_send_email.call_args
            assert call_args.kwargs["to_email"] == "test@example.com"
            assert call_args.kwargs["display_name"] == "test_user"
            assert "verification_token" in call_args.kwargs
            assert len(call_args.kwargs["verification_token"]) > 0

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_register_email_with_email_send_failure(self, mock_send_email):
        """Test that registration succeeds even if email fails to send"""
        mock_send_email.side_effect = Exception("SMTP connection failed")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "smtp_fail@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "smtp_fail_user",
                },
            )

            assert response.status_code == 201


class TestEmailVerification:
    """Test email verification endpoint"""

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_verify_email_with_valid_token(self, mock_send_email):
        """Test successful email verification with valid token"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "verify@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "verify_user",
                },
            )

            mock_send_email.assert_called_once()
            verification_token = mock_send_email.call_args.kwargs["verification_token"]

            verify_response = await client.post(
                "/api/v1/profile/auth/verify-email",
                params={"token": verification_token},
            )

            assert verify_response.status_code == 200
            data = verify_response.json()
            assert data["display_name"] == "verify_user"

    async def test_verify_email_with_invalid_token(self):
        """Test email verification fails with invalid token"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/verify-email",
                params={"token": "invalid_token_12345"},
            )

            assert response.status_code == 400
            assert "invalid" in response.json()["detail"].lower()

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_verify_email_with_expired_token(self, mock_send_email):
        """Test email verification fails with expired token"""
        from src.database import get_db
        from src.users.profile_crud import (
            get_identity_by_provider,
            update_identity,
        )
        from src.users.profile_schemas import AuthProvider

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "expired@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "expired_user",
                },
            )

            verification_token = mock_send_email.call_args.kwargs["verification_token"]

            async for db in get_db():
                identity = await get_identity_by_provider(
                    db, AuthProvider.EMAIL, "expired@example.com"
                )
                await update_identity(
                    db,
                    identity,
                    {"email_verification_token_expires": datetime.now(UTC) - timedelta(hours=1)},
                )
                await db.commit()
                break

            response = await client.post(
                "/api/v1/profile/auth/verify-email",
                params={"token": verification_token},
            )

            assert response.status_code == 400
            assert "expired" in response.json()["detail"].lower()


class TestResendVerificationEmail:
    """Test resend verification email endpoint"""

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_resend_verification_email_success(self, mock_send_email):
        """Test successfully resending verification email"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "resend@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "resend_user",
                },
            )

            mock_send_email.reset_mock()

            response = await client.post(
                "/api/v1/profile/auth/resend-verification",
                params={"email": "resend@example.com"},
            )

            assert response.status_code == 200
            assert "success" in response.json()["message"].lower()
            mock_send_email.assert_called_once()

    async def test_resend_verification_email_not_found(self):
        """Test resending verification email for non-existent email"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/profile/auth/resend-verification",
                params={"email": "notfound@example.com"},
            )

            assert response.status_code == 400
            assert "not found" in response.json()["detail"].lower()

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_resend_verification_email_already_verified(self, mock_send_email):
        """Test resending verification email for already verified email"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "already_verified@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "verified_user",
                },
            )

            verification_token = mock_send_email.call_args.kwargs["verification_token"]

            await client.post(
                "/api/v1/profile/auth/verify-email",
                params={"token": verification_token},
            )

            response = await client.post(
                "/api/v1/profile/auth/resend-verification",
                params={"email": "already_verified@example.com"},
            )

            assert response.status_code == 400
            assert "already verified" in response.json()["detail"].lower()


class TestLoginWithUnverifiedEmail:
    """Test that unverified emails cannot login"""

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_login_with_unverified_email_fails(self, mock_send_email):
        """Test that login fails for unverified email"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "unverified@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "unverified_user",
                },
            )

            response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "unverified@example.com",
                    "password": "SecurePassword123!",
                },
            )

            assert response.status_code == 403
            assert "not verified" in response.json()["detail"].lower()

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_login_with_verified_email_success(self, mock_send_email):
        """Test that login succeeds after email verification"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "verified_login@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "verified_login_user",
                },
            )

            verification_token = mock_send_email.call_args.kwargs["verification_token"]

            await client.post(
                "/api/v1/profile/auth/verify-email",
                params={"token": verification_token},
            )

            response = await client.post(
                "/api/v1/profile/auth/login/email",
                data={
                    "username": "verified_login@example.com",
                    "password": "SecurePassword123!",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"


class TestTokenExpiration:
    """Test verification token expiration logic"""

    @patch.object(email_service, "send_verification_email", new_callable=AsyncMock)
    async def test_token_expires_after_24_hours(self, mock_send_email):
        """Test that verification token has 24 hour expiration"""
        from src.config import settings

        assert settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS == 24

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/profile/auth/register/email",
                params={
                    "email": "expiry_check@example.com",
                    "password": "SecurePassword123!",
                    "display_name": "expiry_user",
                },
            )

        from src.database import get_db
        from src.users.profile_crud import get_identity_by_provider
        from src.users.profile_schemas import AuthProvider

        async for db in get_db():
            identity = await get_identity_by_provider(
                db, AuthProvider.EMAIL, "expiry_check@example.com"
            )
            assert identity is not None
            assert identity.email_verification_token_expires is not None

            time_diff = identity.email_verification_token_expires - datetime.now(UTC)
            assert 23 <= time_diff.total_seconds() / 3600 <= 25
            break
