"""Tests for merging rendered Coral comments into ScrapeResult payloads."""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.coral import CoralCommentNode, CoralComments, merge_coral_into_scrape
from src.firecrawl_client import ScrapeMetadata, ScrapeResult


def _comments(markdown: str, nodes: list[CoralCommentNode] | None = None) -> CoralComments:
    return CoralComments(
        comments_markdown=markdown,
        nodes=nodes or [],
        raw_count=len(nodes or []),
        fetched_at=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )


def test_merge_appends_comments_markdown_and_html_when_both_exist() -> None:
    """Both markdown and html fields preserve existing data and append comments."""
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
        metadata=ScrapeMetadata(source_url="https://example.com/article"),
        links=["https://example.com/related"],
        screenshot="https://cdn.example.com/screenshot.png",
    )
    comments = _comments(
        "- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread.",
        [
            CoralCommentNode(
                id="abc",
                body="<p>Great thread.</p>",
                author_username="alice",
                parent_id=None,
                created_at=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
            )
        ],
    )

    merged = merge_coral_into_scrape(scrape, comments)
    soup = BeautifulSoup(merged.html or "", "html.parser")

    assert (
        merged.markdown
        == "Article body.\n\n## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  Great thread."
    )
    assert scrape.html is not None
    wrapper = soup.find(attrs={"data-platform-comments": True})
    assert wrapper is not None
    assert wrapper["data-platform"] == "coral"
    assert wrapper["data-platform-status"] == "copied"
    article = wrapper.find("article", id="cmt-abc")
    assert article is not None
    assert article["data-utterance-id"] == "abc"
    assert article.get_text(" ", strip=True).endswith("Great thread.")
    assert merged.links == scrape.links
    assert merged.metadata == scrape.metadata
    assert merged.screenshot == scrape.screenshot


def test_merge_adds_comment_header_when_missing() -> None:
    """Header is added only when the rendered comments block does not provide it."""
    scrape = ScrapeResult(markdown="Article text.", html=None)
    comments = _comments(
        "- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  I missed heading."
    )

    merged = merge_coral_into_scrape(scrape, comments)

    assert (
        merged.markdown
        == "Article text.\n\n## Comments\n- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  I missed heading."
    )


def test_merge_preserves_html_when_markdown_only_comments() -> None:
    """Markdown-only comments never invent a synthetic HTML payload."""
    scrape = ScrapeResult(markdown="Article body.", html=None)
    comments = _comments(
        "## Comments\n- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  Nice."
    )

    merged = merge_coral_into_scrape(scrape, comments)

    assert (
        merged.markdown
        == "Article body.\n\n## Comments\n- [abc] author=bob created_at=2026-04-29T12:00:00+00:00 parent=null\n  Nice."
    )
    assert merged.html is None


def test_merge_keeps_html_when_markdown_is_none() -> None:
    """If markdown is missing, output is just the comment block."""
    scrape = ScrapeResult(markdown=None, html="<article>Comments-only page?</article>")
    comments_text = "## Comments\n- [def] author=carol created_at=2026-04-29T12:00:00+00:00 parent=null\n  No body text."
    comments = _comments(
        comments_text,
        [
            CoralCommentNode(
                id="def",
                body="<p>No body text.</p>",
                author_username="carol",
                parent_id=None,
                created_at=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
            )
        ],
    )

    merged = merge_coral_into_scrape(scrape, comments)

    assert merged.markdown == comments_text
    assert scrape.html is not None
    soup = BeautifulSoup(merged.html or "", "html.parser")
    article = soup.find("article", id="cmt-def")
    assert article is not None
    assert article["data-utterance-id"] == "def"


def test_empty_comments_are_noop() -> None:
    """Whitespace-only comments produce no comment section changes."""
    scrape = ScrapeResult(markdown="Article text.", html="<article>Article body.</article>")

    merged = merge_coral_into_scrape(scrape, _comments("   \n\n"))

    assert merged == scrape


def test_merge_does_not_mutate_input_scrape() -> None:
    """Input object remains unchanged after merge call."""
    scrape = ScrapeResult(
        markdown="Article text.",
        html="<article>Article body.</article>",
        metadata=ScrapeMetadata(source_url="https://example.com"),
    )
    before = scrape.model_dump()
    _ = merge_coral_into_scrape(
        scrape,
        _comments(
            "## Comments\n- [abc] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n  New content."
        ),
    )

    assert scrape.model_dump() == before
