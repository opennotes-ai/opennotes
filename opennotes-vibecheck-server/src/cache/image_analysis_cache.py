from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import asyncpg

from src.analyses.safety.vision_client import SafeSearchResult


async def fetch_cached(
    pool: asyncpg.Pool, urls: list[str]
) -> dict[str, SafeSearchResult]:
    if not urls:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT image_url, result_payload
            FROM vibecheck_image_analysis_cache
            WHERE image_url = ANY($1::text[]) AND expires_at > now()
            """,
            urls,
        )
    out: dict[str, SafeSearchResult] = {}
    for row in rows:
        payload = row["result_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        out[row["image_url"]] = SafeSearchResult(**payload)
    return out


async def upsert_cached(
    pool: asyncpg.Pool,
    results: dict[str, SafeSearchResult | None],
    *,
    ttl_hours: int,
) -> None:
    serializable = {u: r for u, r in results.items() if r is not None}
    if not serializable:
        return
    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
    rows = [
        (url, json.dumps(asdict(result)), expires_at)
        for url, result in serializable.items()
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO vibecheck_image_analysis_cache
                (image_url, result_payload, checked_at, expires_at)
            VALUES ($1, $2::jsonb, now(), $3)
            ON CONFLICT (image_url) DO UPDATE SET
                result_payload = EXCLUDED.result_payload,
                checked_at = now(),
                expires_at = EXCLUDED.expires_at
            """,
            rows,
        )
