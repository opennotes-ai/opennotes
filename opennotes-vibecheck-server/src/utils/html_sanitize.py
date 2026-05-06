"""Shared HTML sanitizer used before persisting or exposing scraped HTML.

Why bs4 and not a regex: HTML parsing with regex is documented as
unsafe against common browser-lenient syntax (case-insensitive closing
tags, whitespace before `>`, trailing garbage after `</script>`, nested
comments, `--!>` comment terminators, etc.). CodeQL `py/bad-tag-filter`
and codex W2 P2-1 both flagged the previous regex-based strip. `bs4`
with the stdlib `html.parser` handles the corner cases without pulling
in `lxml`.

Why not trafilatura: trafilatura is a content extractor — it keeps only
the "main article body" and discards structure like forum threads and
comment trees. The extractor agent's `get_html()` tool is specifically
reached for when markdown extraction lost that structure, so we need a
surgical strip rather than a content extractor. Display archives preserve
stylesheet tags; model input keeps the stricter script/style/link cleanup.
"""
from __future__ import annotations

from bs4 import BeautifulSoup, Comment

_DISPLAY_STRIPPED_TAGS: tuple[str, ...] = ("script",)
_LLM_STRIPPED_TAGS: tuple[str, ...] = ("script", "style", "link")


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
