import logging
import secrets
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import pendulum

from src.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        if text_content:
            part1 = MIMEText(text_content, "plain")
            msg.attach(part1)

        part2 = MIMEText(html_content, "html")
        msg.attach(part2)

        try:
            if self.use_tls:
                async with aiosmtplib.SMTP(
                    hostname=self.smtp_host, port=self.smtp_port, timeout=10
                ) as server:
                    await server.starttls()
                    if self.smtp_username and self.smtp_password:
                        await server.login(self.smtp_username, self.smtp_password)
                    await server.send_message(msg)
            else:
                async with aiosmtplib.SMTP(
                    hostname=self.smtp_host, port=self.smtp_port, use_tls=True, timeout=10
                ) as server:
                    if self.smtp_username and self.smtp_password:
                        await server.login(self.smtp_username, self.smtp_password)
                    await server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
        except aiosmtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {to_email}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            raise

    async def send_verification_email(
        self, to_email: str, display_name: str, verification_token: str
    ) -> None:
        verification_url = f"{settings.CORS_ORIGINS[0]}/verify-email?token={verification_token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4a5568;">Welcome to OpenNotes, {display_name}!</h2>
                <p>Thank you for registering. Please verify your email address to complete your registration.</p>
                <p>Click the button below to verify your email:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_url}"
                       style="background-color: #4299e1; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 4px; display: inline-block;">
                        Verify Email Address
                    </a>
                </div>
                <p style="color: #718096; font-size: 14px;">
                    Or copy and paste this link into your browser:<br>
                    <a href="{verification_url}" style="color: #4299e1;">{verification_url}</a>
                </p>
                <p style="color: #718096; font-size: 14px;">
                    This verification link will expire in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.
                </p>
                <p style="color: #718096; font-size: 14px;">
                    If you didn't create an account with OpenNotes, you can safely ignore this email.
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
        Welcome to OpenNotes, {display_name}!

        Thank you for registering. Please verify your email address to complete your registration.

        Verify your email by clicking this link:
        {verification_url}

        This verification link will expire in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.

        If you didn't create an account with OpenNotes, you can safely ignore this email.
        """

        await self.send_email(
            to_email=to_email,
            subject="Verify your Open Notes email address",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_password_reset_email(
        self, to_email: str, display_name: str, reset_token: str
    ) -> None:
        reset_url = f"{settings.CORS_ORIGINS[0]}/reset-password?token={reset_token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4a5568;">Password Reset Request</h2>
                <p>Hi {display_name},</p>
                <p>We received a request to reset your password. Click the button below to create a new password:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}"
                       style="background-color: #4299e1; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 4px; display: inline-block;">
                        Reset Password
                    </a>
                </div>
                <p style="color: #718096; font-size: 14px;">
                    Or copy and paste this link into your browser:<br>
                    <a href="{reset_url}" style="color: #4299e1;">{reset_url}</a>
                </p>
                <p style="color: #718096; font-size: 14px;">
                    This password reset link will expire in 1 hour.
                </p>
                <p style="color: #718096; font-size: 14px;">
                    If you didn't request a password reset, you can safely ignore this email.
                    Your password will remain unchanged.
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
        Password Reset Request

        Hi {display_name},

        We received a request to reset your password. Click the link below to create a new password:
        {reset_url}

        This password reset link will expire in 1 hour.

        If you didn't request a password reset, you can safely ignore this email.
        Your password will remain unchanged.
        """

        await self.send_email(
            to_email=to_email,
            subject="Reset your Open Notes password",
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    def generate_verification_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_token_expiry() -> datetime:
        return pendulum.now("UTC") + pendulum.duration(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )


email_service = EmailService()
