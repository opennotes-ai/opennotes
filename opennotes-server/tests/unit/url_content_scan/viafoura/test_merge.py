from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.services.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.url_content_scan.viafoura.api import ViafouraCommentNode, ViafouraComments
from src.url_content_scan.viafoura.merge import merge_viafoura_into_scrape

pytestmark = pytest.mark.unit

_TS = datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)


def _make_comments(
    nodes: list[ViafouraCommentNode],
    *,
    more_available: bool = False,
) -> ViafouraComments:
    from src.url_content_scan.viafoura.render import render_to_markdown

    markdown = render_to_markdown(nodes)
    if more_available:
        markdown = f"{markdown.rstrip()}\n[comments truncated]"
    return ViafouraComments(
        comments_markdown=markdown,
        nodes=nodes,
        raw_count=len(nodes),
        fetched_at=datetime.now(UTC),
        more_available=more_available,
    )


def _node(
    comment_id: str,
    body: str,
    author: str = "alice",
    parent_id: str | None = None,
) -> ViafouraCommentNode:
    return ViafouraCommentNode(
        id=comment_id,
        body=body,
        author_username=author,
        parent_id=parent_id,
        created_at=_TS,
        actor_uuid=None,
    )


def test_merge_appends_comments_when_scrape_has_both_markdown_and_html() -> None:
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
        metadata=ScrapeMetadata(source_url="https://example.com/article"),
        links=[],
        screenshot=None,
    )
    comments = _make_comments([_node("c1", "<p>Great comment</p>")])

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "Article body." in merged.markdown
    assert "## Comments" in merged.markdown
    assert "Great comment" in merged.markdown
    assert merged.html is not None
    assert "data-platform-comments" in merged.html
    assert 'data-platform="viafoura"' in merged.html


def test_merge_noop_on_empty_comments() -> None:
    scrape = ScrapeResult(markdown="Article text.", html="<article>Article body.</article>")
    empty_comments = ViafouraComments(
        comments_markdown="",
        nodes=[],
        raw_count=0,
        fetched_at=datetime.now(UTC),
        more_available=False,
    )
    assert merge_viafoura_into_scrape(scrape, empty_comments) == scrape


def test_merge_html_is_none_when_scrape_html_is_none() -> None:
    scrape = ScrapeResult(markdown="Article text.", html=None)
    comments = _make_comments([_node("c1", "<p>Comment</p>")])

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.html is None
    assert merged.markdown is not None
    assert "## Comments" in merged.markdown


def test_merge_deduplicates_against_vf3_scrape_html() -> None:
    body_text = "This is a real comment."
    vf3_html = (
        "<html><body>"
        f'<article aria-label="Comment by alice." class="vf3-comment">'
        f"<p>{body_text}</p>"
        "</article>"
        "</body></html>"
    )
    scrape = ScrapeResult(
        markdown=f"Article.\n\n{body_text}",
        html=vf3_html,
    )
    comments = _make_comments([_node("c1", f"<p>{body_text}</p>", author="anon")])

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "alice" in merged.markdown or "anon" in merged.markdown


def test_merge_preserves_metadata_and_links() -> None:
    meta = ScrapeMetadata(source_url="https://example.com/article")
    scrape = ScrapeResult(
        markdown="Article.",
        html="<article>Article.</article>",
        metadata=meta,
        links=["https://example.com/related"],
        screenshot="https://cdn.example.com/shot.png",
    )
    comments = _make_comments([_node("c1", "<p>Comment</p>")])

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.metadata == meta
    assert merged.links == scrape.links
    assert merged.screenshot == scrape.screenshot


def test_merge_comments_block_has_header_prefix() -> None:
    scrape = ScrapeResult(markdown=None, html="<article>text</article>")
    comments = _make_comments([_node("c1", "<p>Hello</p>")])

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert merged.markdown.startswith("## Comments")


def test_merge_truncation_marker_preserved_when_more_available() -> None:
    scrape = ScrapeResult(markdown="Article.", html="<article>Article.</article>")
    comments = _make_comments(
        [_node("c1", "<p>Comment</p>")],
        more_available=True,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "[comments truncated]" in merged.markdown
