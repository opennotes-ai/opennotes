"""Rate-limit key helpers for Vibecheck server routes."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import Request
from slowapi.util import get_remote_address

from src.config import get_settings

_DEV_LIMITER_KEY_SALT = "DEV_SALT_NOT_FOR_PROD"


def hashed_remote_address(request: Request) -> str:
    """Return a compact HMAC digest for the request's remote address."""
    raw_address = get_remote_address(request)
    salt = get_settings().VIBECHECK_LIMITER_KEY_SALT or _DEV_LIMITER_KEY_SALT
    return hmac.new(
        salt.encode("utf-8"),
        raw_address.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]


def hashed_ip_and_job_id_key(request: Request) -> str:
    """Composite slowapi key for budgets scoped to one hashed IP and job id."""
    raw_job = request.path_params.get("job_id", "")
    return f"{hashed_remote_address(request)}:{raw_job}"


def server_submit_rate_key(request: Request) -> str:
    return f"vibecheck:rl:server:submit:{hashed_remote_address(request)}"


def server_poll_rate_key(request: Request) -> str:
    return f"vibecheck:rl:server:poll:{hashed_ip_and_job_id_key(request)}"


def server_retry_rate_key(request: Request) -> str:
    return f"vibecheck:rl:server:retry:{hashed_ip_and_job_id_key(request)}"
