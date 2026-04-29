"""Tests for merging rendered Coral comments into ScrapeResult payloads."""

from __future__ import annotations

from html import escape

from src.coral import merge_coral_into_scrape
from src.firecrawl_client import ScrapeMetadata, ScrapeResult


def _expected_wrapper(markdown: str) -> str:
    return f"<div data-coral-comments>{escape(markdown)}</div>"


def test_merge_appends_comments_markdown_and_html_when_both_exist() -> None:
    """Both markdown and html fields preserve existing data and append comments."""
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
        metadata=ScrapeMetadata(source_url="https://example.com/article"),
        links=["https://example.com/related"],
        screenshot="https://cdn.example.com/screenshot.png",
    )
    comments = "- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread."

    merged = merge_coral_into_scrape(scrape, comments)

    assert merged.markdown == "Article body.\n\n## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread."
    assert merged.html == scrape.html + _expected_wrapper("## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread.")
    assert merged.links == scrape.links
    assert merged.metadata == scrape.metadata
    assert merged.screenshot == scrape.screenshot


def test_merge_adds_comment_header_when_missing() -> None:
    """Header is added only when the rendered comments block does not provide it."""
    scrape = ScrapeResult(markdown="Article text.", html=None)
    comments = "- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  I missed heading."

    merged = merge_coral_into_scrape(scrape, comments)

    assert merged.markdown == "Article text.\n\n## Comments\n- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  I missed heading."


def test_merge_preserves_html_when_markdown_only_comments() -> None:
    """Markdown-only comments never invent a synthetic HTML payload."""
    scrape = ScrapeResult(markdown="Article body.", html=None)
    comments = "## Comments\n- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  Nice."

    merged = merge_coral_into_scrape(scrape, comments)

    assert merged.markdown == "Article body.\n\n## Comments\n- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  Nice."
    assert merged.html is None


def test_merge_keeps_html_when_markdown_is_none() -> None:
    """If markdown is missing, output is just the comment block."""
    scrape = ScrapeResult(markdown=None, html="<article>Comments-only page?</article>")
    comments = "## Comments\n- [def] author=carol created_at=2026-04-29T12:00:00+00:00 parent=null\n  No body text."

    merged = merge_coral_into_scrape(scrape, comments)

    assert merged.markdown == comments
    assert merged.html == scrape.html + _expected_wrapper(comments)


def test_empty_comments_are_noop() -> None:
    """Whitespace-only comments produce no comment section changes."""
    scrape = ScrapeResult(markdown="Article text.", html="<article>Article body.</article>")

    merged = merge_coral_into_scrape(scrape, "   \n\n")

    assert merged == scrape


def test_merge_does_not_mutate_input_scrape() -> None:
    """Input object remains unchanged after merge call."""
    scrape = ScrapeResult(
        markdown="Article text.",
        html="<article>Article body.</article>",
        metadata=ScrapeMetadata(source_url="https://example.com"),
    )
    before = scrape.model_dump()
    _ = merge_coral_into_scrape(scrape, "## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  New content.")

    assert scrape.model_dump() == before
