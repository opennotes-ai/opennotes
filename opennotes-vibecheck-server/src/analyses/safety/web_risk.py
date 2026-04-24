from __future__ import annotations

import asyncio

import asyncpg
import httpx

from src.analyses.safety._schemas import WebRiskFinding
from src.cache.web_risk_cache import fetch_cached, upsert_cached
from src.monitoring import external_api_span
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token

WEB_RISK_URL = "https://webrisk.googleapis.com/v1/uris:search"
THREAT_TYPES = (
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
)


class WebRiskTransientError(Exception):
    """Raised on auth/5xx/429/network — slot worker catches and fails retryable."""


async def check_urls(
    urls: list[str],
    *,
    pool: asyncpg.Pool,
    httpx_client: httpx.AsyncClient,
    ttl_hours: int = 6,
    stats: dict[str, float] | None = None,
) -> dict[str, WebRiskFinding]:
    if not urls:
        return {}
    cached = await fetch_cached(pool, urls)
    missing = [u for u in urls if u not in cached]
    if stats is not None:
        stats["cache_hit_rate"] = len(cached) / len(urls)
        stats["cache_hit_count"] = float(len(cached))
    if not missing:
        return cached
    token = get_access_token(CLOUD_PLATFORM_SCOPE)
    if not token:
        raise WebRiskTransientError("ADC token unavailable")
    sem = asyncio.Semaphore(8)

    async def one(url: str) -> tuple[str, WebRiskFinding]:
        async with sem:
            params: dict[str, str | list[str]] = {
                "uri": url,
                "threatTypes": list(THREAT_TYPES),
            }
            with external_api_span("webrisk", "uris.search") as obs:
                try:
                    r = await httpx_client.get(
                        WEB_RISK_URL,
                        params=params,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10.0,
                    )
                except httpx.HTTPError as exc:
                    obs.set_error_category("network")
                    raise WebRiskTransientError("web-risk network") from exc
                obs.set_response_status(r.status_code)
                if r.status_code == 429:
                    obs.set_error_category("rate_limited")
                    raise WebRiskTransientError(f"web-risk {r.status_code}")
                if r.status_code >= 500:
                    obs.set_error_category("upstream")
                    raise WebRiskTransientError(f"web-risk {r.status_code}")
                r.raise_for_status()
                payload = r.json()
                threat = (payload.get("threat") or {}).get("threatTypes") or []
                obs.add_flagged(1 if threat else 0)
                return url, WebRiskFinding(url=url, threat_types=list(threat))

    results = await asyncio.gather(*(one(u) for u in missing))
    findings = dict(results)
    await upsert_cached(pool, findings, ttl_hours=ttl_hours)
    return {**cached, **findings}
