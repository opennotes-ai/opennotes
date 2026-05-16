from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.url_content_scan.coral import CoralCommentNode, render_to_markdown

pytestmark = pytest.mark.unit


def test_render_to_markdown_preserves_author_timestamp_and_parenting() -> None:
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
    ]

    rendered = render_to_markdown(nodes)

    assert rendered.startswith("## Comments\n")
    assert "[comment-1] author=alice" in rendered
    assert "parent=null" in rendered
    assert "[comment-2] author=bob" in rendered
    assert "parent=comment-1" in rendered


def test_render_to_markdown_preserves_anchor_href_targets() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body='<p>Read the <a href="https://example.com/ref">source</a> before replying.</p>',
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "Read the [source](https://example.com/ref) before replying." in rendered
    assert "before replying. before replying." not in rendered
    assert "<a " not in rendered


def test_render_to_markdown_url_encodes_authors_with_spaces() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body="<p>Hello.</p>",
            author_username="Alice Smith",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "[comment-1] author=Alice%20Smith" in rendered


def test_render_to_markdown_preserves_nested_inline_text_in_list_items() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body="<ul><li>One <strong>nested</strong> item</li></ul>",
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "- One nested item" in rendered


def test_render_to_markdown_preserves_multiple_list_item_blocks() -> None:
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body="<ul><li><p>One</p><p>Two</p></li><li>Three</li></ul>",
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "- One" in rendered
    assert "Two" in rendered
    assert "- Three" in rendered
    assert "OneTwo" not in rendered
