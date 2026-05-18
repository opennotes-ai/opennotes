"""Tests for src.services.email.EmailService.

Behavior-first: tests exercise the public interface only.
No coupling to private methods or implementation details.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.services.email import ConfigurationError, EmailService


def _settings(**overrides: object) -> Settings:
    """Build a minimal Settings object with SMTP fields pre-populated."""
    base = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": "user@example.com",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM_EMAIL": "noreply@example.com",
        "SMTP_FROM_NAME": "Vibecheck",
        "SMTP_USE_TLS": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestEmailServiceInit:
    def test_construction_does_not_raise_when_smtp_host_empty(self) -> None:
        settings = _settings(SMTP_HOST="")
        svc = EmailService(settings)
        assert svc is not None


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_send_email_success_with_starttls(self) -> None:
        settings = _settings(SMTP_USE_TLS=True)
        svc = EmailService(settings)

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.email.aiosmtplib.SMTP", return_value=mock_smtp):
            await svc.send_email(
                to_email="recipient@example.com",
                subject="Hello",
                html_content="<p>Hello</p>",
                text_content="Hello",
            )

        mock_smtp.starttls.assert_called_once()
        mock_smtp.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_success_with_implicit_tls(self) -> None:
        settings = _settings(SMTP_USE_TLS=False)
        svc = EmailService(settings)

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.email.aiosmtplib.SMTP", return_value=mock_smtp) as smtp_cls:
            await svc.send_email(
                to_email="recipient@example.com",
                subject="Hello",
                html_content="<p>Hello</p>",
            )

        smtp_cls.assert_called_once()
        call_kwargs = smtp_cls.call_args.kwargs
        assert call_kwargs.get("use_tls") is True
        mock_smtp.send_message.assert_called_once()
        mock_smtp.starttls.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_email_raises_when_smtp_host_empty(self) -> None:
        settings = _settings(SMTP_HOST="")
        svc = EmailService(settings)

        with pytest.raises(ConfigurationError, match="SMTP_HOST"):
            await svc.send_email(
                to_email="recipient@example.com",
                subject="Hello",
                html_content="<p>Hello</p>",
            )

    @pytest.mark.asyncio
    async def test_send_email_raises_on_smtp_transport_failure(self) -> None:
        import aiosmtplib

        settings = _settings()
        svc = EmailService(settings)

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=False)
        mock_smtp.starttls = AsyncMock(side_effect=aiosmtplib.SMTPConnectError("connection refused"))

        with patch("src.services.email.aiosmtplib.SMTP", return_value=mock_smtp):
            with pytest.raises(aiosmtplib.SMTPException):
                await svc.send_email(
                    to_email="recipient@example.com",
                    subject="Hello",
                    html_content="<p>Hello</p>",
                )

    @pytest.mark.asyncio
    async def test_to_email_not_logged_in_plaintext(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        settings = _settings()
        svc = EmailService(settings)

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=False)

        with caplog.at_level(logging.INFO, logger="src.services.email"):
            with patch("src.services.email.aiosmtplib.SMTP", return_value=mock_smtp):
                await svc.send_email(
                    to_email="private@secret.example.com",
                    subject="Hello",
                    html_content="<p>Hello</p>",
                )

        for record in caplog.records:
            assert "private@secret.example.com" not in record.getMessage(), (
                f"Plaintext PII found in log: {record.getMessage()!r}"
            )
