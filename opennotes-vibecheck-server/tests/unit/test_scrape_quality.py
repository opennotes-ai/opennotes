"""Behavior tests for the post-scrape quality classifier.

The classifier maps a `ScrapeResult` / `CachedScrape` into one of four
states the scrape ladder dispatches on:

    AUTH_WALL > INTERSTITIAL > LEGITIMATELY_EMPTY > OK

Priority order is the load-bearing invariant — a CF challenge sitting
on top of a login wall must always classify `AUTH_WALL` (terminal),
never `INTERSTITIAL` (escalate). Each test exercises a single branch
through the public `classify_scrape()` API with realistic fixture-shaped
payloads; no internal helpers are mocked.
"""
from __future__ import annotations

import pytest

from src.cache.scrape_cache import CachedScrape
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.jobs.scrape_quality import (
    AUTH_WALL_HTML_MARKERS,
    AUTH_WALL_STATUS_CODES,
    INTERSTITIAL_MARKERS,
    LEGITIMATELY_EMPTY_MARKERS,
    MIN_BODY_CHARS,
    ScrapeQuality,
    classify_scrape,
)

# ---------------------------------------------------------------------------
# OK — normal blog post.
# ---------------------------------------------------------------------------


def test_normal_blog_post_classifies_ok() -> None:
    body_paragraph = (
        "This is the opening paragraph of a blog post that obviously has real content. " * 10
    )
    result = ScrapeResult(
        markdown=f"# A Long Title For A Real Blog Post\n\n{body_paragraph}",
        html="<html><body><article><h1>A Long Title</h1><p>Real content here.</p></article></body></html>",
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com/post"),
    )

    assert classify_scrape(result) is ScrapeQuality.OK


# ---------------------------------------------------------------------------
# AUTH_WALL — login forms, redirect-to-login metadata, 401/403.
# ---------------------------------------------------------------------------


def test_login_form_password_input_classifies_auth_wall() -> None:
    result = ScrapeResult(
        markdown="Sign in to continue",
        html=(
            "<html><body><form action='/login' method='post'>"
            "<input name='email' type='email'>"
            "<input name='password' type='password'>"
            "<button>Sign in</button></form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


def test_status_code_403_alone_classifies_auth_wall() -> None:
    result = ScrapeResult(
        markdown="Forbidden",
        html="<html><body>Forbidden</body></html>",
        metadata=ScrapeMetadata(status_code=403),
    )

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


def test_status_code_401_classifies_auth_wall() -> None:
    result = ScrapeResult(
        markdown="",
        html="",
        metadata=ScrapeMetadata(status_code=401),
    )

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


def test_login_action_url_in_form_classifies_auth_wall() -> None:
    result = ScrapeResult(
        markdown="Welcome — please sign in.",
        html=(
            "<html><body>"
            "<form action='https://example.com/login' method='post'>"
            "<input type='text' name='username'>"
            "</form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


# ---------------------------------------------------------------------------
# AUTH_WALL priority — login wall under a CF interstitial.
# ---------------------------------------------------------------------------


def test_cf_interstitial_with_login_form_classifies_auth_wall_not_interstitial() -> None:
    """Priority order assertion: AUTH_WALL beats INTERSTITIAL.

    A CF challenge layered on top of a real login form must classify
    AUTH_WALL (terminal — never escalate). Misclassifying as
    INTERSTITIAL would push us into the interact-tier ladder, attempting
    to bypass auth, which is a ToS violation.
    """
    result = ScrapeResult(
        markdown="Just a moment... checking your browser",
        html=(
            "<html><head><title>Just a moment...</title></head><body>"
            "<div class='cf-browser-verification'>verifying...</div>"
            "<form action='/login' method='post'>"
            "<input type='password' name='password'>"
            "</form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=403),
    )

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


# ---------------------------------------------------------------------------
# INTERSTITIAL — CF challenge / JS-required markers.
# ---------------------------------------------------------------------------


def test_cf_just_a_moment_marker_classifies_interstitial() -> None:
    result = ScrapeResult(
        markdown="Just a moment... please wait while we verify your browser.",
        html=(
            "<html><head><title>Just a moment...</title></head>"
            "<body><div>checking your browser</div></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.INTERSTITIAL


def test_cf_browser_verification_class_classifies_interstitial() -> None:
    result = ScrapeResult(
        markdown="",
        html=(
            "<html><body>"
            "<div class='cf-browser-verification'>verifying...</div>"
            "</body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.INTERSTITIAL


def test_enable_javascript_marker_classifies_interstitial() -> None:
    result = ScrapeResult(
        markdown="Please enable JavaScript to continue.",
        html=(
            "<html><body><noscript>Please enable JavaScript and reload the page.</noscript>"
            "</body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.INTERSTITIAL


# ---------------------------------------------------------------------------
# LEGITIMATELY_EMPTY — 404, deleted page, empty bundle.
# ---------------------------------------------------------------------------


def test_404_page_not_found_classifies_legitimately_empty() -> None:
    result = ScrapeResult(
        markdown="# 404\n\nPage not found",
        html="<html><body><h1>404</h1><p>Page not found</p></body></html>",
        metadata=ScrapeMetadata(status_code=404),
    )

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


def test_deleted_marker_classifies_legitimately_empty() -> None:
    result = ScrapeResult(
        markdown="This post has been deleted",
        html="<html><body><p>This post has been deleted</p></body></html>",
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


def test_empty_markdown_and_empty_html_classifies_legitimately_empty() -> None:
    """Replaces the existing extractor.py:137 'no markdown' check.

    No markers at all + empty bundle => default empty (terminal),
    NOT interstitial (escalate). Empty-without-evidence is legitimate.
    """
    result = ScrapeResult(
        markdown="",
        html="",
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


def test_whitespace_only_markdown_and_empty_html_classifies_legitimately_empty() -> None:
    result = ScrapeResult(
        markdown="   \n\n  \t  ",
        html="",
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


def test_none_metadata_does_not_crash() -> None:
    """Defensive: missing metadata must not raise."""
    result = ScrapeResult(markdown="", html="", metadata=None)

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


# ---------------------------------------------------------------------------
# CachedScrape — same classification surface.
# ---------------------------------------------------------------------------


def test_cached_scrape_subclass_classifies_same_as_scrape_result() -> None:
    cached = CachedScrape(
        markdown="# A Real Long Cached Article\n\n" + ("filler content " * 50),
        html="<html><body><article>cached content</article></body></html>",
        metadata=ScrapeMetadata(status_code=200, source_url="https://example.com/cached"),
        storage_key="abc123-deadbeef.png",
    )

    assert classify_scrape(cached) is ScrapeQuality.OK


# ---------------------------------------------------------------------------
# Constants are exported and consistent.
# ---------------------------------------------------------------------------


def test_constants_are_exported_for_parameterization() -> None:
    """ACs require constants exported for test parameterization."""
    assert isinstance(INTERSTITIAL_MARKERS, tuple)
    assert isinstance(AUTH_WALL_HTML_MARKERS, tuple)
    assert isinstance(LEGITIMATELY_EMPTY_MARKERS, tuple)
    assert isinstance(AUTH_WALL_STATUS_CODES, frozenset)
    assert MIN_BODY_CHARS > 0
    assert "Just a moment" in INTERSTITIAL_MARKERS
    assert 401 in AUTH_WALL_STATUS_CODES
    assert 403 in AUTH_WALL_STATUS_CODES


@pytest.mark.parametrize("marker", INTERSTITIAL_MARKERS)
def test_each_interstitial_marker_triggers_interstitial(marker: str) -> None:
    result = ScrapeResult(
        markdown=f"Notice: {marker}",
        html=f"<html><body>{marker}</body></html>",
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.INTERSTITIAL


@pytest.mark.parametrize("status_code", sorted(AUTH_WALL_STATUS_CODES))
def test_each_auth_wall_status_code_triggers_auth_wall(status_code: int) -> None:
    result = ScrapeResult(
        markdown="",
        html="",
        metadata=ScrapeMetadata(status_code=status_code),
    )

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


# ---------------------------------------------------------------------------
# Determinism + purity.
# ---------------------------------------------------------------------------


def test_classify_is_deterministic() -> None:
    result = ScrapeResult(
        markdown="Just a moment...",
        html="<html><body>Just a moment...</body></html>",
        metadata=ScrapeMetadata(status_code=200),
    )

    first = classify_scrape(result)
    second = classify_scrape(result)
    third = classify_scrape(result)

    assert first is second is third


def test_enum_string_values_are_stable() -> None:
    assert ScrapeQuality.OK.value == "ok"
    assert ScrapeQuality.INTERSTITIAL.value == "interstitial"
    assert ScrapeQuality.AUTH_WALL.value == "auth_wall"
    assert ScrapeQuality.LEGITIMATELY_EMPTY.value == "legitimately_empty"
