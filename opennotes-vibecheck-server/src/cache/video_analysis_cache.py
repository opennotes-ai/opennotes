from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import asyncpg

from src.analyses.safety._schemas import FrameFinding


async def fetch_cached(
    pool: asyncpg.Pool, urls: list[str]
) -> dict[str, list[FrameFinding]]:
    if not urls:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT video_url, frame_findings_payload
            FROM vibecheck_video_analysis_cache
            WHERE video_url = ANY($1::text[]) AND expires_at > now()
            """,
            urls,
        )
    out: dict[str, list[FrameFinding]] = {}
    for row in rows:
        payload = row["frame_findings_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        out[row["video_url"]] = [FrameFinding.model_validate(f) for f in payload]
    return out


async def upsert_cached(
    pool: asyncpg.Pool,
    results: dict[str, list[FrameFinding]],
    *,
    ttl_hours: int,
) -> None:
    serializable = {u: findings for u, findings in results.items() if findings}
    if not serializable:
        return
    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
    rows = [
        (url, json.dumps([f.model_dump() for f in findings]), expires_at)
        for url, findings in serializable.items()
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO vibecheck_video_analysis_cache
                (video_url, frame_findings_payload, checked_at, expires_at)
            VALUES ($1, $2::jsonb, now(), $3)
            ON CONFLICT (video_url) DO UPDATE SET
                frame_findings_payload = EXCLUDED.frame_findings_payload,
                checked_at = now(),
                expires_at = EXCLUDED.expires_at
            """,
            rows,
        )
