"""Render parsed Coral comments into a parser-friendly Markdown stream."""

from __future__ import annotations

import html
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from urllib.parse import quote

from lxml import html as lxml_html
from lxml.html import HtmlElement
from lxml.html.clean import Cleaner


class _CommentLike(Protocol):
    id: str
    body: str
    author_username: str | None
    parent_id: str | None
    created_at: datetime


_BLOCK_TAGS = {"article", "blockquote", "div", "footer", "header", "li", "ol", "p", "section", "ul"}


def _collapse_inline_whitespace(text: str) -> str:
    return " ".join(text.split())


def _body_html_to_markdown_text(body: str) -> str:  # noqa: PLR0912
    root = lxml_html.fragment_fromstring(body, create_parent="div")
    for anchor in root.xpath(".//a"):
        if not isinstance(anchor, HtmlElement):
            continue
        label = _collapse_inline_whitespace(anchor.text_content())
        href = anchor.get("href")
        parent = anchor.getparent()
        replacement = f"[{label}]({href})" if label and href else label
        if parent is not None and replacement:
            previous = anchor.getprevious()
            if previous is not None:
                previous.tail = f"{previous.tail or ''}{replacement}"
            else:
                parent.text = f"{parent.text or ''}{replacement}"
        anchor.drop_tree()
    for br in root.xpath(".//br"):
        br.tail = f"\n{br.tail or ''}"
        br.drop_tag()
    for list_item in root.xpath(".//li"):
        if isinstance(list_item, HtmlElement):
            if list_item.text and list_item.text.strip():
                list_item.text = f"- {list_item.text}"
            elif len(list_item):
                first_child = list_item[0]
                first_child.text = f"- {first_child.text or ''}"
            else:
                list_item.text = "-"
            list_item.tail = f"\n{list_item.tail or ''}"
    for tag_name in _BLOCK_TAGS:
        for block in root.xpath(f".//{tag_name}"):
            if isinstance(block, HtmlElement):
                block.text = f"\n{block.text or ''}"
                block.tail = f"\n{block.tail or ''}"
    lines: list[str] = []
    for line in root.text_content().splitlines():
        normalized = _collapse_inline_whitespace(line)
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


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
        author = quote(node.author_username or "anonymous", safe="")
        parent = node.parent_id or "null"
        lines.append(
            f"{indent}- [{node.id}] author={author} created_at={node.created_at.isoformat()} parent={parent}"
        )
        lines.append(_indent_lines(body, f"{indent}  "))
        for child in children.get(node.id, []):
            walk(child, depth + 1)

    for root in children.get(None, []):
        walk(root, 0)
    return lines


def render_to_markdown(nodes: Sequence[_CommentLike]) -> str:
    lines = _to_markdown_lines(nodes)
    if not lines:
        return "## Comments\n"
    return "\n".join(["## Comments", *lines])


_COMMENT_BODY_CLEANER = Cleaner(
    safe_attrs_only=True,
    safe_attrs=frozenset({"href", "rel"}),
    allow_tags=frozenset({"a", "blockquote", "br", "code", "em", "li", "ol", "p", "strong", "ul"}),
    remove_unknown_tags=False,
    page_structure=False,
    links=False,
    javascript=True,
    scripts=True,
    style=True,
    embedded=True,
    frames=True,
    forms=True,
    annoying_tags=True,
)


def _sanitize_comment_body_html(body: str) -> str:
    if not body or not body.strip():
        return ""
    try:
        return _COMMENT_BODY_CLEANER.clean_html(body)
    except Exception:
        return html.escape(body)


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
        replies = "".join(
            f"<li>{render_article(child)}</li>" for child in children.get(node.id, [])
        )
        replies_list = f'<ol class="opennotes-comment__replies">{replies}</ol>' if replies else ""
        return (
            f'<article id="cmt-{comment_id}" data-utterance-id="{comment_id}" '
            'class="opennotes-comment">'
            '<header class="opennotes-comment__header">'
            f'<span class="opennotes-comment__author">{author}</span>'
            f'<time datetime="{created_at}">{created_at}</time>'
            f"{parent_ref}"
            "</header>"
            f'<div class="opennotes-comment__body">{body}</div>'
            f"{replies_list}"
            "</article>"
        )

    items = "".join(f"<li>{render_article(root)}</li>" for root in roots)
    return f'<ol class="opennotes-comments">{items}</ol>'
