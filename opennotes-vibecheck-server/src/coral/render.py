"""Render parsed Coral comments into a parser-friendly Markdown stream."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Protocol


class _CommentLike(Protocol):
    id: str
    body: str
    author_username: str | None
    parent_id: str | None
    created_at: object


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Best-effort strip of simple HTML from comment body."""
    return re.sub(_TAG_RE, "", text)


def _indent_lines(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" for line in text.splitlines() or [""])


def _to_markdown_lines(nodes: Iterable[_CommentLike]) -> list[str]:
    by_id: dict[str, _CommentLike] = {node.id: node for node in nodes}
    children: dict[str | None, list[_CommentLike]] = defaultdict(list)

    for node in nodes:
        parent_id = node.parent_id
        if parent_id is not None and parent_id not in by_id:
            parent_id = None
        children[parent_id].append(node)

    for group in children.values():
        group.sort(key=lambda comment: comment.created_at)

    lines: list[str] = []

    def walk(node: _CommentLike, depth: int) -> None:
        indent = "  " * depth
        body = _strip_html(node.body or "")
        author = node.author_username or "anonymous"
        parent = node.parent_id or "null"
        header = (
            f"{indent}- [{node.id}] author={author} "
            f"created_at={node.created_at.isoformat()} parent={parent}"
        )
        lines.append(header)
        lines.append(_indent_lines(f"  {body}", indent))
        for child in children.get(node.id, []):
            walk(child, depth + 1)

    for root in children.get(None, []):
        walk(root, 0)

    return lines


def render_to_markdown(nodes: list[_CommentLike]) -> str:
    """Render nodes as indented Markdown grouped by parent-child chains.

    The renderer is deliberately simple: it preserves author/timestamp/parent
    references while stripping basic HTML from `body` so downstream markdown/
    text processing can stay predictable.
    """
    lines = _to_markdown_lines(nodes)
    if not lines:
        return "## Comments\n"
    return "\n".join(["## Comments", *lines])
