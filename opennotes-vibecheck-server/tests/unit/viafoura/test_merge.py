"""Viafoura comment merge tests."""

from __future__ import annotations

from html import escape

from src.firecrawl_client import ScrapeResult
from src.viafoura import merge_viafoura_into_scrape


def test_merge_viafoura_into_scrape_appends_platform_marker_html() -> None:
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
    )
    comments = "## Comments\n- [abc] author=alice created_at=2026-05-08T12:00:00+00:00 parent=null\n  Useful comment."

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown == f"Article body.\n\n{comments}"
    assert scrape.html is not None
    assert merged.html == (
        scrape.html
        + '<div data-platform-comments data-platform="viafoura" data-platform-status="copied">'
        + escape(comments)
        + "</div>"
    )


def test_merge_viafoura_into_scrape_is_noop_for_empty_comments() -> None:
    scrape = ScrapeResult(markdown="Article body.", html="<article>Article body.</article>")

    assert merge_viafoura_into_scrape(scrape, "  \n") == scrape
