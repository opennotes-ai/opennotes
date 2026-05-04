from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException

from src.config import Settings, get_settings


async def require_scrape_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Require the operator-only scrape API bearer token.

    This static token is for internal/operator use only. Do not embed it in a
    publicly distributed browser extension; a public extension needs per-device
    token issuance and revocation.
    """
    configured = settings.VIBECHECK_SCRAPE_API_TOKEN
    if not configured or not authorization:
        raise HTTPException(status_code=401, detail="invalid_token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="invalid_token")

    if not secrets.compare_digest(token, configured):
        raise HTTPException(status_code=401, detail="invalid_token")
