"""Shared HTML sanitizer used before persisting or exposing scraped HTML.

Why bs4 and not a regex: HTML parsing with regex is documented as
unsafe against common browser-lenient syntax (case-insensitive closing
tags, whitespace before `>`, trailing garbage after `</script>`, nested
comments, `--!>` comment terminators, etc.). CodeQL `py/bad-tag-filter`
and codex W2 P2-1 both flagged the previous regex-based strip. `bs4`
with the stdlib `html.parser` handles the corner cases without pulling
in `lxml`.

Trafilatura usage is scoped to archive *display* (TASK-1577.02): the
archive iframe needs the post text in the visible 432px viewport, but
SPA-rendered pages (Mastodon and similar) embed the post thousands of
pixels below site chrome that Firecrawl's only_main_content extractor
fails to strip from the html field. `extract_archive_main_content` runs
trafilatura on the cached html for that case, with a markdown render
fallback so working pages keep working. LLM/analyze paths still use the
surgical `strip_for_display`/`strip_for_llm` because forum-thread
structure is needed downstream of the extractor agent's `get_html()`.
"""
from __future__ import annotations

import functools

import trafilatura
from bs4 import BeautifulSoup, Comment
from markdown_it import MarkdownIt

_DISPLAY_STRIPPED_TAGS: tuple[str, ...] = ("script",)
_LLM_STRIPPED_TAGS: tuple[str, ...] = ("script", "style", "link")
_ARCHIVE_EXTRACT_MIN_CHARS = 200

_SCROLL_LOCK_CLASS_FRAGMENTS: frozenset[str] = frozenset({
    "met-panel-open", "modal-open", "menu-open", "no-scroll",
    "has-contextual-navigation", "overflow-hidden", "is-locked",
})
_SCROLL_LOCK_STYLE_PROPERTIES: tuple[str, ...] = (
    "overflow", "overflow-x", "overflow-y", "overscroll-behavior",
)
_SCROLL_LOCK_STYLE_VALUE_MARKERS: tuple[str, ...] = (
    "hidden", "clip", "none",
)

# TASK-1577.02 (Codex P2.5): tags and attribute patterns to strip from
# extracted archive HTML even though the iframe CSP is `default-src 'none'`.
# Defense in depth — the markup shouldn't carry exploit gadgets even when
# they cannot execute under the current CSP.
_ARCHIVE_FORBIDDEN_TAGS: tuple[str, ...] = (
    "script",
    "iframe",
    "object",
    "embed",
    "form",
)
_ARCHIVE_UNSAFE_URL_SCHEMES: tuple[str, ...] = (
    "javascript:",
    "vbscript:",
    "data:text/html",
)


def _neutralize_page_scroll_locks(soup: BeautifulSoup) -> None:
    """Strip overflow/overscroll inline styles and lock classes from html/body only."""
    for tag in (soup.find("html"), soup.find("body")):
        if tag is None:
            continue

        style = tag.get("style")
        if style and isinstance(style, str):
            kept = []
            for declaration in style.split(";"):
                if not declaration.strip():
                    continue
                parts = declaration.split(":", 1)
                if len(parts) == 2:
                    prop = parts[0].strip().lower()
                    val = parts[1].strip().lower()
                    if prop in _SCROLL_LOCK_STYLE_PROPERTIES and any(
                        marker in val for marker in _SCROLL_LOCK_STYLE_VALUE_MARKERS
                    ):
                        continue
                kept.append(declaration.strip())
            remainder = "; ".join(kept)
            if remainder:
                tag["style"] = remainder
            else:
                del tag["style"]

        classes = tag.get("class")
        if classes:
            if isinstance(classes, str):
                tokens = classes.split()
            else:
                tokens = list(classes)
            filtered = [t for t in tokens if t.lower() not in _SCROLL_LOCK_CLASS_FRAGMENTS]
            if filtered:
                tag["class"] = filtered
            else:
                del tag["class"]


def _strip_tags_and_comments(
    html: str | None, stripped_tags: tuple[str, ...]
) -> str | None:
    if html is None:
        return None
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(stripped_tags):
        tag.decompose()

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    return str(soup)


def strip_for_display(html: str | None) -> str | None:
    """Remove executable/comment noise while preserving stylesheet tags.

    Returns None if input is None; returns '' if input is an empty string.
    Preserves every other element and text node so downstream consumers
    that render archived HTML still see page styling.
    """
    if html is None:
        return None
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_DISPLAY_STRIPPED_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    _neutralize_page_scroll_locks(soup)
    return str(soup)


def strip_for_llm(html: str | None) -> str | None:
    """Remove `<script>`, `<style>`, `<link>`, and HTML comments from `html`.

    This preserves the prior `strip_noise` behavior for extractor and model
    input paths that do not need display CSS.
    """
    return _strip_tags_and_comments(html, _LLM_STRIPPED_TAGS)


def _sanitize_extracted_archive_html(html: str) -> str:
    """Defense-in-depth scrub of trafilatura output (Codex P2.5).

    Trafilatura preserves `<a href="javascript:...">`, inline event
    handlers, `<form>` / `<iframe>` / `<object>` / `<embed>`, and
    `<meta http-equiv="refresh">`. The archive iframe CSP blocks script
    execution and most navigation, but the markup itself shouldn't carry
    exploit gadgets that could fire under a relaxed CSP elsewhere.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(_ARCHIVE_FORBIDDEN_TAGS):
        tag.decompose()
    for meta in soup.find_all("meta"):
        http_equiv = meta.get("http-equiv")
        if isinstance(http_equiv, str) and http_equiv.strip().lower() == "refresh":
            meta.decompose()
    for tag in soup.find_all(True):
        for attr_name in list(tag.attrs):
            attr_lower = attr_name.lower()
            if attr_lower.startswith("on"):
                del tag.attrs[attr_name]
                continue
            if attr_lower in {"href", "src", "action", "formaction"}:
                value = tag.attrs[attr_name]
                if not isinstance(value, str):
                    continue
                trimmed = value.strip().lower()
                if any(trimmed.startswith(scheme) for scheme in _ARCHIVE_UNSAFE_URL_SCHEMES):
                    del tag.attrs[attr_name]
    return str(soup)


# Cache size chosen for memory bound: 64 entries times ~120KB cached_html
# upper bound is ~8MB worst case. lru_cache hashes its string args via
# Python's hash (interned + length-bounded), so repeat lookups against a
# stable cached row are O(1) after the first extraction. Cache is cleared
# implicitly when the process restarts.
@functools.lru_cache(maxsize=64)
def extract_archive_main_content(
    cached_html: str | None,
    cached_markdown: str | None,
) -> str | None:
    """Extract main article content for the archive iframe (TASK-1577.02).

    Trafilatura primary path: best for SPA-rendered pages whose SSR HTML is
    dominated by site chrome. Empirically (Mastodon reference URL) this
    drops the rendered iframe from ~9000px to ~1000px and lands the post
    text within the visible 432px viewport. Markdown render fallback for
    pages where trafilatura under-extracts; Firecrawl already produced
    that markdown with only_main_content=True. Returns None if neither
    yields usable content; the caller should then fall through to
    `strip_for_display(cached_html)` or 404 to the screenshot tab.

    Both paths gate on `_ARCHIVE_EXTRACT_MIN_CHARS` so trivial output
    cannot block the surgical strip_for_display fallback (Codex P2.4),
    and trafilatura output is sanitized (Codex P2.5).
    """
    if cached_html and cached_html.strip():
        extracted = trafilatura.extract(
            cached_html,
            output_format="html",
            include_links=True,
            include_images=True,
            include_tables=True,
            favor_recall=True,
        )
        if extracted and len(extracted.strip()) >= _ARCHIVE_EXTRACT_MIN_CHARS:
            return _sanitize_extracted_archive_html(extracted)

    if cached_markdown and cached_markdown.strip():
        rendered = MarkdownIt("commonmark").enable("table").render(cached_markdown)
        if rendered and len(rendered.strip()) >= _ARCHIVE_EXTRACT_MIN_CHARS:
            return _sanitize_extracted_archive_html(rendered)

    return None
