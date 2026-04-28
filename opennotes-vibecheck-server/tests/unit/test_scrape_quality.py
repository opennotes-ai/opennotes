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

import json
from pathlib import Path

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

FIXTURES = Path(__file__).parent.parent / "fixtures" / "scrape_quality"


def _load_fixture(name: str) -> ScrapeResult:
    payload = json.loads((FIXTURES / name).read_text())
    return ScrapeResult.model_validate(payload)


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
        html=("<html><body><div class='cf-browser-verification'>verifying...</div></body></html>"),
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


def test_bare_login_url_substrings_are_not_in_markers() -> None:
    """Regression guard: bare URL substrings produce false positives.

    Header navigation anchors like `<a href="/login">Sign in</a>` were
    previously matched by `'/login"'` and friends, causing publicly
    readable articles with login chrome to misclassify as AUTH_WALL.
    """
    bare_substring_markers = (
        '/login"',
        "/login'",
        '/signin"',
        "/signin'",
        '/sign-in"',
        "/sign-in'",
    )
    for marker in bare_substring_markers:
        assert marker not in AUTH_WALL_HTML_MARKERS, (
            f"{marker!r} matches benign header nav links — must not be a marker"
        )


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


# ---------------------------------------------------------------------------
# Real-world fixtures captured via Firecrawl /scrape (TASK-1488.22).
#
# The header-login-link false positive was discovered on
# https://quizlet.com/blog/pride-month-2021 (job c79722c2-...). The
# fixtures exercise the full Pydantic validation path the live scrape
# ladder uses.
# ---------------------------------------------------------------------------


def test_quizlet_blog_with_login_link_chrome_classifies_ok() -> None:
    """Regression test for the TASK-1488.22 Quizlet false positive.

    The page is a public blog post (status 200, ~9.7k chars markdown).
    Site chrome contains a `/login` anchor in the nav. Previously the
    bare-URL substring `'/login"'` matched, classifying AUTH_WALL and
    terminating the job; the user saw an extraction failure for a page
    that was fully readable.
    """
    result = _load_fixture("quizlet_blog.json")

    assert classify_scrape(result) is ScrapeQuality.OK


def test_real_sparse_login_page_classifies_auth_wall() -> None:
    """Genuine login wall: sparse body + password input -> AUTH_WALL.

    Vimeo's `/log_in` page returns 200 with ~286 chars of markdown and
    a `<input type="password">`. After tightening, AUTH_WALL still fires
    because the sparse-body gate is satisfied and a password marker is
    present — preserving the ToS-critical priority order.
    """
    result = _load_fixture("login_gated_sparse.json")

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


def test_real_sparse_login_page_via_cached_scrape_classifies_auth_wall() -> None:
    """Tier 2 (CachedScrape) path also classifies sparse + password as AUTH_WALL.

    `_run_tier2` (orchestrator.py) re-runs `classify_scrape` on the
    interact-tier bundle. A real auth wall must not slip through Tier 2
    by being treated as OK — the sparse-body gate must still fire on
    the cached-scrape subclass.
    """
    payload = json.loads((FIXTURES / "login_gated_sparse.json").read_text())
    cached = CachedScrape.model_validate({**payload, "storage_key": "test-key.png"})

    assert classify_scrape(cached) is ScrapeQuality.AUTH_WALL


# ---------------------------------------------------------------------------
# Long-body login pages — password input still fires AUTH_WALL even
# when the page renders substantial supporting prose (privacy/terms
# links, social-login boilerplate, "trouble logging in" copy).
#
# These tests close the regression Codex 5.5-high flagged on PR #438:
# a 582-char login page returning OK is a ToS violation because Tier 2
# /interact would then attempt to bypass real auth.
# ---------------------------------------------------------------------------


def test_long_login_page_with_password_classifies_auth_wall() -> None:
    """Real-world login pages have substantive supporting copy.

    Privacy/Terms links, "Sign in with Google/Apple/Facebook" buttons,
    "Trouble logging in?" help text, and language selectors push the
    markdown well past the old SPARSE_BODY_THRESHOLD = 500. A page
    with `<input type="password">` is a login wall regardless of
    body length.
    """
    boilerplate = (
        "Sign in to your account. Sign in with Google. Sign in with Apple. "
        "Sign in with Facebook. By continuing you agree to our Terms of "
        "Service and Privacy Policy. Need help? Visit our help center for "
        "assistance with login issues, account recovery, two-factor "
        "authentication setup, security best practices, single sign-on "
        "configuration, and more. Trouble logging in? Reset your password. "
        "New user? Create an account. Trusted by millions of creators "
        "worldwide. We support modern browsers including Chrome, Firefox, "
        "Safari, and Edge. JavaScript and cookies must be enabled."
    )
    result = ScrapeResult(
        markdown=boilerplate,
        html=(
            "<html><body><form action='/login' method='post'>"
            "<input name='email' type='email'>"
            "<input name='password' type='password'>"
            "</form></body></html>"
        ),
        metadata=ScrapeMetadata(status_code=200),
    )
    # Sanity-check the fixture body length so the regression intent is
    # explicit: this would have slipped through the SPARSE_BODY_THRESHOLD
    # = 500 gate that was originally proposed.
    assert len(result.markdown or "") > 500

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL


def test_real_long_login_page_fixture_classifies_auth_wall() -> None:
    """WordPress.org login (2368 chars markdown + password input).

    Real Firecrawl capture; locks in the long-body-login regression.
    """
    result = _load_fixture("login_gated_long.json")
    assert len(result.markdown or "") > 500

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL

    assert classify_scrape(result) is ScrapeQuality.AUTH_WALL
