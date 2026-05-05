"""Render parsed Coral comments into a parser-friendly Markdown stream."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from lxml import html as lxml_html
from lxml.html import HtmlElement


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
        tail = anchor.tail or ""
        if parent is not None and replacement:
            previous = anchor.getprevious()
            if previous is not None:
                previous.tail = f"{previous.tail or ''}{replacement}{tail}"
            else:
                parent.text = f"{parent.text or ''}{replacement}{tail}"
        anchor.drop_tree()
    for br in root.xpath(".//br"):
        br.tail = f"\n{br.tail or ''}"
        br.drop_tag()
    for list_item in root.xpath(".//li"):
        if isinstance(list_item, HtmlElement):
            list_item.text = f"- {_collapse_inline_whitespace(list_item.text or '')}".rstrip()
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
        author = node.author_username or "anonymous"
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
