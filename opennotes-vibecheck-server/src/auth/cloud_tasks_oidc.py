"""OIDC verification for the Cloud Tasks -> internal-worker handoff.

The internal worker endpoint `POST /_internal/jobs/{job_id}/run` is
exposed on the same domain as the public API because Cloud Run does not
support private ingress selectively per path. To keep the endpoint safe
from open-internet POSTs, we require every request to carry an OIDC ID
token that:

    1. was signed by Google (`iss == https://accounts.google.com`);
    2. names our server URL as the audience (`aud == VIBECHECK_SERVER_URL`);
    3. was issued for the Cloud Tasks enqueuer service account
       (`email == VIBECHECK_TASKS_ENQUEUER_SA`);
    4. has `email_verified == True`.

Any mismatch returns 401 with a stable `error_code=unauthorized` slug so
frontend/infra log correlation can tell "Cloud Tasks misconfigured" apart
from "token signature is wrong".

Implementation notes
--------------------

`_verify_oauth2_token` is the single monkeypatch point tests substitute.
We wrap the real `google.oauth2.id_token.verify_oauth2_token` rather than
importing it directly inside the dependency so tests can swap it without
patching a deep import path. The real verifier already asserts the
signature via Google's JWKS and raises `ValueError` on audience mismatch,
but we **still** re-check `aud`, `iss`, `email`, `email_verified` after
the verifier returns — defence-in-depth against a future API change that
would relax one of those fields.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from src.config import Settings, get_settings
from src.monitoring import get_logger

logger = get_logger(__name__)

_EXPECTED_ISSUER = "https://accounts.google.com"


def _verify_oauth2_token(
    token: str, request: Any, audience: str
) -> Mapping[str, Any]:
    """Thin wrapper around google.oauth2.id_token.verify_oauth2_token.

    Isolated so tests can monkeypatch one small surface instead of the
    google SDK module. In production this calls the real verifier which
    fetches Google's JWKS, checks the signature, and asserts audience
    equality (raising ValueError on mismatch).
    """
    return id_token.verify_oauth2_token(token, request, audience=audience)


def _extract_bearer_token(request: Request) -> str | None:
    """Pull the bearer token from `Authorization: Bearer <jwt>`.

    Case-insensitive on the scheme prefix. Returns None when the header
    is absent or malformed — callers treat that as 401.
    """
    header = request.headers.get("authorization") or request.headers.get(
        "Authorization"
    )
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _reject(reason: str) -> HTTPException:
    """Build the 401 response with a stable `error_code` slug.

    We log the reason so operators can distinguish configuration mismatches
    (wrong audience / wrong SA) from signature failures. The response body
    itself carries only `unauthorized` so an attacker cannot probe which
    field of the claim set rejected them.
    """
    logger.warning("oidc verification failed: reason=%s", reason)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error_code": "unauthorized", "message": "invalid oidc token"},
    )


async def verify_cloud_tasks_oidc(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency that verifies Cloud Tasks OIDC credentials.

    Raises `HTTPException(401)` on any failure (missing header, bad scheme,
    signature failure, or any claim mismatch). On success returns None —
    the handler proceeds with no extra state; the caller is implicit.
    """
    if not settings.VIBECHECK_SERVER_URL or not settings.VIBECHECK_TASKS_ENQUEUER_SA:
        # Deploy-time misconfig: refuse to accept any token rather than
        # accidentally accepting unauthenticated callers. Operators wire
        # both settings via `.env.yaml` before traffic reaches the endpoint.
        raise _reject("settings_missing")

    token = _extract_bearer_token(request)
    if token is None:
        raise _reject("missing_bearer")

    try:
        claims = _verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.VIBECHECK_SERVER_URL,
        )
    except Exception as exc:  # google.auth raises ValueError; catch broadly
        raise _reject(f"verify_raised:{type(exc).__name__}")

    if not isinstance(claims, Mapping):
        raise _reject("claims_not_mapping")

    if claims.get("iss") != _EXPECTED_ISSUER:
        raise _reject("issuer_mismatch")
    if claims.get("aud") != settings.VIBECHECK_SERVER_URL:
        raise _reject("audience_mismatch")
    if claims.get("email") != settings.VIBECHECK_TASKS_ENQUEUER_SA:
        raise _reject("email_mismatch")
    if not claims.get("email_verified"):
        raise _reject("email_unverified")


__all__ = ["verify_cloud_tasks_oidc"]
