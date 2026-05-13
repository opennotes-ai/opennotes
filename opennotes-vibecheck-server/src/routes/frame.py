from __future__ import annotations

import asyncio
import re
from inspect import isawaitable
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from supabase import create_client

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache, canonical_cache_key
from src.cache.screenshot_store import GCSScreenshotStore, InMemoryScreenshotStore, ScreenshotStore
from src.config import get_settings
from src.firecrawl_client import (
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
    ScrapeMetadata,
    ScrapeResult,
)
from src.jobs.pdf_storage import get_pdf_upload_store
from src.jobs.scrape_quality import ScrapeQuality, classify_scrape
from src.monitoring import get_logger
from src.utils.html_sanitize import extract_archive_main_content, strip_for_display
from src.utils.url_security import InvalidURL, validate_public_http_url
from src.utterances.annotate_html import annotate_utterances_in_html
from src.utterances.lookup import get_utterances_for_archive
from src.utterances.schema import Utterance

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["frame"])

_HEAD_TIMEOUT_SECONDS = 5.0
_SCREENSHOT_TIMEOUT_SECONDS = 60.0
_SCREENSHOT_REQUEST_BUDGET_SECONDS = 90.0
_ARCHIVE_REQUEST_BUDGET_SECONDS = 8.0
_BLOCKING_XFO_VALUES = {"deny", "sameorigin"}
_BROWSER_HTML_ARCHIVE_TIER = "browser_html"
_ARCHIVE_CACHE_TIERS = ("interact", "scrape")
_PERMISSIVE_FRAME_ANCESTOR_TOKENS = {"*", "https:", "http:", "data:"}
_ALLOWED_GCS_HOSTS = frozenset({
    "storage.googleapis.com",
    "storage.cloud.google.com",
})


def _is_gcs_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in ("http", "https")
            and parsed.hostname in _ALLOWED_GCS_HOSTS
            and parsed.port is None
        )
    except Exception:
        return False
_ARCHIVE_CSP = (
    "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; "
    "font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; "
    "frame-ancestors 'self'"
)
_ARCHIVE_DISPLAY_STYLES = (
    "<style>"
    "img{max-width:100%!important;height:auto!important}"
    "[data-platform-comments]{margin:2rem 0;padding-top:1rem;border-top:1px solid #d8dee4;"
    "font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5}"
    "[data-platform-comments] .opennotes-comments{list-style:none;margin:0;padding:0}"
    "[data-platform-comments] .opennotes-comments>li{margin:0 0 1rem;padding:0}"
    "[data-platform-comments] article{margin:.75rem 0;padding:.75rem;border:1px solid #d8dee4;"
    "border-radius:6px;background:#fff}"
    "[data-platform-comments] article article{margin-left:1.25rem;border-left:3px solid #8c959f}"
    "[data-platform-comments] header{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;"
    "margin-bottom:.5rem;color:#57606a;font-size:.875rem}"
    "[data-platform-comments] .opennotes-comment__author{font-weight:600;color:#24292f}"
    "[data-platform-comments] time{font-variant-numeric:tabular-nums}"
    "[data-platform-comments] .opennotes-comment__parent{font-size:.8125rem}"
    "[data-platform-comments] .opennotes-comment__body p{margin:.5rem 0}"
    "[data-platform-comments] .opennotes-comment__body>:first-child{margin-top:0}"
    "[data-platform-comments] .opennotes-comment__body>:last-child{margin-bottom:0}"
    "[data-platform-comments] article:target{outline:3px solid #0969da;outline-offset:2px}"
    "</style>"
)
_DOCTYPE_RE = re.compile(r"^(<!doctype[^>]*>)", re.IGNORECASE | re.DOTALL)

_SELECT_PDF_ARCHIVE_SQL = """
SELECT a.html, j.normalized_url AS gcs_key
FROM vibecheck_jobs j
JOIN vibecheck_pdf_archives a ON a.job_id = j.job_id
WHERE j.job_id = $1
  AND j.source_type = 'pdf'
  AND a.expires_at > now()
"""

_SELECT_PDF_JOB_SQL = """
SELECT j.normalized_url AS gcs_key
FROM vibecheck_jobs j
JOIN vibecheck_pdf_archives a ON a.job_id = j.job_id
WHERE j.job_id = $1
  AND j.source_type = 'pdf'
  AND a.expires_at > now()
"""

_SELECT_BROWSER_HTML_ARCHIVE_SQL = """
SELECT
    s.url,
    s.final_url,
    s.page_title,
    s.markdown,
    s.html,
    s.screenshot_storage_key
FROM vibecheck_jobs j
JOIN vibecheck_scrapes s ON s.job_id = j.job_id
WHERE j.job_id = $1
  AND j.source_type = 'browser_html'
  AND j.normalized_url = $2
  AND s.tier = 'browser_html'
  AND s.normalized_url = $2
  AND s.html IS NOT NULL
  AND s.expires_at > now()
  AND s.evicted_at IS NULL
"""

_SELECT_BROWSER_HTML_SCREENSHOT_SQL = """
SELECT s.screenshot_storage_key
FROM vibecheck_jobs j
JOIN vibecheck_scrapes s ON s.job_id = j.job_id
WHERE j.job_id = $1
  AND j.source_type = 'browser_html'
  AND j.normalized_url = $2
  AND s.tier = 'browser_html'
  AND s.normalized_url = $2
  AND s.screenshot_storage_key IS NOT NULL
  AND s.expires_at > now()
  AND s.evicted_at IS NULL
LIMIT 1
"""

_SELECT_TIER_SCREENSHOT_SQL = """
SELECT screenshot_storage_key
FROM vibecheck_scrapes
WHERE normalized_url = $1
  AND tier = $2
  AND screenshot_storage_key IS NOT NULL
  AND expires_at > now()
  AND evicted_at IS NULL
ORDER BY scraped_at DESC
LIMIT 1
"""

# Map machine-readable `InvalidURL.reason` slugs back to the human-readable
# 400-detail strings the frame routes returned before the SSRF refactor
# (TASK-1473.11). Frontend clients assert on these exact strings; changing
# them would silently break callers. Any new reason added to
# `src.utils.url_security` must be added here too — the fallback in
# `_validate_http_url` keeps the route from raising 500 if that slips, but
# clients pinning the older copy would still drift.
_REASON_TO_HUMAN_DETAIL: dict[str, str] = {
    "scheme_not_allowed": "URL must be an http(s) URL",
    "missing_host": "URL must include a host",
    "invalid_host": "URL host is invalid",
    "host_blocked": "URL host is not allowed",
    "private_ip": "URL points to a private network address",
    "resolved_private_ip": "URL points to a private network address",
    "unresolvable_host": "URL host could not be resolved",
}


class FrameCompatResponse(BaseModel):
    can_iframe: bool
    blocking_header: str | None
    csp_frame_ancestors: str | None = None
    has_archive: bool = False
    archive_render_mode: Literal["html_full_page", "html_extracted", "markdown", "text"] | None = None


class ScreenshotResponse(BaseModel):
    screenshot_url: str


class ScreenshotErrorResponse(BaseModel):
    detail: str
    reason: str


def _validate_http_url(url: str) -> None:
    """Delegate SSRF validation to the shared guard and raise HTTP 400 on failure.

    Kept as a thin wrapper so the three call sites in this module (both routes
    plus the redirect-follower) retain their original shape — the guard itself
    lives in `src.utils.url_security` and is reused by the async analyze
    pipeline (TASK-1473.11/.12).

    The 400 `detail` body preserves the prior human-readable strings (mapped
    from `InvalidURL.reason`) so frontend clients pinning copy like
    `"URL must be an http(s) URL"` keep working across the SSRF refactor.
    """
    try:
        validate_public_http_url(url)
    except InvalidURL as exc:
        detail = _REASON_TO_HUMAN_DETAIL.get(exc.reason, "URL is not allowed")
        raise HTTPException(status_code=400, detail=detail) from exc


def _frame_ancestors_blocks(csp_value: str) -> tuple[bool, str | None, str | None]:
    directives = [d.strip() for d in csp_value.split(";") if d.strip()]
    for directive in directives:
        parts = directive.split()
        if not parts or parts[0].lower() != "frame-ancestors":
            continue
        frame_ancestors = " ".join(parts)
        tokens = [t.strip().lower().strip("'\"") for t in parts[1:]]
        if not tokens or "none" in tokens:
            return (
                True,
                f"content-security-policy: frame-ancestors {' '.join(tokens) or 'none'}",
                frame_ancestors,
            )
        if any(tok in _PERMISSIVE_FRAME_ANCESTOR_TOKENS for tok in tokens):
            return False, None, frame_ancestors
        return True, f"content-security-policy: frame-ancestors {' '.join(tokens)}", frame_ancestors
    return False, None, None


def _evaluate_headers(headers: httpx.Headers) -> tuple[bool, str | None, str | None]:
    csp_frame_ancestors: str | None = None
    csp = headers.get("content-security-policy")
    if csp:
        blocks, reason, csp_frame_ancestors = _frame_ancestors_blocks(csp)
        if blocks:
            return False, reason, csp_frame_ancestors

    xfo = headers.get("x-frame-options")
    if xfo:
        normalized = xfo.strip().lower()
        if normalized in _BLOCKING_XFO_VALUES:
            return False, f"x-frame-options: {xfo.strip()}", csp_frame_ancestors
    return True, None, csp_frame_ancestors


async def _probe_target(url: str) -> httpx.Headers:
    # SSRF defense: do NOT auto-follow redirects. Re-validate each redirect hop
    # against the same allowlist so a 3xx can't smuggle us to a private IP.
    async with httpx.AsyncClient(timeout=_HEAD_TIMEOUT_SECONDS, follow_redirects=False) as client:
        try:
            response = await _request_with_validated_redirects(client, "HEAD", url)
        except httpx.HTTPError as exc:
            logger.info("frame-compat HEAD failed for %s: %s", url, exc)
            raise HTTPException(status_code=502, detail="Target URL unreachable") from exc
        if response.status_code == 405:
            try:
                response = await _request_with_validated_redirects(client, "GET", url)
            except httpx.HTTPError as exc:
                logger.info("frame-compat GET fallback failed for %s: %s", url, exc)
                raise HTTPException(status_code=502, detail="Target URL unreachable") from exc
        return response.headers


async def _request_with_validated_redirects(
    client: httpx.AsyncClient, method: str, url: str, *, max_redirects: int = 5
) -> httpx.Response:
    current_url = url
    for _ in range(max_redirects + 1):
        # Re-validate at every request to make the SSRF guard obvious to
        # dataflow analysis — on iteration 0 this is redundant (caller validated)
        # but on later iterations it's the only check between an attacker-chosen
        # Location header and client.request().
        _validate_http_url(current_url)
        response = await client.request(method, current_url)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current_url = str(httpx.URL(current_url).join(location))
    raise HTTPException(status_code=502, detail="Too many redirects")


@router.get("/frame-compat", response_model=FrameCompatResponse)
async def frame_compat(
    request: Request,
    url: str = Query(...),
    job_id: str | None = Query(None),
) -> FrameCompatResponse:
    _validate_http_url(url)
    parsed_job_id = _parse_archive_job_id(job_id)
    headers, (has_archive, archive_render_mode) = await asyncio.gather(
        _probe_target(url),
        _has_cached_archive(url, request=request, job_id=parsed_job_id),
    )
    can_iframe, blocking_header, csp_frame_ancestors = _evaluate_headers(headers)
    return FrameCompatResponse(
        can_iframe=can_iframe,
        blocking_header=blocking_header,
        csp_frame_ancestors=csp_frame_ancestors,
        has_archive=has_archive,
        archive_render_mode=archive_render_mode,
    )


def get_firecrawl_client() -> FirecrawlClient:
    settings = get_settings()
    return FirecrawlClient(
        api_key=settings.FIRECRAWL_API_KEY,
        timeout=_SCREENSHOT_TIMEOUT_SECONDS,
    )


def get_scrape_cache() -> SupabaseScrapeCache:
    settings = get_settings()
    key = (
        settings.VIBECHECK_SUPABASE_SERVICE_ROLE_KEY
        or settings.VIBECHECK_SUPABASE_ANON_KEY
    )
    if not settings.VIBECHECK_SUPABASE_URL or not key:
        raise RuntimeError("scrape cache is not configured")
    client = create_client(settings.VIBECHECK_SUPABASE_URL, key)
    store: ScreenshotStore
    if settings.VIBECHECK_GCS_SCREENSHOT_BUCKET:
        store = GCSScreenshotStore(settings.VIBECHECK_GCS_SCREENSHOT_BUCKET)
    else:
        store = InMemoryScreenshotStore()
    return SupabaseScrapeCache(client, store, ttl_hours=settings.CACHE_TTL_HOURS)


async def _has_cached_archive(
    url: str, *, request: Request | None = None, job_id: UUID | None = None
) -> tuple[bool, Literal["html_full_page", "html_extracted", "markdown", "text"] | None]:
    try:
        scrape_cache = get_scrape_cache()
    except Exception as exc:
        logger.info("archive cache lookup failed for %s: %s", url, exc)
        return False, None

    cached, tier = await _get_cached_archive(
        url, scrape_cache, request=request, job_id=job_id, require_usable=True
    )
    if not cached:
        return False, None
    if cached.html:
        render_mode = "html_full_page" if tier == _BROWSER_HTML_ARCHIVE_TIER else "html_extracted"
        return True, render_mode
    # NOTE: markdown and text modes are reserved for future use.
    # _get_cached_archive only returns entries with cached.html today,
    # making these branches currently unreachable.
    if cached.markdown:
        return True, "markdown"
    return True, "text"


async def _get_cached_archive(
    url: str,
    scrape_cache: SupabaseScrapeCache,
    *,
    request: Request | None = None,
    job_id: UUID | None = None,
    require_usable: bool = False,
) -> tuple[CachedScrape | None, str | None]:
    try:
        if request is not None and job_id is not None:
            cached = await _get_browser_html_archive(request, job_id, requested_url=url)
            if (
                cached
                and cached.html
                and (not require_usable or classify_scrape(cached) is ScrapeQuality.OK)
            ):
                return cached, _BROWSER_HTML_ARCHIVE_TIER
        for tier in _ARCHIVE_CACHE_TIERS:
            cached = await scrape_cache.get(url, tier=tier)
            if cached and cached.html:
                if require_usable and classify_scrape(cached) is not ScrapeQuality.OK:
                    continue
                return cached, tier
        return None, None
    except Exception as exc:
        logger.info("archive cache lookup failed for %s: %s", url, exc)
        return None, None


async def _get_browser_html_archive(
    request: Request, job_id: UUID, *, requested_url: str
) -> CachedScrape | None:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        logger.info("browser_html archive lookup skipped for %s: database unavailable", job_id)
        return None

    normalized_url = canonical_cache_key(requested_url)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_BROWSER_HTML_ARCHIVE_SQL, job_id, normalized_url)
    except Exception as exc:
        logger.info("browser_html archive lookup failed for %s: %s", job_id, exc)
        return None
    if row is None:
        return None
    return CachedScrape(
        markdown=row["markdown"] or "",
        html=row["html"],
        raw_html=None,
        screenshot=None,
        links=None,
        metadata=ScrapeMetadata(
            title=row["page_title"],
            source_url=row["final_url"] or row["url"],
        ),
        warning=None,
        storage_key=row["screenshot_storage_key"],
    )


async def _lookup_stored_screenshot_key(
    request: Request,
    *,
    url: str,
    job_id: UUID | None,
) -> str | None:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        logger.info("stored screenshot lookup skipped for %s: database unavailable", url)
        return None

    normalized_url = canonical_cache_key(url)
    try:
        async with pool.acquire() as conn:
            if job_id is not None:
                key = await conn.fetchval(
                    _SELECT_BROWSER_HTML_SCREENSHOT_SQL, job_id, normalized_url
                )
                if isinstance(key, str) and key:
                    return key
            for tier in _ARCHIVE_CACHE_TIERS:
                key = await conn.fetchval(
                    _SELECT_TIER_SCREENSHOT_SQL, normalized_url, tier
                )
                if isinstance(key, str) and key:
                    return key
    except Exception as exc:
        logger.info("stored screenshot lookup failed for %s: %s", url, exc)
        return None
    return None


async def _revalidate_archive_final_url(
    scrape: CachedScrape,
    *,
    original_url: str,
    scrape_cache: Any,
    tier: str = "scrape",
) -> None:
    final = scrape.metadata.source_url if scrape.metadata else None
    if not final:
        return
    try:
        _validate_http_url(final)
    except HTTPException:
        evict = getattr(scrape_cache, "evict", None)
        if callable(evict) and tier != _BROWSER_HTML_ARCHIVE_TIER:
            try:
                result = evict(original_url, tier=tier)
                if isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning("archive cache evict failed for %s: %s", original_url, exc)
        raise


def _archive_display_html(
    cached_html: str | None,
    cached_markdown: str | None,
    *,
    utterances: list[Utterance] | None = None,
) -> str | None:
    """Pick the archive iframe body for `cached_html`/`cached_markdown`.

    TASK-1577.02 prefers main-content extraction so SPA-rendered pages
    surface the post within the visible iframe viewport. Falls back to
    the surgical `strip_for_display` so non-SPA pages keep working.

    Codex P1.2: when the job has utterances, we prefer the extracted
    version only when it preserves every utterance text — otherwise the
    per-utterance highlights would silently disappear. Falling through
    to `strip_for_display` is safe because that path keeps the full
    document text.
    """
    extracted = extract_archive_main_content(cached_html, cached_markdown)
    stripped = strip_for_display(cached_html) if cached_html else None

    if extracted and (
        not utterances or _extracted_preserves_utterances(extracted, utterances)
    ):
        return extracted
    if stripped:
        return stripped
    return extracted


def _archive_response(html: str) -> Response:
    m = _DOCTYPE_RE.match(html)
    content = (
        m.group(1) + _ARCHIVE_DISPLAY_STYLES + html[m.end() :]
        if m
        else _ARCHIVE_DISPLAY_STYLES + html
    )
    return Response(
        content=content,
        headers={
            "content-type": "text/html; charset=utf-8",
            "cache-control": "no-store, private",
            "content-security-policy": _ARCHIVE_CSP,
        },
    )


def _parse_archive_job_id(job_id: str | None) -> UUID | None:
    if job_id in (None, ""):
        return None
    try:
        return UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job_id") from exc


def _get_db_pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return pool


async def _get_pdf_archive(pool: Any, job_id: UUID) -> tuple[str, str] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_PDF_ARCHIVE_SQL, job_id)
    if row is None:
        return None
    html = row["html"]
    gcs_key = row["gcs_key"]
    if not isinstance(html, str) or not isinstance(gcs_key, str):
        return None
    return html, gcs_key


async def _get_pdf_gcs_key(pool: Any, job_id: UUID) -> str | None:
    async with pool.acquire() as conn:
        gcs_key = await conn.fetchval(_SELECT_PDF_JOB_SQL, job_id)
    return gcs_key if isinstance(gcs_key, str) else None


async def _fetch_archive_utterances(
    *,
    request: Request,
    job_id: UUID | None,
    requested_url: str,
) -> list[Utterance]:
    if job_id is None:
        return []
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        logger.warning("archive utterance annotation skipped: database pool not initialized")
        return []
    try:
        return await get_utterances_for_archive(pool, job_id, requested_url)
    except Exception as exc:
        logger.warning("archive utterance lookup failed for job %s: %s", job_id, exc)
        return []


def _extracted_preserves_utterances(
    extracted_html: str,
    utterances: list[Utterance],
) -> bool:
    """Return True iff every utterance text appears in `extracted_html`.

    Codex P1.2: trafilatura can drop comment/forum blocks that the analyze
    pipeline marked as utterances. When that happens the archive iframe
    shows main content but the per-utterance highlights silently disappear.
    Caller compares this against a strip_for_display fallback that tends
    to preserve all original text and picks whichever surfaces more
    utterances.
    """
    if not utterances:
        return True
    haystack = extracted_html.lower()
    for utterance in utterances:
        text = getattr(utterance, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        if text.strip().lower() not in haystack:
            return False
    return True


async def _render_archive_response(
    cached_html: str | None,
    cached_markdown: str | None,
    *,
    request: Request,
    job_id: UUID | None,
    requested_url: str,
) -> Response:
    """Build the archive iframe response for the supplied scrape body.

    Centralizes the cached and fresh-scrape paths so archive_preview
    stays under the cyclomatic-complexity budget. Fetches utterances,
    picks extracted vs stripped, annotates, wraps with CSP + styles.
    """
    utterances = await _fetch_archive_utterances(
        request=request, job_id=job_id, requested_url=requested_url
    )
    display_html = _archive_display_html(
        cached_html, cached_markdown, utterances=utterances
    )
    if not display_html:
        raise HTTPException(status_code=502, detail="Archive unavailable")
    if utterances:
        display_html = annotate_utterances_in_html(display_html, utterances)
    return _archive_response(display_html)


async def _annotate_archive_html(
    html: str,
    *,
    request: Request,
    job_id: UUID | None,
    requested_url: str,
) -> str:
    utterances = await _fetch_archive_utterances(
        request=request, job_id=job_id, requested_url=requested_url
    )
    if not utterances:
        return html
    return annotate_utterances_in_html(html, utterances)


@router.get("/archive-preview")
async def archive_preview(
    request: Request,
    url: str | None = Query(None),
    job_id: str | None = Query(None),
    generate: bool = Query(False),
    source_type: str = Query("url"),
    content_format: str | None = Query(None, alias="format"),
) -> Response:
    parsed_job_id = _parse_archive_job_id(job_id)
    if source_type == "pdf":
        if parsed_job_id is None:
            raise HTTPException(status_code=400, detail="job_id is required")
        pdf_archive = await _get_pdf_archive(_get_db_pool(request), parsed_job_id)
        if pdf_archive is None:
            raise HTTPException(status_code=404, detail="Archive unavailable")
        html, gcs_key = pdf_archive
        html = await _annotate_archive_html(
            html,
            request=request,
            job_id=parsed_job_id,
            requested_url=gcs_key,
        )
        return _archive_response(html)

    if url is None:
        raise HTTPException(status_code=400, detail="URL must be an http(s) URL")
    _validate_http_url(url)
    scrape_cache = get_scrape_cache()
    cached, cached_tier = await _get_cached_archive(
        url,
        scrape_cache,
        request=request,
        job_id=parsed_job_id,
        require_usable=True,
    )
    if cached and cached.html:
        # TODO: If Firecrawl exposes a hosted archive URL in CachedScrape metadata,
        # return a redirect to that URL instead of serving cached sanitized HTML.
        await _revalidate_archive_final_url(
            cached, original_url=url, scrape_cache=scrape_cache, tier=cached_tier or "scrape"
        )
        if content_format == "text":
            raw = cached.markdown or cached.html or ""
            return Response(
                content=raw,
                headers={
                    "content-type": "text/plain; charset=utf-8",
                    "cache-control": "no-store, private",
                    "x-content-type-options": "nosniff",
                },
            )
        return await _render_archive_response(
            cached.html,
            cached.markdown,
            request=request,
            job_id=parsed_job_id,
            requested_url=url,
        )

    if not generate:
        raise HTTPException(status_code=404, detail="Archive unavailable")

    fc = get_firecrawl_client()
    try:
        # TASK-1577.02: request markdown alongside html so the archive
        # display extractor's markdown fallback (`extract_archive_main_content`)
        # can fire when trafilatura under-extracts on a fresh scrape too.
        fresh = await asyncio.wait_for(
            fc.scrape(url, formats=["html", "markdown"], only_main_content=True),
            timeout=_ARCHIVE_REQUEST_BUDGET_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Archive unavailable")
    except Exception as exc:
        logger.warning("archive preview scrape failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Archive unavailable") from exc

    if classify_scrape(fresh) is not ScrapeQuality.OK:
        raise HTTPException(status_code=502, detail="Archive unavailable")

    try:
        stored = await scrape_cache.put(url, fresh, tier="scrape")
    except Exception as exc:
        logger.warning("archive preview cache write failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Archive unavailable") from exc

    await _revalidate_archive_final_url(stored, original_url=url, scrape_cache=scrape_cache)
    return await _render_archive_response(
        stored.html,
        stored.markdown,
        request=request,
        job_id=parsed_job_id,
        requested_url=url,
    )


@router.get("/pdf-read")
async def pdf_read(request: Request, job_id: str = Query(...)) -> RedirectResponse:
    parsed_job_id = _parse_archive_job_id(job_id)
    if parsed_job_id is None:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    gcs_key = await _get_pdf_gcs_key(_get_db_pool(request), parsed_job_id)
    if gcs_key is None:
        raise HTTPException(status_code=404, detail="PDF unavailable")

    settings = get_settings()
    if not settings.VIBECHECK_PDF_UPLOAD_BUCKET:
        raise HTTPException(status_code=503, detail="PDF storage is not configured")

    signed_url = get_pdf_upload_store(settings.VIBECHECK_PDF_UPLOAD_BUCKET).signed_read_url(
        gcs_key
    )
    if not signed_url:
        raise HTTPException(status_code=502, detail="PDF unavailable")
    if not _is_gcs_url(signed_url):
        logger.warning("pdf_read: signed URL has unexpected domain, refusing redirect")
        raise HTTPException(status_code=502, detail="PDF unavailable")
    return RedirectResponse(
        signed_url,
        status_code=302,
        headers={
            "cache-control": "no-store, private",
            "referrer-policy": "no-referrer",
        },
    )


def _extract_screenshot_url(result: ScrapeResult | Any) -> str | None:
    direct = getattr(result, "screenshot", None)
    if isinstance(direct, str) and direct:
        return direct
    # Defensive fallback: some Firecrawl responses nest the screenshot URL in
    # `metadata.screenshot` (extra field — ScrapeMetadata has extra='allow').
    metadata = getattr(result, "metadata", None)
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        meta_shot = metadata.get("screenshot")
    else:
        meta_shot = getattr(metadata, "screenshot", None)
        if meta_shot is None:
            extras = getattr(metadata, "model_extra", None) or {}
            meta_shot = extras.get("screenshot")
    if isinstance(meta_shot, str) and meta_shot:
        return meta_shot
    return None


def _screenshot_404(detail: str, reason: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": detail, "reason": reason})


@router.get(
    "/screenshot",
    response_model=ScreenshotResponse,
    responses={404: {"model": ScreenshotErrorResponse}},
)
async def screenshot(
    request: Request,
    url: str = Query(...),
    job_id: str | None = Query(None),
) -> dict[str, str] | JSONResponse:
    _validate_http_url(url)
    parsed_job_id = _parse_archive_job_id(job_id)
    stored_key = await _lookup_stored_screenshot_key(
        request,
        url=url,
        job_id=parsed_job_id,
    )
    if stored_key:
        try:
            signed_url = get_scrape_cache().sign_screenshot_key(stored_key)
        except Exception as exc:
            logger.info("stored screenshot signing failed for %s: %s", url, exc)
        else:
            if signed_url:
                return {"screenshot_url": signed_url}

    fc = get_firecrawl_client()
    try:
        result = await asyncio.wait_for(
            fc.scrape(url, formats=["screenshot"]),
            timeout=_SCREENSHOT_REQUEST_BUDGET_SECONDS,
        )
    except FirecrawlBlocked as exc:
        logger.info("firecrawl refused screenshot for %s: %s", url, exc)
        return _screenshot_404("Site not supported", "unsupported_site")
    except (FirecrawlError, httpx.TransportError, TimeoutError) as exc:
        logger.warning("firecrawl scrape failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Screenshot service failed") from exc
    shot_url = _extract_screenshot_url(result)
    if not shot_url:
        return _screenshot_404("No screenshot available", "no_screenshot")
    return {"screenshot_url": shot_url}
