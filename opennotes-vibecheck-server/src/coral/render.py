"""Render parsed Coral comments into a parser-friendly Markdown stream."""

from __future__ import annotations

import html
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

import bleach
from bs4 import BeautifulSoup
from bs4.element import Tag


class _CommentLike(Protocol):
    id: str
    body: str
    author_username: str | None
    parent_id: str | None
    created_at: datetime


_BLOCK_TAGS = {
    "article",
    "blockquote",
    "div",
    "footer",
    "header",
    "li",
    "ol",
    "p",
    "section",
    "ul",
}

_COMMENT_BODY_TAGS = frozenset(
    {
        "a",
        "blockquote",
        "br",
        "code",
        "em",
        "li",
        "ol",
        "p",
        "strong",
        "ul",
    }
)
_COMMENT_BODY_ATTRIBUTES = {
    "a": ["href", "rel", "target"],
}
_COMMENT_BODY_PROTOCOLS = ["http", "https", "mailto"]


def _collapse_inline_whitespace(text: str) -> str:
    return " ".join(text.split())


def _body_html_to_markdown_text(body: str) -> str:
    """Best-effort normalize Coral HTML fragments into readable Markdown text."""
    soup = BeautifulSoup(body, "html.parser")

    for anchor in soup.find_all("a"):
        if not isinstance(anchor, Tag):
            continue
        label = _collapse_inline_whitespace(anchor.get_text(" ", strip=True))
        href = anchor.get("href")
        href_text = href if isinstance(href, str) else None
        if label and href_text:
            anchor.replace_with(f"[{label}]({href_text})")
        elif label:
            anchor.replace_with(label)
        else:
            anchor.decompose()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    for list_item in soup.find_all("li"):
        list_item.insert(0, "- ")
        list_item.append("\n")

    for block in soup.find_all(list(_BLOCK_TAGS)):
        block.insert_before("\n")
        block.append("\n")

    lines = []
    for line in soup.get_text().splitlines():
        normalized = _collapse_inline_whitespace(line)
        if normalized:
            lines.append(normalized)

    return "\n".join(lines)


def _sanitize_comment_body_html(body: str) -> str:
    soup = BeautifulSoup(body or "", "html.parser")
    for unsafe in soup.find_all(["script", "style"]):
        unsafe.decompose()
    return bleach.clean(
        str(soup),
        tags=_COMMENT_BODY_TAGS,
        attributes=_COMMENT_BODY_ATTRIBUTES,
        protocols=_COMMENT_BODY_PROTOCOLS,
        strip=True,
    )


def _indent_lines(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" for line in text.splitlines() or [""])


def _to_markdown_lines(nodes: Sequence[_CommentLike]) -> list[str]:
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
        body = _body_html_to_markdown_text(node.body or "")
        author = node.author_username or "anonymous"
        parent = node.parent_id or "null"
        header = (
            f"{indent}- [{node.id}] author={author} "
            f"created_at={node.created_at.isoformat()} parent={parent}"
        )
        lines.append(header)
        lines.append(_indent_lines(body, f"{indent}  "))
        for child in children.get(node.id, []):
            walk(child, depth + 1)

    for root in children.get(None, []):
        walk(root, 0)

    return lines


def _comment_tree(
    nodes: Sequence[_CommentLike],
) -> tuple[dict[str | None, list[_CommentLike]], list[_CommentLike]]:
    by_id: dict[str, _CommentLike] = {node.id: node for node in nodes}
    children: dict[str | None, list[_CommentLike]] = defaultdict(list)

    for node in nodes:
        parent_id = node.parent_id
        if parent_id is not None and parent_id not in by_id:
            parent_id = None
        children[parent_id].append(node)

    for group in children.values():
        group.sort(key=lambda comment: comment.created_at)

    return children, children.get(None, [])


def render_comments_to_html(nodes: Sequence[_CommentLike]) -> str:
    """Render comment nodes as semantic, sanitized HTML for archive display."""
    children, roots = _comment_tree(nodes)
    if not roots:
        return ""

    def render_article(node: _CommentLike) -> str:
        comment_id = html.escape(node.id, quote=True)
        author = html.escape(node.author_username or "anonymous")
        created_at = html.escape(node.created_at.isoformat(), quote=True)
        parent_id = node.parent_id or ""
        parent_ref = (
            '<span class="opennotes-comment__parent">'
            f'in reply to <a href="#cmt-{html.escape(parent_id, quote=True)}">'
            f"{html.escape(parent_id)}</a></span>"
            if parent_id
            else ""
        )
        body = _sanitize_comment_body_html(node.body or "")
        replies = "".join(render_article(child) for child in children.get(node.id, []))
        return (
            f'<article id="cmt-{comment_id}" data-utterance-id="{comment_id}" '
            'class="opennotes-comment">'
            '<header class="opennotes-comment__header">'
            f'<span class="opennotes-comment__author">{author}</span>'
            f'<time datetime="{created_at}">{created_at}</time>'
            f"{parent_ref}"
            "</header>"
            f'<div class="opennotes-comment__body">{body}</div>'
            f"{replies}"
            "</article>"
        )

    items = "".join(f"<li>{render_article(root)}</li>" for root in roots)
    return f'<ol class="opennotes-comments">{items}</ol>'


def render_to_markdown(nodes: Sequence[_CommentLike]) -> str:
    """Render nodes as indented Markdown grouped by parent-child chains.

    The renderer is deliberately simple: it preserves author/timestamp/parent
    references while normalizing Coral's HTML `body` fragments so downstream
    markdown/text processing can stay predictable.
    """
    lines = _to_markdown_lines(nodes)
    if not lines:
        return "## Comments\n"
    return "\n".join(["## Comments", *lines])
