from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from firecrawl import Firecrawl

from src.config import get_settings
from src.monitoring import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["frame"])

_HEAD_TIMEOUT_SECONDS = 5.0
_SCREENSHOT_TIMEOUT_SECONDS = 30.0
_BLOCKING_XFO_VALUES = {"deny", "sameorigin"}
_PERMISSIVE_FRAME_ANCESTOR_TOKENS = {"*", "https:", "http:", "data:"}


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL must be an http(s) URL")


def _frame_ancestors_blocks(csp_value: str) -> tuple[bool, str | None]:
    directives = [d.strip() for d in csp_value.split(";") if d.strip()]
    for directive in directives:
        parts = directive.split()
        if not parts or parts[0].lower() != "frame-ancestors":
            continue
        tokens = [t.strip().lower().strip("'\"") for t in parts[1:]]
        if not tokens or "none" in tokens:
            return True, f"content-security-policy: frame-ancestors {' '.join(tokens) or 'none'}"
        if any(tok in _PERMISSIVE_FRAME_ANCESTOR_TOKENS for tok in tokens):
            return False, None
        return True, f"content-security-policy: frame-ancestors {' '.join(tokens)}"
    return False, None


def _evaluate_headers(headers: httpx.Headers) -> tuple[bool, str | None]:
    xfo = headers.get("x-frame-options")
    if xfo:
        normalized = xfo.strip().lower()
        if normalized in _BLOCKING_XFO_VALUES:
            return False, f"x-frame-options: {xfo.strip()}"
    csp = headers.get("content-security-policy")
    if csp:
        blocks, reason = _frame_ancestors_blocks(csp)
        if blocks:
            return False, reason
    return True, None


async def _probe_target(url: str) -> httpx.Headers:
    async with httpx.AsyncClient(
        timeout=_HEAD_TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        try:
            response = await client.head(url)
        except httpx.HTTPError as exc:
            logger.info("frame-compat HEAD failed for %s: %s", url, exc)
            raise HTTPException(status_code=502, detail="Target URL unreachable") from exc
        if response.status_code == 405:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                logger.info("frame-compat GET fallback failed for %s: %s", url, exc)
                raise HTTPException(status_code=502, detail="Target URL unreachable") from exc
        return response.headers


@router.get("/frame-compat")
async def frame_compat(url: str = Query(...)) -> dict[str, Any]:
    _validate_http_url(url)
    headers = await _probe_target(url)
    can_iframe, blocking_header = _evaluate_headers(headers)
    return {"can_iframe": can_iframe, "blocking_header": blocking_header}


class _InlineFirecrawl:
    def __init__(self, api_key: str) -> None:
        self._inner = Firecrawl(api_key=api_key, timeout=_SCREENSHOT_TIMEOUT_SECONDS)

    def scrape(self, url: str, formats: list[str]) -> Any:
        return self._inner.scrape(url, formats=formats)  # pyright: ignore[reportArgumentType]


def get_firecrawl_client() -> Any:
    # TODO(TASK-1471.05): replace with shared src.firecrawl_client.FirecrawlClient
    # once BE-2 lands it. Minimal inline firecrawl-py call until then.
    settings = get_settings()
    return _InlineFirecrawl(api_key=settings.FIRECRAWL_API_KEY)


def _extract_screenshot_url(result: Any) -> str | None:
    direct = getattr(result, "screenshot", None)
    if isinstance(direct, str) and direct:
        return direct
    metadata = getattr(result, "metadata", None)
    if isinstance(metadata, dict):
        meta_shot = metadata.get("screenshot")
        if isinstance(meta_shot, str) and meta_shot:
            return meta_shot
    return None


@router.get("/screenshot")
async def screenshot(url: str = Query(...)) -> dict[str, str]:
    _validate_http_url(url)
    fc = get_firecrawl_client()
    try:
        result = fc.scrape(url, formats=["screenshot"])
    except Exception as exc:
        logger.warning("firecrawl scrape failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Screenshot service failed") from exc
    shot_url = _extract_screenshot_url(result)
    if not shot_url:
        raise HTTPException(status_code=502, detail="No screenshot produced")
    return {"screenshot_url": shot_url}
