"""Helpers for merging Viafoura comments into scraped article payloads."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import logfire
from bs4 import BeautifulSoup, Tag

from src.firecrawl_client import ScrapeResult

from .api import ViafouraCommentNode, ViafouraComments
from .render import render_comments_to_html, render_to_markdown

_COMMENTS_HEADER = "## Comments"
_ARIA_LABEL_RE = re.compile(r"Comment by (.+?)\.\s*$")
_TRUNCATION_MARKER = "[comments truncated]"


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return " ".join(normalized.split()).lower()


def _extract_vf3_body(element: Tag) -> str:
    for descendant in element.find_all(True):
        descendant_classes = descendant.get("class") or []
        if any(
            "comment-body" in c or "vf3-comment-content" in c
            for c in descendant_classes
        ):
            return descendant.get_text(" ", strip=True)
    return element.get_text(" ", strip=True)


def _build_body_to_authors(soup: BeautifulSoup) -> dict[str, list[tuple[str, Tag]]]:
    body_to_authors: dict[str, list[tuple[str, Tag]]] = {}
    for article in soup.select("article[aria-label^='Comment by ']"):
        classes = article.get("class") or []
        if not any("vf3-comment" in c for c in classes):
            continue
        label_attr = article.get("aria-label")
        if not isinstance(label_attr, str):
            continue
        match = _ARIA_LABEL_RE.search(label_attr.strip())
        if not match:
            continue
        username = match.group(1)
        body_text = _extract_vf3_body(article)
        key = _normalize_text(body_text)
        if key:
            body_to_authors.setdefault(key, []).append((username, article))
    return body_to_authors


def _node_body_key(node: ViafouraCommentNode) -> str:
    soup = BeautifulSoup(node.body or "", "html.parser")
    return _normalize_text(soup.get_text(" ", strip=True))


def _strip_matched_paragraphs(markdown: str, matched_keys: set[str]) -> str:
    paragraphs = re.split(r"\n\n+", markdown)
    kept = [p for p in paragraphs if _normalize_text(p) not in matched_keys]
    return "\n\n".join(kept)


@dataclass
class _DeduplicateResult:
    nodes: list[ViafouraCommentNode]
    matched_keys: set[str] = field(default_factory=set)
    updated_html: str | None = None
    nodes_matched: int = 0
    articles_decomposed: int = 0


def _deduplicate_against_scrape_html(
    nodes: list[ViafouraCommentNode],
    soup: BeautifulSoup,
    body_to_authors: dict[str, list[tuple[str, Tag]]],
) -> _DeduplicateResult:
    api_nodes_per_key: dict[str, int] = {}
    for node in nodes:
        key = _node_body_key(node)
        if key in body_to_authors:
            api_nodes_per_key[key] = api_nodes_per_key.get(key, 0) + 1

    consumed: dict[str, int] = {}
    updated_nodes: list[ViafouraCommentNode] = []
    matched_keys: set[str] = set()
    nodes_matched = 0

    for node in nodes:
        key = _node_body_key(node)
        if key not in body_to_authors:
            updated_nodes.append(node)
            continue
        authors_list = body_to_authors[key]
        if api_nodes_per_key.get(key, 0) != len(authors_list):
            updated_nodes.append(node)
            continue
        idx = consumed.get(key, 0)
        username, _ = authors_list[idx]
        consumed[key] = idx + 1
        updated_nodes.append(node.model_copy(update={"author_username": username}))
        matched_keys.add(key)
        nodes_matched += 1

    articles_decomposed = 0
    if matched_keys:
        for key in matched_keys:
            for _username, article in body_to_authors[key]:
                article.decompose()
                articles_decomposed += 1

    return _DeduplicateResult(
        nodes=updated_nodes,
        matched_keys=matched_keys,
        updated_html=str(soup) if matched_keys else None,
        nodes_matched=nodes_matched,
        articles_decomposed=articles_decomposed,
    )


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
    articles_found = 0
    nodes_matched = 0
    articles_decomposed = 0
    matched_body_keys: set[str] = set()

    if scrape.html is not None:
        soup = BeautifulSoup(scrape.html, "html.parser")
        body_to_authors = _build_body_to_authors(soup)
        articles_found = sum(len(v) for v in body_to_authors.values())

        if body_to_authors:
            result = _deduplicate_against_scrape_html(nodes, soup, body_to_authors)
            nodes = result.nodes
            matched_body_keys = result.matched_keys
            nodes_matched = result.nodes_matched
            articles_decomposed = result.articles_decomposed
            nodes_modified = nodes_matched > 0
            if result.updated_html is not None:
                scrape_html_for_concat = result.updated_html

    logfire.info(
        "viafoura.merge.dedup",
        articles_found=articles_found,
        nodes_matched=nodes_matched,
        articles_decomposed=articles_decomposed,
        parse_failed=0,
    )

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

    source_markdown = scrape.markdown
    if source_markdown and matched_body_keys:
        source_markdown = _strip_matched_paragraphs(source_markdown, matched_body_keys)

    merged_markdown = (
        comments_block
        if source_markdown is None
        else f"{source_markdown}\n\n{comments_block}"
        if source_markdown
        else comments_block
    )

    comments_html = render_comments_to_html(nodes)
    merged_html = _build_merged_html(scrape.html, scrape_html_for_concat, comments_html)

    return scrape.model_copy(update={"markdown": merged_markdown, "html": merged_html})


def _build_merged_html(
    original_html: str | None,
    scrape_html_for_concat: str | None,
    comments_html: str,
) -> str | None:
    if original_html is None:
        return None
    if not comments_html:
        return scrape_html_for_concat
    return (
        f'{scrape_html_for_concat}<div data-platform-comments data-platform="viafoura" '
        f'data-platform-status="copied">{comments_html}</div>'
    )


__all__ = ["merge_viafoura_into_scrape"]
