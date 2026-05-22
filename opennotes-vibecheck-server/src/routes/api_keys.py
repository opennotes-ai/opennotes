"""POST /api/keys/request — self-serve API key issuance (TASK-1651.04).

Flow:
  1. Lowercase and validate email (MX check, 5s timeout) → 400 on failure
  2. Generate opk_<prefix>_<secret> key in memory; compute SHA-256 hash
  3. Acquire pg_advisory_lock on a dedicated connection (keyed on email hash)
  4. Send email with the plaintext key
     → If send fails: 503, release lock, no DB state changes
  5. BEGIN TXN: soft-delete prior active rows; INSERT new row; COMMIT
  6. Release advisory lock
  7. Return { ok: true }

PII policy: raw email is never logged; rate-limit per-email key uses
sha256(lower(email))[:16] to avoid PII in the slowapi backend.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import secrets
import struct
from typing import Any

import aiosmtplib
import asyncpg
import email_validator
import uuid_utils
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from limits import parse as _parse_limit
from limits.aio.strategies import MovingWindowRateLimiter as _AsyncMWRL
from pydantic import BaseModel

from src.config import get_settings
from src.monitoring import get_logger
from src.services.email import ConfigurationError, EmailService
from src.services.limiter_storage import (
    build_limiter_storage,
    build_slowapi_limiter,
    clear_memory_storage_state,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/keys", tags=["api-keys"])

_EMAIL_RATE_LIMIT_SCOPE = "vibecheck-key-request-email"
_IP_RATE_LIMIT_SCOPE = "vibecheck-key-request-ip"


def _ip_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        client_ip = xff.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"
    return f"apikey:rl:ip:{client_ip}"


def _email_key_from_header(request: Request) -> str:
    raw = request.headers.get("X-Rate-Limit-Email-Key", "unknown")
    return f"apikey:rl:email:{raw}"


_email_limiter = build_slowapi_limiter(
    key_func=_email_key_from_header,
    consumer_label="vibecheck_key_request_email",
)
_email_limiter_storage = build_limiter_storage("vibecheck_key_request_email_storage")

_ip_limiter = build_slowapi_limiter(
    key_func=_ip_key,
    consumer_label="vibecheck_key_request_ip",
)
_ip_limiter_storage = build_limiter_storage("vibecheck_key_request_ip_storage")


def reset_rate_limit_state_for_testing() -> None:
    """Drop in-process rate limit state. Used by tests between cases."""
    clear_memory_storage_state(_email_limiter_storage)
    clear_memory_storage_state(_ip_limiter_storage)
    try:
        _email_limiter.reset()
    except Exception:
        pass
    try:
        _ip_limiter.reset()
    except Exception:
        pass


class APIKeyRequest(BaseModel):
    email: str


class APIKeyRequestResponse(BaseModel):
    ok: bool


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message},
    )


def _hashed_email_key(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


def _email_lock_key(email_lower: str) -> int:
    digest = hashlib.sha256(email_lower.encode()).digest()[:8]
    return struct.unpack(">q", digest)[0]


def _generate_key() -> tuple[str, str, str]:
    prefix = secrets.token_hex(4)
    secret = secrets.token_hex(16)
    full_key = f"opk_{prefix}_{secret}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


def _build_email_body(email: str, full_key: str) -> tuple[str, str]:
    text = (
        f"Your Vibecheck API key:\n\n"
        f"  {full_key}\n\n"
        f"Usage example:\n"
        f"  curl -H 'Authorization: Bearer {full_key}' https://vibecheck.opennotes.ai/api/scrape\n\n"
        f"This key will be deleted if not used within 48 hours.\n\n"
        f"Keep this key private — it grants scraping access on your behalf.\n"
    )
    html = (
        f"<p>Your Vibecheck API key:</p>"
        f"<pre>{full_key}</pre>"
        f"<p>Usage example:</p>"
        f"<pre>curl -H 'Authorization: Bearer {full_key}' "
        f"https://vibecheck.opennotes.ai/api/scrape</pre>"
        f"<p><strong>This key will be deleted if not used within 48 hours.</strong></p>"
        f"<p>Keep this key private — it grants scraping access on your behalf.</p>"
    )
    return text, html


async def _validate_email(email: str) -> str | None:
    """Validate email including MX lookup with a 5s timeout.

    Returns the normalised email (lowercased/validated) or None on failure.
    Raises TimeoutError if the DNS check takes > 5s.
    """
    def _do_validate() -> str:
        result = email_validator.validate_email(email, check_deliverability=True)
        return result.normalized.lower()

    return await asyncio.wait_for(
        asyncio.to_thread(_do_validate),
        timeout=5,
    )


def _get_db_pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise RuntimeError("db_pool not initialized")
    return pool


async def _check_rate_limits(
    request: Request,
    email_hash: str,
    *,
    ip_limit: int = 10,
    email_limit: int = 5,
) -> JSONResponse | None:
    """Check both per-IP and per-email rate limits.

    Returns a 429 JSONResponse if exceeded, or None to continue.
    Uses the limits library directly for moving-window checks.
    """
    ip_key = _ip_key(request)
    email_key = f"apikey:rl:email:{email_hash}"

    ip_strategy = _AsyncMWRL(_ip_limiter_storage)
    email_strategy = _AsyncMWRL(_email_limiter_storage)

    ip_item = _parse_limit(f"{ip_limit}/hour")
    email_item = _parse_limit(f"{email_limit}/hour")

    ip_allowed = await ip_strategy.hit(ip_item, ip_key)
    if not ip_allowed:
        return _error_response(429, "rate_limited", "Too many requests from this IP")

    email_allowed = await email_strategy.hit(email_item, email_key)
    if not email_allowed:
        return _error_response(429, "rate_limited", "Too many requests for this email")

    return None


async def _issue_key_with_lock(
    pool: Any,
    email_norm: str,
    email_service: Any,
    key_prefix: str,
    key_hash: str,
    html_body: str,
    text_body: str,
) -> JSONResponse | APIKeyRequestResponse:
    lock_key = _email_lock_key(email_norm)
    async with pool.acquire() as lock_conn:
        await lock_conn.fetchval("SELECT pg_advisory_lock($1::bigint)", lock_key)
        try:
            return await _locked_issue(
                pool, lock_conn, email_norm, email_service, key_prefix, key_hash, html_body, text_body
            )
        finally:
            await lock_conn.fetchval("SELECT pg_advisory_unlock($1::bigint)", lock_key)


async def _locked_issue(
    pool: Any,
    lock_conn: Any,
    email_norm: str,
    email_service: Any,
    key_prefix: str,
    key_hash: str,
    html_body: str,
    text_body: str,
) -> JSONResponse | APIKeyRequestResponse:
    existing = await lock_conn.fetchrow(
        "SELECT created_at FROM public.vibecheck_api_keys "
        "WHERE lower(email) = lower($1) AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT 1",
        email_norm,
    )
    if existing is not None:
        age = datetime.datetime.now(datetime.UTC) - existing["created_at"].replace(
            tzinfo=datetime.UTC
        )
        if age.total_seconds() < 30:
            return APIKeyRequestResponse(ok=True)

    try:
        await email_service.send_email(
            to_email=email_norm,
            subject="Your Vibecheck API key",
            html_content=html_body,
            text_content=text_body,
        )
    except (TimeoutError, ConfigurationError, aiosmtplib.SMTPException, OSError) as exc:
        logger.exception(
            "email send failed for email_hash=%s error_code=%s",
            _hashed_email_key(email_norm),
            type(exc).__name__,
        )
        return _error_response(
            503,
            "email_send_failed",
            "Failed to send the API key email. Please try again later.",
        )

    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE public.vibecheck_api_keys SET deleted_at = now() "
                "WHERE lower(email) = lower($1) AND deleted_at IS NULL",
                email_norm,
            )
            new_id = str(uuid_utils.uuid7())
            await conn.execute(
                "INSERT INTO public.vibecheck_api_keys "
                "(id, email, key_prefix, key_hash) "
                "VALUES ($1, $2, $3, $4)",
                new_id,
                email_norm,
                key_prefix,
                key_hash,
            )
    except (asyncpg.PostgresError, OSError) as exc:
        logger.exception(
            "api key db write failed for email_hash=%s error_code=%s",
            _hashed_email_key(email_norm),
            type(exc).__name__,
        )
        return _error_response(
            503,
            "db_write_failed",
            "Key issued via email but database write failed. "
            "Your first scrape attempt will prompt you to re-request a key.",
        )

    return APIKeyRequestResponse(ok=True)


@router.post("/request", status_code=200, response_model=APIKeyRequestResponse)
async def request_api_key(
    request: Request,
    body: APIKeyRequest,
) -> Any:
    """Issue a self-serve API key via email. No authorization required."""
    email_raw = body.email.lower().strip()

    try:
        email_norm = await _validate_email(email_raw)
    except (TimeoutError, email_validator.EmailNotValidError):
        return _error_response(
            400,
            "invalid_email",
            "The email address is invalid or could not be verified. "
            "Please check the address and try again.",
        )

    if email_norm is None:
        return _error_response(400, "invalid_email", "The email address could not be validated.")

    email_hash = _hashed_email_key(email_norm)
    rate_limit_response = await _check_rate_limits(request, email_hash)
    if rate_limit_response is not None:
        return rate_limit_response

    full_key, key_prefix, key_hash = _generate_key()
    settings = get_settings()
    email_service = EmailService(settings)
    text_body, html_body = _build_email_body(email_norm, full_key)
    pool = _get_db_pool(request)

    return await _issue_key_with_lock(
        pool, email_norm, email_service, key_prefix, key_hash, html_body, text_body
    )


__all__ = ["APIKeyRequest", "APIKeyRequestResponse", "router"]
