from __future__ import annotations

import datetime
import hashlib
import hmac
import logging

from fastapi import Depends, Header, HTTPException, Request

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

_INVALID = HTTPException(status_code=401, detail="invalid_token")


async def require_scrape_token(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not authorization:
        raise _INVALID

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _INVALID

    if settings.VIBECHECK_LEGACY_SCRAPE_TOKEN and token == settings.VIBECHECK_LEGACY_SCRAPE_TOKEN:
        logger.info("legacy scrape token used")
        return

    parts = token.split("_")
    if len(parts) != 3 or parts[0] != "opk":
        raise _INVALID

    key_prefix = parts[1]

    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status_code=503, detail="database pool not initialized")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, key_hash, deleted_at, last_used_at, created_at"
            " FROM vibecheck_api_keys WHERE key_prefix = $1",
            key_prefix,
        )

    if row is None:
        raise _INVALID

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(token_hash, row["key_hash"]):
        raise _INVALID

    if row["deleted_at"] is not None:
        raise _INVALID

    if row["last_used_at"] is None:
        threshold = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=48)
        if row["created_at"] < threshold:
            raise _INVALID

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE vibecheck_api_keys SET last_used_at = now() WHERE id = $1",
                row["id"],
            )
    except Exception as exc:
        logger.warning("failed to update last_used_at for key %s: %s", key_prefix, exc)
