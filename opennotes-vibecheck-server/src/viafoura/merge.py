"""Helpers for merging Viafoura comments into scraped article payloads."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.firecrawl_client import ScrapeResult

from .api import ViafouraCommentNode, ViafouraComments
from .render import render_comments_to_html, render_to_markdown

_COMMENTS_HEADER = "## Comments"
_ARIA_LABEL_RE = re.compile(r"Comment by (.+?)\.\s*$")
_TRUNCATION_MARKER = "[comments truncated]"


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).lower()


def _extract_vf3_body(element: BeautifulSoup) -> str:
    content = element.find(class_=lambda c: c and (
        "comment-body" in c or "vf3-comment-content" in c
    ))
    if content:
        return content.get_text(" ", strip=True)
    return element.get_text(" ", strip=True)


def _build_body_to_author(soup: BeautifulSoup) -> dict[str, str]:
    body_to_author: dict[str, str] = {}
    for article in soup.select("article[aria-label^='Comment by ']"):
        classes = article.get("class") or []
        if not any("vf3-comment" in c for c in classes):
            continue
        label = article.get("aria-label", "")
        match = _ARIA_LABEL_RE.search(label.strip())
        if not match:
            continue
        username = match.group(1)
        body_text = _extract_vf3_body(article)
        key = _normalize_text(body_text)
        if key and key not in body_to_author:
            body_to_author[key] = username
    return body_to_author


def _node_body_key(node: ViafouraCommentNode) -> str:
    soup = BeautifulSoup(node.body or "", "html.parser")
    return _normalize_text(soup.get_text(" ", strip=True))


def merge_viafoura_into_scrape(
    scrape: ScrapeResult,
    comments: ViafouraComments,
) -> ScrapeResult:
    """Return a ScrapeResult with rendered Viafoura comments appended."""
    comments_markdown = comments.comments_markdown
    if not comments_markdown or not comments_markdown.strip():
        return scrape

    nodes = comments.nodes
    scrape_html_for_concat = scrape.html
    nodes_modified = False

    if scrape.html is not None:
        soup = BeautifulSoup(scrape.html, "html.parser")
        body_to_author = _build_body_to_author(soup)

        if body_to_author:
            matched_keys: set[str] = set()
            updated_nodes: list[ViafouraCommentNode] = []
            for node in nodes:
                key = _node_body_key(node)
                if key in body_to_author:
                    updated_nodes.append(
                        node.model_copy(update={"author_username": body_to_author[key]})
                    )
                    matched_keys.add(key)
                    nodes_modified = True
                else:
                    updated_nodes.append(node)

            if matched_keys:
                for article in soup.select("article[aria-label^='Comment by ']"):
                    classes = article.get("class") or []
                    if not any("vf3-comment" in c for c in classes):
                        continue
                    body_text = _extract_vf3_body(article)
                    key = _normalize_text(body_text)
                    if key in matched_keys:
                        article.decompose()
                scrape_html_for_concat = str(soup)

            nodes = updated_nodes

    if nodes_modified:
        was_truncated = comments_markdown.rstrip().endswith(_TRUNCATION_MARKER)
        comments_markdown = render_to_markdown(nodes)
        if was_truncated:
            comments_markdown = f"{comments_markdown.rstrip()}\n{_TRUNCATION_MARKER}"

    comments_block = (
        comments_markdown
        if comments_markdown.startswith(_COMMENTS_HEADER)
        else f"{_COMMENTS_HEADER}\n{comments_markdown}"
    )

    merged_markdown = (
        comments_block
        if scrape.markdown is None
        else f"{scrape.markdown}\n\n{comments_block}"
        if scrape.markdown
        else comments_block
    )

    comments_html = render_comments_to_html(nodes)
    merged_html = (
        None
        if scrape.html is None
        else scrape_html_for_concat
        if not comments_html
        else (
            f'{scrape_html_for_concat}<div data-platform-comments data-platform="viafoura" '
            f'data-platform-status="copied">{comments_html}</div>'
        )
    )

    return scrape.model_copy(update={"markdown": merged_markdown, "html": merged_html})


__all__ = ["merge_viafoura_into_scrape"]
