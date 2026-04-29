"""Tests for Coral comment-to-markdown rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from src.coral import CoralCommentNode, render_to_markdown


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


def test_render_to_markdown_strips_html_tags() -> None:
    """HTML in comment bodies is converted into plain text for LLM readability."""
    nodes = [
        CoralCommentNode(
            id="comment-1",
            body="<p>Hello <strong>world</strong>! <a href='#'>Go</a>.</p>",
            author_username="alice",
            parent_id=None,
            created_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    ]

    rendered = render_to_markdown(nodes)

    assert "Hello world! Go." in rendered
    assert "<p>" not in rendered
    assert "</" not in rendered
