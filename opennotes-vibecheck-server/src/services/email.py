"""Transactional email delivery via aiosmtplib.

PII policy: recipient addresses are never logged in plaintext.
All log messages use a hashed or redacted representation of to_email.
"""
from __future__ import annotations

import hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from src.config import Settings
from src.monitoring import get_logger

logger = get_logger(__name__)


class ConfigurationError(RuntimeError):
    """Raised when a required SMTP setting is absent."""


def _redact_email(email: str) -> str:
    """Return a stable, non-reversible token for the email address."""
    digest = hashlib.sha256(email.encode()).hexdigest()[:12]
    return f"sha256:{digest}"


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.SMTP_HOST
        self._port = settings.SMTP_PORT
        self._username = settings.SMTP_USERNAME
        self._password = settings.SMTP_PASSWORD
        self._from_email = settings.SMTP_FROM_EMAIL
        self._from_name = settings.SMTP_FROM_NAME
        self._use_tls = settings.SMTP_USE_TLS

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        if not self._host:
            raise ConfigurationError(
                "SMTP_HOST is not configured — cannot send email. "
                "Set SMTP_HOST in the environment or .env file."
            )

        redacted = _redact_email(to_email)
        logger.info("Attempting email send to %s subject=%r", redacted, subject)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self._from_name} <{self._from_email}>"
        msg["To"] = to_email

        if text_content:
            msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            if self._use_tls:
                async with aiosmtplib.SMTP(
                    hostname=self._host,
                    port=self._port,
                    timeout=10,
                ) as server:
                    await server.starttls()
                    if self._username and self._password:
                        await server.login(self._username, self._password)
                    await server.send_message(msg)
            else:
                async with aiosmtplib.SMTP(
                    hostname=self._host,
                    port=self._port,
                    use_tls=True,
                    timeout=10,
                ) as server:
                    if self._username and self._password:
                        await server.login(self._username, self._password)
                    await server.send_message(msg)

            logger.info("Email sent successfully to %s", redacted)
        except aiosmtplib.SMTPException as exc:
            logger.error("SMTP error sending email to %s: %s", redacted, exc)
            raise
        except Exception as exc:
            logger.error("Unexpected error sending email to %s: %s", redacted, exc)
            raise
