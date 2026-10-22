"""Post-scrape quality classifier."""

from __future__ import annotations

from enum import StrEnum
from html.parser import HTMLParser
from urllib.parse import urlparse

from src.services.firecrawl_client import ScrapeResult


class ScrapeQuality(StrEnum):
    OK = "ok"
    INTERSTITIAL = "interstitial"
    AUTH_WALL = "auth_wall"
    LEGITIMATELY_EMPTY = "legitimately_empty"


AUTH_WALL_STATUS_CODES: frozenset[int] = frozenset({401, 403})
AUTH_WALL_HTML_MARKERS: tuple[str, ...] = (
    'type="password"',
    "type='password'",
    'action="/login"',
    "action='/login'",
    'action="/signin"',
    "action='/signin'",
    'action="/sign-in"',
    "action='/sign-in'",
)
_AUTH_WALL_LOGIN_PATHS: tuple[str, ...] = ("/login", "/signin", "/sign-in")
INTERSTITIAL_MARKERS: tuple[str, ...] = (
    "Just a moment",
    "cf-browser-verification",
    "Checking your browser",
    "challenge-platform",
    "Please enable JavaScript",
    "Please turn JavaScript on",
    "Enable JavaScript and reload",
    "__cf_chl_",
    "cf-challenge",
    "DDoS protection by",
)
LEGITIMATELY_EMPTY_MARKERS: tuple[str, ...] = (
    "Page not found",
    "page not found",
    "404 Not Found",
    "This post has been deleted",
    "This page has been removed",
    "Sorry, this page isn't available",
    "Sorry, this page isn’t available",  # noqa: RUF001
    "doesn't exist",
    "no longer available",
    "has been removed",
)
LEGITIMATELY_EMPTY_STATUS_CODES: frozenset[int] = frozenset({404, 410})
MIN_BODY_CHARS: int = 32


def classify_scrape(result: ScrapeResult) -> ScrapeQuality:  # noqa: PLR0911
    metadata = result.metadata
    status_code = metadata.status_code if metadata is not None else None
    html = result.html or ""
    markdown = result.markdown or ""
    body_text = f"{markdown}\n{html}"

    if status_code is not None and status_code in AUTH_WALL_STATUS_CODES:
        return ScrapeQuality.AUTH_WALL
    if _contains_any(html, AUTH_WALL_HTML_MARKERS):
        return ScrapeQuality.AUTH_WALL
    if _contains_login_form_action(html):
        return ScrapeQuality.AUTH_WALL

    if _contains_any(body_text, INTERSTITIAL_MARKERS):
        return ScrapeQuality.INTERSTITIAL

    if status_code is not None and status_code in LEGITIMATELY_EMPTY_STATUS_CODES:
        return ScrapeQuality.LEGITIMATELY_EMPTY
    if _contains_any(body_text, LEGITIMATELY_EMPTY_MARKERS):
        return ScrapeQuality.LEGITIMATELY_EMPTY
    if not markdown.strip() and not html.strip():
        return ScrapeQuality.LEGITIMATELY_EMPTY
    if len(markdown.strip()) < MIN_BODY_CHARS and not html.strip():
        return ScrapeQuality.LEGITIMATELY_EMPTY

    return ScrapeQuality.OK


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


class _LoginFormActionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._actions: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "form":
            return
        for key, value in attrs:
            if key == "action" and value is not None:
                self._actions.append(value)

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(self._actions)


def _contains_login_form_action(html: str) -> bool:
    parser = _LoginFormActionParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return False

    for action in parser.actions:
        parsed = urlparse(action.strip())
        path = parsed.path or ""
        normalized_path = path.lower().rstrip("/")
        if not normalized_path:
            continue
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        if normalized_path in _AUTH_WALL_LOGIN_PATHS:
            return True

    return False
