from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Literal, Protocol

from httpx import URL
from pydantic import BaseModel

from src.services.firecrawl_client import ScrapeResult
from src.url_content_scan.html_sanitize import (
    enrich_display_with_raw_styles,
    extract_archive_main_content,
    strip_for_display,
)
from src.url_content_scan.scrape_quality import ScrapeQuality, classify_scrape
from src.url_content_scan.utterances.annotate_html import annotate_utterances_in_html
from src.url_content_scan.utterances.schema import Utterance
from src.utils.url_security import InvalidURL, validate_public_http_url

_HEAD_FALLBACK_STATUS = 405
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_BLOCKING_XFO_VALUES = frozenset({"deny", "sameorigin"})
_PERMISSIVE_FRAME_ANCESTOR_TOKENS = frozenset({"*", "https:", "http:", "data:"})
_SCREENSHOT_URL_TTL = timedelta(minutes=15)
_ARCHIVE_CACHE_TIERS: tuple[str, ...] = ("browser_html", "interact", "scrape")
_BROWSER_HTML_ARCHIVE_TIER = "browser_html"

_ARCHIVE_CSP = (
    "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; "
    "font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; "
    "frame-ancestors 'self'"
)
_ARCHIVE_DISPLAY_STYLES = "<style>img{max-width:100%!important;height:auto!important}</style>"
_DOCTYPE_RE = re.compile(r"^(<!doctype[^>]*>)", re.IGNORECASE | re.DOTALL)


class ResponseLike(Protocol):
    status_code: int
    headers: Any


class RequestClientLike(Protocol):
    async def request(self, method: str, url: str) -> ResponseLike: ...


class ScrapeCacheLike(Protocol):
    async def get(self, url: str, *, tier: str = "scrape") -> Any: ...
    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        screenshot_bytes: bytes | None = None,
        *,
        tier: str = "scrape",
    ) -> Any: ...
    async def evict(self, url: str, *, tier: str = "scrape") -> None: ...


class ScraperLike(Protocol):
    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult: ...


class ScreenshotStoreLike(Protocol):
    async def sign_url(self, storage_key: str, *, ttl: timedelta) -> str | None: ...


class FrameCompatResult(BaseModel):
    can_iframe: bool
    blocking_header: str | None
    csp_frame_ancestors: str | None = None
    has_archive: bool = False
    archive_render_mode: Literal["html_full_page", "html_extracted", "markdown", "text"] | None = (
        None
    )


def _header_map(headers: Any) -> dict[str, str]:
    if hasattr(headers, "multi_items"):
        items = headers.multi_items()
    elif hasattr(headers, "items"):
        items = headers.items()
    else:
        items = []
    out: dict[str, str] = {}
    for key, value in items:
        out[str(key).lower()] = str(value)
    return out


def _frame_ancestors_blocks(csp_value: str) -> tuple[bool, str | None, str | None]:
    directives = [directive.strip() for directive in csp_value.split(";") if directive.strip()]
    for directive in directives:
        parts = directive.split()
        if not parts or parts[0].lower() != "frame-ancestors":
            continue
        frame_ancestors = " ".join(parts)
        tokens = [token.strip().lower().strip("'\"") for token in parts[1:]]
        if not tokens or "none" in tokens:
            return True, "content-security-policy: frame-ancestors none", frame_ancestors
        if any(token in _PERMISSIVE_FRAME_ANCESTOR_TOKENS for token in tokens):
            return False, None, frame_ancestors
        return (
            True,
            f"content-security-policy: frame-ancestors {' '.join(tokens)}",
            frame_ancestors,
        )
    return False, None, None


def _evaluate_headers(headers: Any) -> tuple[bool, str | None, str | None]:
    header_map = _header_map(headers)
    csp_frame_ancestors: str | None = None
    csp = header_map.get("content-security-policy")
    if csp:
        blocks, blocking_header, csp_frame_ancestors = _frame_ancestors_blocks(csp)
        if blocks:
            return False, blocking_header, csp_frame_ancestors

    xfo = header_map.get("x-frame-options")
    if xfo:
        normalized = xfo.strip().lower()
        if normalized in _BLOCKING_XFO_VALUES:
            return False, f"x-frame-options: {xfo.strip()}", csp_frame_ancestors
    return True, None, csp_frame_ancestors


async def _request_with_validated_redirects(
    client: RequestClientLike,
    method: str,
    url: str,
    *,
    max_redirects: int = 5,
) -> ResponseLike:
    current_url = validate_public_http_url(url)
    for _ in range(max_redirects + 1):
        response = await client.request(method, current_url)
        if response.status_code not in _REDIRECT_STATUSES:
            return response
        location = _header_map(response.headers).get("location")
        if not location:
            return response
        current_url = validate_public_http_url(str(URL(current_url).join(location)))
    raise InvalidURL(reason="too_many_redirects", message="too many redirects")


def _cached_to_scrape_result(cached: Any) -> ScrapeResult:
    return ScrapeResult(
        html=getattr(cached, "html", None),
        markdown=getattr(cached, "markdown", None),
        metadata=getattr(cached, "metadata", None),
    )


async def _get_usable_cached_archive(
    url: str,
    *,
    scrape_cache: ScrapeCacheLike | None,
) -> tuple[Any | None, str | None]:
    if scrape_cache is None:
        return None, None
    for tier in _ARCHIVE_CACHE_TIERS:
        cached = await scrape_cache.get(url, tier=tier)
        if not cached or not getattr(cached, "html", None):
            continue
        if classify_scrape(_cached_to_scrape_result(cached)) is not ScrapeQuality.OK:
            continue
        return cached, tier
    return None, None


async def _revalidate_archive_final_url(
    cached: Any,
    *,
    original_url: str,
    scrape_cache: ScrapeCacheLike,
    tier: str,
) -> None:
    metadata = getattr(cached, "metadata", None)
    final_url = getattr(metadata, "source_url", None) if metadata is not None else None
    if not final_url:
        return
    try:
        validate_public_http_url(final_url)
    except InvalidURL:
        await scrape_cache.evict(original_url, tier=tier)
        raise


def _archive_display_html(
    cached_html: str | None,
    cached_markdown: str | None,
    *,
    utterances: list[Utterance] | None = None,
    raw_html: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Pick the archive iframe body for `cached_html`/`cached_markdown`.

    Prefers main-content extraction so SPA-rendered pages surface the post
    within the visible iframe viewport. Falls back to the surgical
    `strip_for_display` so non-SPA pages keep working.

    When the job has utterances, we prefer the extracted version only when
    it preserves every utterance text — otherwise the per-utterance highlights
    would silently disappear. Falling through to `strip_for_display` is safe
    because that path keeps the full document text.
    """
    enriched_html = (
        enrich_display_with_raw_styles(cached_html, raw_html, base_url=base_url)
        if cached_html and raw_html
        else cached_html
    )
    extracted = extract_archive_main_content(enriched_html, cached_markdown)
    stripped = strip_for_display(enriched_html) if enriched_html else None

    if extracted and (not utterances or _extracted_preserves_utterances(extracted, utterances)):
        return extracted
    if stripped:
        return stripped
    return extracted


def _extracted_preserves_utterances(
    extracted_html: str,
    utterances: list[Utterance],
) -> bool:
    """Return True iff every utterance text appears in `extracted_html`.

    Trafilatura can drop comment/forum blocks that the analyze pipeline
    marked as utterances. When that happens the archive iframe shows main
    content but the per-utterance highlights silently disappear. Caller
    compares this against a strip_for_display fallback that tends to preserve
    all original text and picks whichever surfaces more utterances.
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


def _archive_response_html(html: str) -> str:
    """Inject the defensive display stylesheet and return the full HTML string."""
    m = _DOCTYPE_RE.match(html)
    if m:
        return m.group(1) + _ARCHIVE_DISPLAY_STYLES + html[m.end() :]
    return _ARCHIVE_DISPLAY_STYLES + html


def _build_archive_display(
    cached_html: str | None,
    cached_markdown: str | None,
    *,
    utterances: list[Utterance] | None = None,
    raw_html: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Build the final archive display HTML: extract, annotate, wrap with styles."""
    display_html = _archive_display_html(
        cached_html,
        cached_markdown,
        utterances=utterances,
        raw_html=raw_html,
        base_url=base_url,
    )
    if not display_html:
        return None
    if utterances:
        display_html = annotate_utterances_in_html(display_html, utterances)
    return _archive_response_html(display_html)


async def frame_compat(
    url: str,
    *,
    client: RequestClientLike,
    scrape_cache: ScrapeCacheLike | None = None,
) -> FrameCompatResult:
    safe_url = validate_public_http_url(url)
    response = await _request_with_validated_redirects(client, "HEAD", safe_url)
    if response.status_code == _HEAD_FALLBACK_STATUS:
        response = await _request_with_validated_redirects(client, "GET", safe_url)
    can_iframe, blocking_header, csp_frame_ancestors = _evaluate_headers(response.headers)
    cached_archive, cached_tier = await _get_usable_cached_archive(
        safe_url, scrape_cache=scrape_cache
    )

    archive_render_mode: Literal["html_full_page", "html_extracted", "markdown", "text"] | None = (
        None
    )
    if cached_archive:
        if getattr(cached_archive, "html", None):
            archive_render_mode = (
                "html_full_page" if cached_tier == _BROWSER_HTML_ARCHIVE_TIER else "html_extracted"
            )
        elif getattr(cached_archive, "markdown", None):
            archive_render_mode = "markdown"
        else:
            archive_render_mode = "text"

    return FrameCompatResult(
        can_iframe=can_iframe,
        blocking_header=blocking_header,
        csp_frame_ancestors=csp_frame_ancestors,
        has_archive=bool(cached_archive),
        archive_render_mode=archive_render_mode,
    )


async def archive_preview(
    url: str,
    *,
    scrape_cache: ScrapeCacheLike,
    scraper: ScraperLike | None = None,
    generate: bool = False,
    utterances: list[Utterance] | None = None,
    content_format: str | None = None,
) -> str | None:
    safe_url = validate_public_http_url(url)
    cached, cached_tier = await _get_usable_cached_archive(safe_url, scrape_cache=scrape_cache)
    if cached and cached_tier:
        await _revalidate_archive_final_url(
            cached,
            original_url=safe_url,
            scrape_cache=scrape_cache,
            tier=cached_tier,
        )
        if content_format == "text":
            return getattr(cached, "markdown", None) or getattr(cached, "html", None) or ""
        cached_html = getattr(cached, "html", None)
        cached_markdown = getattr(cached, "markdown", None)
        raw_html = getattr(cached, "raw_html", None)
        return _build_archive_display(
            cached_html,
            cached_markdown,
            utterances=utterances,
            raw_html=raw_html,
            base_url=safe_url,
        )

    if not generate or scraper is None:
        return None

    fresh = await scraper.scrape(safe_url, formats=["html", "markdown"], only_main_content=True)
    if classify_scrape(fresh) is not ScrapeQuality.OK:
        return None

    stored = await scrape_cache.put(safe_url, fresh, tier="scrape")
    await _revalidate_archive_final_url(
        stored,
        original_url=safe_url,
        scrape_cache=scrape_cache,
        tier="scrape",
    )
    stored_html = getattr(stored, "html", None)
    stored_markdown = getattr(stored, "markdown", None)
    stored_raw_html = getattr(stored, "raw_html", None)
    return _build_archive_display(
        stored_html,
        stored_markdown,
        utterances=utterances,
        raw_html=stored_raw_html,
        base_url=safe_url,
    )


async def lookup_screenshot(
    url: str,
    *,
    scrape_cache: ScrapeCacheLike,
    screenshot_store: ScreenshotStoreLike,
) -> dict[str, str] | None:
    safe_url = validate_public_http_url(url)
    for tier in _ARCHIVE_CACHE_TIERS:
        cached = await scrape_cache.get(safe_url, tier=tier)
        if not cached:
            continue
        storage_key = getattr(cached, "storage_key", None)
        if not isinstance(storage_key, str) or not storage_key:
            continue
        signed_url = await screenshot_store.sign_url(storage_key, ttl=_SCREENSHOT_URL_TTL)
        if signed_url:
            return {"screenshot_url": signed_url}
    return None


__all__ = [
    "FrameCompatResult",
    "archive_preview",
    "frame_compat",
    "lookup_screenshot",
]
