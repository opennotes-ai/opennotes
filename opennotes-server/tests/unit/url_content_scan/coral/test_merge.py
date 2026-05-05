from __future__ import annotations

from html import escape

import pytest

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.url_content_scan.coral import merge_coral_into_scrape

pytestmark = pytest.mark.unit


def _expected_wrapper(markdown: str) -> str:
    return f"<div data-coral-comments>{escape(markdown)}</div>"


def test_merge_appends_comments_markdown_and_html_when_both_exist() -> None:
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
        metadata=ScrapeMetadata(source_url="https://example.com/article"),
        links=["https://example.com/related"],
        screenshot="https://cdn.example.com/screenshot.png",
    )
    comments = (
        "- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread."
    )

    merged = merge_coral_into_scrape(scrape, comments)

    assert (
        merged.markdown
        == "Article body.\n\n## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread."
    )
    assert scrape.html is not None
    assert merged.html == scrape.html + _expected_wrapper(
        "## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread."
    )
    assert merged.links == scrape.links
    assert merged.metadata == scrape.metadata
    assert merged.screenshot == scrape.screenshot


def test_empty_comments_are_noop() -> None:
    scrape = ScrapeResult(markdown="Article text.", html="<article>Article body.</article>")
    assert merge_coral_into_scrape(scrape, "   \n\n") == scrape
