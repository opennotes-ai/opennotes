"""Viafoura comment markdown rendering tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.viafoura import ViafouraCommentNode, render_to_markdown


def test_render_to_markdown_preserves_viafoura_comment_fields() -> None:
    rendered = render_to_markdown(
        [
            ViafouraCommentNode(
                id="comment-1",
                body="Top-level comment.",
                author_username="alice",
                parent_id=None,
                created_at=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            ),
            ViafouraCommentNode(
                id="comment-2",
                body="Reply body.",
                author_username="bob",
                parent_id="comment-1",
                created_at=datetime(2026, 5, 8, 12, 5, tzinfo=UTC),
            ),
        ]
    )

    assert rendered.startswith("## Comments\n")
    assert "[comment-1] author=alice" in rendered
    assert "created_at=2026-05-08T12:00:00+00:00" in rendered
    assert "parent=null" in rendered
    assert "[comment-2] author=bob" in rendered
    assert "parent=comment-1" in rendered
    assert "Reply body." in rendered
