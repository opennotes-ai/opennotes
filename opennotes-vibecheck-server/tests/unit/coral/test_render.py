"""Tests for Coral comment-to-markdown rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.coral import CoralCommentNode, render_comments_to_html, render_to_markdown


def test_render_to_markdown_preserves_author_timestamp_and_parenting() -> None:
    """Rendered Markdown keeps author, timestamp, and parent_id for parsing."""
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body="<p>Hello, world!</p>",
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        ),
        CoralCommentNode(
            id="comment-2",
            body="<p>Replying to Alice</p>",
            author_username="bob",
            parent_id="comment-1",
            created_at=datetime(2026, 4, 29, 10, 5, tzinfo=UTC),
        ),
        CoralCommentNode(
            id="comment-3",
            body="<p>Another root comment</p>",
            author_username=None,
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 10, tzinfo=UTC),
        ),
    ]

    rendered = render_to_markdown(nodes)

    assert rendered.startswith("## Comments\n")
    assert "[comment-1] author=alice" in rendered
    assert "parent=null" in rendered
    assert "created_at=2026-04-29T10:00:00+00:00" in rendered
    assert "[comment-2] author=bob" in rendered
    assert "parent=comment-1" in rendered
    assert "Replying to Alice" in rendered
    assert "[comment-3] author=anonymous" in rendered
    assert rendered.index("comment-1") < rendered.index("comment-2")
    assert rendered.index("comment-2") < rendered.index("comment-3")


def test_render_to_markdown_preserves_html_body_boundaries() -> None:
    """Paragraphs, line breaks, lists, nested text, and entities stay readable."""
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body=(
                "<p>First paragraph &amp; entity.</p>"
                "<p>Second line<br>after break.</p>"
                "<ul><li>One <strong>nested</strong> item</li><li>Second item</li></ul>"
            ),
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "First paragraph & entity." in rendered
    assert "Second line\n  after break." in rendered
    assert "- One nested item" in rendered
    assert "- Second item" in rendered
    assert "<p>" not in rendered
    assert "</" not in rendered


def test_render_to_markdown_preserves_anchor_href_targets() -> None:
    """Coral comment links keep their target URL for downstream extraction."""
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body=(
                '<p>Read the <a href="https://example.com/ref">source</a> '
                "before replying.</p>"
            ),
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "Read the [source](https://example.com/ref) before replying." in rendered
    assert "<a " not in rendered


def test_render_comments_to_html_renders_threaded_articles() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body="<p>Hello <em>there</em>.</p>",
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        ),
        CoralCommentNode(
            id="comment-2",
            body="<p>Replying to Alice</p>",
            author_username="bob",
            parent_id="comment-1",
            created_at=datetime(2026, 4, 29, 10, 5, tzinfo=UTC),
        ),
    ]

    rendered = render_comments_to_html(nodes)
    soup = BeautifulSoup(rendered, "html.parser")

    root_list = soup.find("ol", class_="opennotes-comments")
    assert root_list is not None
    root_article = soup.find("article", id="cmt-comment-1")
    reply_article = soup.find("article", id="cmt-comment-2")
    assert root_article is not None
    assert reply_article is not None
    assert root_article["data-utterance-id"] == "comment-1"
    assert reply_article["data-utterance-id"] == "comment-2"
    reply_list = reply_article.find_parent("ol")
    reply_item = reply_article.find_parent("li")
    assert reply_list is not None
    assert reply_item is not None
    assert reply_list.find_parent("article") == root_article
    assert reply_item.find_parent("ol") == reply_list
    author = root_article.find("span", class_="opennotes-comment__author")
    timestamp = root_article.find("time")
    emphasized = root_article.find("em")
    assert author is not None
    assert timestamp is not None
    assert emphasized is not None
    assert author.get_text(strip=True) == "alice"
    assert timestamp["datetime"] == "2026-04-29T10:00:00+00:00"
    assert emphasized.get_text(strip=True) == "there"


def test_render_comments_to_html_strips_anchor_targets() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body='<p>Read <a href="https://example.com/ref" target="_blank">this</a>.</p>',
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_comments_to_html(nodes)
    soup = BeautifulSoup(rendered, "html.parser")

    anchor = soup.find("a")
    assert anchor is not None
    assert anchor["href"] == "https://example.com/ref"
    assert "target" not in anchor.attrs


def test_render_comments_to_html_sanitizes_unsafe_body_html() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body=(
                '<p onclick="alert(1)">Safe <a href="javascript:alert(1)">link</a></p>'
                "<script>alert(1)</script><img src=x onerror=alert(1)>"
            ),
            author_username=None,
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_comments_to_html(nodes)
    soup = BeautifulSoup(rendered, "html.parser")

    assert soup.find("script") is None
    assert soup.find("img") is None
    assert "onclick" not in str(soup)
    assert "javascript:" not in str(soup)
    anchor = soup.find("a")
    author = soup.find("span", class_="opennotes-comment__author")
    assert anchor is not None
    assert author is not None
    assert anchor.get_text(strip=True) == "link"
    assert author.get_text(strip=True) == "anonymous"


def test_render_comments_to_html_returns_empty_string_for_empty_nodes() -> None:
    assert render_comments_to_html([]) == ""
