from __future__ import annotations

import pytest

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.url_content_scan.scrape_quality import (
    AUTH_WALL_HTML_MARKERS,
    AUTH_WALL_STATUS_CODES,
    INTERSTITIAL_MARKERS,
    LEGITIMATELY_EMPTY_MARKERS,
    MIN_BODY_CHARS,
    ScrapeQuality,
    classify_scrape,
)


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


def test_cf_interstitial_with_login_form_classifies_auth_wall_not_interstitial() -> None:
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


def test_404_page_not_found_classifies_legitimately_empty() -> None:
    result = ScrapeResult(
        markdown="# 404\n\nPage not found",
        html="<html><body><h1>404</h1><p>Page not found</p></body></html>",
        metadata=ScrapeMetadata(status_code=404),
    )

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


def test_empty_markdown_and_empty_html_classifies_legitimately_empty() -> None:
    result = ScrapeResult(
        markdown="",
        html="",
        metadata=ScrapeMetadata(status_code=200),
    )

    assert classify_scrape(result) is ScrapeQuality.LEGITIMATELY_EMPTY


def test_constants_are_exported_for_parameterization() -> None:
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
