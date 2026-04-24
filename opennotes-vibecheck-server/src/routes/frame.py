from __future__ import annotations

import asyncio
from inspect import isawaitable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from supabase import create_client

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.cache.screenshot_store import GCSScreenshotStore, InMemoryScreenshotStore, ScreenshotStore
from src.config import get_settings
from src.firecrawl_client import FirecrawlClient, ScrapeResult
from src.monitoring import get_logger
from src.utils.html_sanitize import strip_noise
from src.utils.url_security import InvalidURL, validate_public_http_url

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["frame"])

_HEAD_TIMEOUT_SECONDS = 5.0
_SCREENSHOT_TIMEOUT_SECONDS = 60.0
_SCREENSHOT_REQUEST_BUDGET_SECONDS = 90.0
_ARCHIVE_REQUEST_BUDGET_SECONDS = 8.0
_BLOCKING_XFO_VALUES = {"deny", "sameorigin"}
_PERMISSIVE_FRAME_ANCESTOR_TOKENS = {"*", "https:", "http:", "data:"}
_ARCHIVE_CSP = (
    "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; "
    "font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; "
    "frame-ancestors 'self'"
)

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
async def frame_compat(url: str = Query(...)) -> FrameCompatResponse:
    _validate_http_url(url)
    headers, has_archive = await asyncio.gather(_probe_target(url), _has_cached_archive(url))
    can_iframe, blocking_header, csp_frame_ancestors = _evaluate_headers(headers)
    return FrameCompatResponse(
        can_iframe=can_iframe,
        blocking_header=blocking_header,
        csp_frame_ancestors=csp_frame_ancestors,
        has_archive=has_archive,
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


async def _has_cached_archive(url: str) -> bool:
    try:
        cached = await get_scrape_cache().get(url)
    except Exception as exc:
        logger.info("archive cache lookup failed for %s: %s", url, exc)
        return False
    return bool(cached and cached.html)


async def _revalidate_archive_final_url(
    scrape: CachedScrape,
    *,
    original_url: str,
    scrape_cache: Any,
) -> None:
    final = scrape.metadata.source_url if scrape.metadata else None
    if not final:
        return
    try:
        _validate_http_url(final)
    except HTTPException:
        evict = getattr(scrape_cache, "evict", None)
        if callable(evict):
            try:
                result = evict(original_url)
                if isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning("archive cache evict failed for %s: %s", original_url, exc)
        raise


def _archive_response(html: str) -> Response:
    return Response(
        content=html,
        headers={
            "content-type": "text/html; charset=utf-8",
            "cache-control": "no-store, private",
            "content-security-policy": _ARCHIVE_CSP,
        },
    )


@router.get("/archive-preview")
async def archive_preview(
    url: str = Query(...),
    generate: bool = Query(False),
) -> Response:
    _validate_http_url(url)
    scrape_cache = get_scrape_cache()
    cached = await scrape_cache.get(url)
    if cached and cached.html:
        # TODO: If Firecrawl exposes a hosted archive URL in CachedScrape metadata,
        # return a redirect to that URL instead of serving cached sanitized HTML.
        await _revalidate_archive_final_url(
            cached, original_url=url, scrape_cache=scrape_cache
        )
        return _archive_response(cached.html)

    if not generate:
        raise HTTPException(status_code=404, detail="Archive unavailable")

    fc = get_firecrawl_client()
    try:
        fresh = await asyncio.wait_for(
            fc.scrape(url, formats=["html"], only_main_content=True),
            timeout=_ARCHIVE_REQUEST_BUDGET_SECONDS,
        )
        stored = await scrape_cache.put(url, fresh)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Archive unavailable")
    except Exception as exc:
        logger.warning("archive preview scrape failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Archive unavailable") from exc

    await _revalidate_archive_final_url(stored, original_url=url, scrape_cache=scrape_cache)
    html = strip_noise(stored.html) if stored.html else None
    if not html:
        raise HTTPException(status_code=502, detail="Archive unavailable")
    return _archive_response(html)


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


@router.get("/screenshot")
async def screenshot(url: str = Query(...)) -> dict[str, str]:
    _validate_http_url(url)
    fc = get_firecrawl_client()
    try:
        result = await asyncio.wait_for(
            fc.scrape(url, formats=["screenshot"]),
            timeout=_SCREENSHOT_REQUEST_BUDGET_SECONDS,
        )
    except Exception as exc:
        logger.warning("firecrawl scrape failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Screenshot service failed") from exc
    shot_url = _extract_screenshot_url(result)
    if not shot_url:
        raise HTTPException(status_code=502, detail="No screenshot produced")
    return {"screenshot_url": shot_url}
