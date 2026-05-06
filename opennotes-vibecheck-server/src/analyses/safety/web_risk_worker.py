from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import logfire

from src.analyses.safety.web_risk import check_urls
from src.config import Settings
from src.utterances.media_extraction import page_level_media


async def run_web_risk(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    source_url = getattr(payload, "source_url", None)
    utterances = list(getattr(payload, "utterances", []) or [])
    pool_urls: set[str] = set()
    if source_url:
        pool_urls.add(source_url)
    media = page_level_media(utterances)
    for key in ("urls", "images", "videos"):
        pool_urls.update(media.get(key, []))
    urls = sorted(pool_urls)
    if not urls:
        return {"findings": [], "urls_checked": 0}
    stats: dict[str, float] = {}
    with logfire.span(
        "vibecheck.section.web_risk",
        url_count=len(urls),
        cache_hit_rate=0.0,
    ) as span:
        async with httpx.AsyncClient() as hx:
            findings = await check_urls(
                urls,
                pool=pool,
                httpx_client=hx,
                ttl_hours=settings.WEB_RISK_CACHE_TTL_HOURS,
                stats=stats,
            )
        span.set_attribute("cache_hit_rate", stats.get("cache_hit_rate", 0.0))
    return {
        "findings": [
            f.model_dump() for f in findings.values() if f.threat_types
        ],
        "urls_checked": len(urls),
    }
