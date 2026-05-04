from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import html2text
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.analyses.safety.web_risk import WebRiskTransientError, check_urls
from src.auth.scrape_token import require_scrape_token
from src.cache.scrape_cache import canonical_cache_key
from src.config import Settings, get_settings
from src.jobs.enqueue import enqueue_job
from src.monitoring import get_logger
from src.routes.analyze import (
    _error_response,
    _get_db_pool,
    _host_of,
    _mark_job_failed_enqueue,
    limiter,
)
from src.utils.html_sanitize import strip_noise
from src.utils.url_security import InvalidURL

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["scrape"])

_MAX_HTML_BYTES = 10 * 1024 * 1024
_MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
_BROWSER_HTML_TIER = "browser_html"


class ScrapeSubmitRequest(BaseModel):
    url: str = Field(..., description="HTTP(S) source URL of the scraped page")
    html: str = Field(..., description="Raw HTML from the browser extension")
    markdown: str | None = Field(default=None)
    title: str | None = Field(default=None)
    description: str | None = Field(default=None)


class ScrapeSubmitResponse(BaseModel):
    job_id: UUID
    analyze_url: str
    created_at: datetime


def _rate_limit_value() -> str:
    return f"{get_settings().RATE_LIMIT_PER_IP_PER_HOUR}/hour"


def _byte_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _markdown_from_html(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_links = False
    return converter.handle(html)


def _analyze_url(settings: Settings, job_id: UUID) -> str:
    base = settings.VIBECHECK_WEB_URL.rstrip("/")
    return f"{base}/analyze?job={job_id}" if base else f"/analyze?job={job_id}"


async def _insert_failed_unsafe_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    message: str,
) -> tuple[UUID, datetime]:
    job_id = uuid4()
    created_at = await conn.fetchval(
        """
        INSERT INTO vibecheck_jobs (
            job_id, url, normalized_url, host, status, attempt_id,
            error_code, error_message, sections, cached, source_type,
            created_at, updated_at, finished_at
        )
        VALUES (
            $1, $2, $3, $4, 'failed', $5,
            'unsafe_url', $6, '{}'::jsonb, false, 'browser_html',
            now(), now(), now()
        )
        RETURNING created_at
        """,
        job_id,
        url,
        normalized_url,
        host,
        uuid4(),
        message,
    )
    assert isinstance(created_at, datetime)
    return job_id, created_at


async def _insert_browser_scrape_and_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    html: str,
    markdown: str,
    title: str | None,
) -> tuple[UUID, UUID, datetime]:
    job_id = uuid4()
    attempt_id = uuid4()

    # This intentionally does not use SupabaseScrapeCache.put()'s evict fence:
    # browser_html writes have no screenshot upload window, so the TASK-1488.18
    # race that _upsert_if_not_evicted protects is not present.
    await conn.execute(
        """
        INSERT INTO vibecheck_scrapes (
            normalized_url, tier, url, final_url, host, page_kind,
            page_title, markdown, html, job_id, attempt_id,
            scraped_at, expires_at, evicted_at
        )
        VALUES (
            $1, 'browser_html', $2, $2, $3, 'other',
            $4, $5, $6, $7, $8,
            now(), now() + INTERVAL '72 hours', NULL
        )
        """,
        normalized_url,
        url,
        host,
        title,
        markdown,
        html,
        job_id,
        attempt_id,
    )
    row = await conn.fetchrow(
        """
        INSERT INTO vibecheck_jobs (
            job_id, url, normalized_url, host, status, attempt_id, source_type
        )
        VALUES ($1, $2, $3, $4, 'pending', $5, 'browser_html')
        RETURNING job_id, created_at
        """,
        job_id,
        url,
        normalized_url,
        host,
        attempt_id,
    )
    assert row is not None
    return row["job_id"], attempt_id, row["created_at"]


@router.post(
    "/scrape",
    status_code=201,
    response_model=ScrapeSubmitResponse,
)
@limiter.limit(_rate_limit_value)
async def submit_scrape(  # noqa: PLR0911
    request: Request,
    body: ScrapeSubmitRequest,
    _: None = Depends(require_scrape_token),
) -> Any:
    settings = get_settings()
    if not body.url:
        return _error_response(400, "invalid_url", "url is required")
    if not body.html:
        return _error_response(400, "invalid_html", "html is required")
    if _byte_len(body.html) > _MAX_HTML_BYTES:
        return _error_response(413, "payload_too_large", "html exceeds 10MB limit")
    if body.markdown is not None and _byte_len(body.markdown) > _MAX_MARKDOWN_BYTES:
        return _error_response(413, "payload_too_large", "markdown exceeds 2MB limit")

    try:
        normalized_url = canonical_cache_key(body.url)
    except InvalidURL as exc:
        logger.info("POST /api/scrape rejected url: reason=%s", exc.reason)
        return _error_response(400, "invalid_url", f"url rejected: {exc.reason}")

    host = _host_of(normalized_url)
    pool = _get_db_pool(request)

    async with httpx.AsyncClient(timeout=10.0) as hx:
        try:
            gate_findings = await check_urls(
                [normalized_url],
                pool=pool,
                httpx_client=hx,
                ttl_hours=settings.WEB_RISK_CACHE_TTL_HOURS,
            )
        except WebRiskTransientError:
            return _error_response(
                503,
                "rate_limited",
                "web risk scan temporarily unavailable",
                headers={"Retry-After": "5"},
            )

    page_finding = gate_findings.get(normalized_url)
    if page_finding is not None and page_finding.threat_types:
        async with pool.acquire() as conn:
            job_id, created_at = await _insert_failed_unsafe_job(
                conn,
                url=body.url,
                normalized_url=normalized_url,
                host=host,
                message=f"page URL flagged by Web Risk: {', '.join(page_finding.threat_types)}",
            )
        return _error_response(400, "unsafe_url", "url flagged by Web Risk")

    sanitized_html = strip_noise(body.html) or ""
    markdown = body.markdown.strip() if body.markdown and body.markdown.strip() else None
    if markdown is None:
        markdown = _markdown_from_html(sanitized_html)
    if _byte_len(markdown) > _MAX_MARKDOWN_BYTES:
        return _error_response(413, "payload_too_large", "markdown exceeds 2MB limit")

    async with pool.acquire() as conn, conn.transaction():
        job_id, attempt_id, created_at = await _insert_browser_scrape_and_job(
            conn,
            url=body.url,
            normalized_url=normalized_url,
            host=host,
            html=sanitized_html,
            markdown=markdown,
            title=body.title,
        )

    try:
        await enqueue_job(job_id, attempt_id, settings)
    except Exception as exc:
        logger.warning("enqueue_job failed for browser scrape job %s: %s", job_id, exc)
        await _mark_job_failed_enqueue(pool, job_id)
        return _error_response(500, "internal", "enqueue failed")

    response = ScrapeSubmitResponse(
        job_id=job_id,
        analyze_url=_analyze_url(settings, job_id),
        created_at=created_at,
    )
    return JSONResponse(status_code=201, content=json.loads(response.model_dump_json()))
