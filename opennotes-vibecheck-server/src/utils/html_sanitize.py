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

import trafilatura
from bs4 import BeautifulSoup, Comment
from markdown_it import MarkdownIt

_DISPLAY_STRIPPED_TAGS: tuple[str, ...] = ("script",)
_LLM_STRIPPED_TAGS: tuple[str, ...] = ("script", "style", "link")
_ARCHIVE_EXTRACT_MIN_CHARS = 200


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
    return _strip_tags_and_comments(html, _DISPLAY_STRIPPED_TAGS)


def strip_for_llm(html: str | None) -> str | None:
    """Remove `<script>`, `<style>`, `<link>`, and HTML comments from `html`.

    This preserves the prior `strip_noise` behavior for extractor and model
    input paths that do not need display CSS.
    """
    return _strip_tags_and_comments(html, _LLM_STRIPPED_TAGS)


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
            return extracted

    if cached_markdown and cached_markdown.strip():
        return MarkdownIt("commonmark").enable("table").render(cached_markdown)

    return None
