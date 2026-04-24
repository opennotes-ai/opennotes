from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import asyncpg

from src.analyses.safety._schemas import WebRiskFinding


async def fetch_cached(pool: asyncpg.Pool, urls: list[str]) -> dict[str, WebRiskFinding]:
    if not urls:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT url, finding_payload
            FROM vibecheck_web_risk_lookups
            WHERE url = ANY($1::text[]) AND expires_at > now()
            """,
            urls,
        )
    out: dict[str, WebRiskFinding] = {}
    for row in rows:
        payload = row["finding_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        out[row["url"]] = WebRiskFinding.model_validate(payload)
    return out


async def upsert_cached(
    pool: asyncpg.Pool,
    findings: dict[str, WebRiskFinding],
    *,
    ttl_hours: int = 6,
) -> None:
    if not findings:
        return
    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
    rows = [
        (url, json.dumps(f.model_dump()), expires_at)
        for url, f in findings.items()
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO vibecheck_web_risk_lookups (url, finding_payload, checked_at, expires_at)
            VALUES ($1, $2::jsonb, now(), $3)
            ON CONFLICT (url) DO UPDATE SET
                finding_payload = EXCLUDED.finding_payload,
                checked_at = now(),
                expires_at = EXCLUDED.expires_at
            """,
            rows,
        )
