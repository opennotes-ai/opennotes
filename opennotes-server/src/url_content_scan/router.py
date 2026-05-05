from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob
from src.cache.redis_client import redis_client
from src.config import settings
from src.database import get_db, get_session_maker
from src.services.firecrawl_client import FirecrawlClient, FirecrawlError
from src.url_content_scan.analyze_handler import AnalyzeSubmissionError, submit_url_scan
from src.url_content_scan.auth import get_url_scan_api_key
from src.url_content_scan.frame import archive_preview, frame_compat, lookup_screenshot
from src.url_content_scan.models import UrlScanState
from src.url_content_scan.normalize import canonical_cache_key
from src.url_content_scan.poll_handler import load_job_state
from src.url_content_scan.rate_limiter import RateLimitStatus, UrlScanRateLimiter
from src.url_content_scan.recent_analyses import RecentAnalysis, list_recent
from src.url_content_scan.retry_handler import prepare_section_retry
from src.url_content_scan.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    FrameCompatResponse,
    JobState,
    RetryResponse,
    ScreenshotResponse,
    SectionSlug,
    SidebarPayload,
)
from src.url_content_scan.scrape_cache import ScrapeCache
from src.url_content_scan.screenshot_store import ScreenshotStore
from src.users.models import APIKey
from src.utils.url_security import InvalidURL

router = APIRouter(prefix="/api/v1/url_scan", tags=["url_scan"])


def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    error_host: str | None = None,
) -> JSONResponse:
    content = {"error_code": error_code, "message": message}
    if error_host is not None:
        content["error_host"] = error_host
    return JSONResponse(status_code=status_code, content=content, headers=headers)


def _rate_limit_response(result: RateLimitStatus) -> JSONResponse:
    return _error_response(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        "rate limit exceeded",
        headers={"Retry-After": str(max(1, result.retry_after_seconds))},
    )


def _http_exception_response(exc: HTTPException) -> JSONResponse:
    error_code = "internal"
    message = str(exc.detail)
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        error_code = "not_found"
    elif exc.status_code == status.HTTP_400_BAD_REQUEST:
        error_code = "invalid_url"
    elif exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        error_code = "upstream_error"
    return _error_response(exc.status_code, error_code, message, headers=exc.headers)


def _parse_job_id(job_id: str | None) -> UUID | None:
    if not job_id:
        return None
    try:
        return UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job_id") from exc


def _get_rate_limiter(request: Request) -> UrlScanRateLimiter:
    injected = getattr(request.app.state, "url_scan_rate_limiter", None)
    if injected is not None:
        return injected
    return UrlScanRateLimiter(redis_client=getattr(redis_client, "client", None))


def _client_host(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


async def _check_submit_rate_limits(
    *,
    request: Request,
    api_key: APIKey,
    url: str,
) -> JSONResponse | None:
    limiter = _get_rate_limiter(request)
    api_key_limit = await limiter.check_api_key_limit(api_key)
    if not api_key_limit.allowed:
        return _rate_limit_response(api_key_limit)
    try:
        normalized_url = canonical_cache_key(url)
    except InvalidURL:
        return None
    ip_url_limit = await limiter.check_ip_url_limit(_client_host(request), normalized_url)
    if not ip_url_limit.allowed:
        return _rate_limit_response(ip_url_limit)
    return None


def get_scrape_cache(request: Request) -> ScrapeCache:
    injected = getattr(request.app.state, "url_scan_scrape_cache", None)
    if injected is not None:
        return injected
    redis = getattr(redis_client, "client", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="URL scan cache is not configured")
    return ScrapeCache(
        redis_client=redis,
        session_factory=get_session_maker(),
        screenshot_store=ScreenshotStore.from_settings(),
    )


def _get_optional_scrape_cache(request: Request) -> ScrapeCache | None:
    try:
        return get_scrape_cache(request)
    except HTTPException:
        return None


def get_firecrawl_client(request: Request) -> FirecrawlClient:
    injected = getattr(request.app.state, "url_scan_firecrawl_client", None)
    if injected is not None:
        return injected
    return FirecrawlClient(settings.FIRECRAWL_API_KEY, api_base=settings.FIRECRAWL_API_BASE)


def get_screenshot_store(request: Request) -> ScreenshotStore:
    injected = getattr(request.app.state, "url_scan_screenshot_store", None)
    if injected is not None:
        return injected
    return ScreenshotStore.from_settings()


class _RecentScreenshotSigner:
    def __init__(self, screenshot_store: ScreenshotStore) -> None:
        self._screenshot_store = screenshot_store

    async def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        if not storage_key:
            return None
        return await self._screenshot_store.sign_url(storage_key, ttl=timedelta(minutes=15))


async def _resolve_archive_url(
    db: AsyncSession,
    *,
    url: str | None,
    job_id: UUID | None,
) -> str | None:
    if url:
        return url
    if job_id is None:
        return None
    result = await db.execute(select(UrlScanState.source_url).where(UrlScanState.job_id == job_id))
    return result.scalar_one_or_none()


async def _job_exists(db: AsyncSession, job_id: UUID) -> bool:
    result = await db.execute(select(BatchJob.id).where(BatchJob.id == job_id))
    return result.scalar_one_or_none() is not None


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze(
    body: AnalyzeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(get_url_scan_api_key),
) -> AnalyzeResponse | JSONResponse:
    rate_limit_result = await _check_submit_rate_limits(
        request=request, api_key=api_key, url=body.url
    )
    if rate_limit_result is not None:
        return rate_limit_result
    try:
        return await submit_url_scan(db, request, body)
    except AnalyzeSubmissionError as exc:
        return _error_response(
            exc.status_code,
            exc.error_code.value,
            exc.message,
            headers=exc.headers,
        )


@router.post(
    "/embed/v1/start",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def embed_start(
    body: AnalyzeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(get_url_scan_api_key),
) -> AnalyzeResponse | JSONResponse:
    return await analyze(body=body, request=request, db=db, api_key=api_key)


@router.get("/jobs/{job_id}", response_model=JobState)
async def poll_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: APIKey = Depends(get_url_scan_api_key),
) -> JobState | JSONResponse:
    state = await load_job_state(db, job_id)
    if state is None:
        return _error_response(status.HTTP_404_NOT_FOUND, "not_found", "job not found")
    return state


@router.post(
    "/jobs/{job_id}/retry/{slug}",
    response_model=RetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_section(
    job_id: UUID,
    slug: SectionSlug,
    db: AsyncSession = Depends(get_db),
    _api_key: APIKey = Depends(get_url_scan_api_key),
) -> RetryResponse | JSONResponse:
    try:
        return await prepare_section_retry(db, job_id, slug)
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return _error_response(exc.status_code, "internal", str(exc.detail))


@router.get("/analyses/recent", response_model=list[RecentAnalysis])
async def recent_analyses(
    request: Request,
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _api_key: APIKey = Depends(get_url_scan_api_key),
) -> list[RecentAnalysis]:
    signer = getattr(request.app.state, "recent_signer", None)
    if signer is None:
        signer = _RecentScreenshotSigner(get_screenshot_store(request))
    return await list_recent(db, limit=limit, signer=signer)


@router.get("/frame-compat", response_model=FrameCompatResponse)
async def frame_compat_route(
    request: Request,
    url: str = Query(...),
    job_id: str | None = Query(None),
    _api_key: APIKey = Depends(get_url_scan_api_key),
) -> FrameCompatResponse | JSONResponse:
    try:
        _parse_job_id(job_id)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            result = await frame_compat(
                url,
                client=client,
                scrape_cache=_get_optional_scrape_cache(request),
            )
    except InvalidURL as exc:
        return _error_response(status.HTTP_400_BAD_REQUEST, "invalid_url", exc.reason)
    except HTTPException as exc:
        return _http_exception_response(exc)
    except httpx.HTTPError as exc:
        return _error_response(status.HTTP_502_BAD_GATEWAY, "upstream_error", str(exc))
    except Exception as exc:
        return _error_response(status.HTTP_502_BAD_GATEWAY, "upstream_error", str(exc))
    return FrameCompatResponse.model_validate(result.model_dump())


@router.get("/screenshot", response_model=ScreenshotResponse)
async def screenshot_route(
    request: Request,
    url: str = Query(...),
    _api_key: APIKey = Depends(get_url_scan_api_key),
) -> ScreenshotResponse | JSONResponse:
    try:
        result = await lookup_screenshot(
            url,
            scrape_cache=get_scrape_cache(request),
            screenshot_store=get_screenshot_store(request),
        )
    except InvalidURL as exc:
        return _error_response(status.HTTP_400_BAD_REQUEST, "invalid_url", exc.reason)
    except HTTPException as exc:
        return _http_exception_response(exc)
    except Exception as exc:
        return _error_response(status.HTTP_502_BAD_GATEWAY, "upstream_error", str(exc))
    if result is None:
        return _error_response(status.HTTP_404_NOT_FOUND, "not_found", "Screenshot unavailable")
    return ScreenshotResponse.model_validate(result)


@router.get(
    "/archive-preview",
    response_model=None,
    response_class=HTMLResponse,
    responses={
        200: {
            "description": "HTML archive preview",
            "content": {"text/html": {"schema": {"type": "string"}}},
        }
    },
)
async def archive_preview_route(  # noqa: PLR0911
    request: Request,
    url: str | None = Query(None),
    job_id: str | None = Query(None),
    generate: bool = Query(False),
    source_type: str = Query("url"),
    db: AsyncSession = Depends(get_db),
    _api_key: APIKey = Depends(get_url_scan_api_key),
) -> Response | JSONResponse:
    try:
        parsed_job_id = _parse_job_id(job_id)
        if source_type == "pdf":
            if parsed_job_id is None:
                return _error_response(
                    status.HTTP_400_BAD_REQUEST,
                    "invalid_url",
                    "job_id is required",
                )
            if not await _job_exists(db, parsed_job_id):
                return _error_response(
                    status.HTTP_404_NOT_FOUND,
                    "not_found",
                    "job not found",
                )
            return _error_response(
                status.HTTP_404_NOT_FOUND,
                "not_found",
                "Archive unavailable",
            )
        resolved_url = await _resolve_archive_url(db, url=url, job_id=parsed_job_id)
        if resolved_url is None:
            return _error_response(
                status.HTTP_400_BAD_REQUEST,
                "invalid_url",
                "URL must be an http(s) URL",
            )
        html = await archive_preview(
            resolved_url,
            scrape_cache=get_scrape_cache(request),
            scraper=get_firecrawl_client(request) if generate else None,
            generate=generate,
        )
    except InvalidURL as exc:
        return _error_response(status.HTTP_400_BAD_REQUEST, "invalid_url", exc.reason)
    except HTTPException as exc:
        return _http_exception_response(exc)
    except FirecrawlError as exc:
        return _error_response(status.HTTP_502_BAD_GATEWAY, "upstream_error", str(exc))
    except Exception as exc:
        return _error_response(status.HTTP_502_BAD_GATEWAY, "upstream_error", str(exc))
    if html is None:
        return _error_response(status.HTTP_404_NOT_FOUND, "not_found", "Archive unavailable")
    return Response(
        html,
        media_type="text/html; charset=utf-8",
        headers={
            "cache-control": "no-store, private",
            "content-security-policy": "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
            "x-content-type-options": "nosniff",
        },
    )


@router.get(
    "/_schema_anchor",
    response_model=JobState,
    summary="URL scan schema anchor",
    description="Always returns 410 Gone.",
    responses={410: {"description": "Always. Placeholder route for schema generation."}},
)
async def schema_anchor() -> JobState:
    raise HTTPException(status_code=410, detail="schema-anchor placeholder")


@router.get(
    "/_sidebar_schema_anchor",
    response_model=SidebarPayload,
    summary="URL scan sidebar schema anchor",
    description="Always returns 410 Gone.",
    responses={410: {"description": "Always. Placeholder route for schema generation."}},
)
async def sidebar_schema_anchor() -> SidebarPayload:
    raise HTTPException(status_code=410, detail="schema-anchor placeholder")
