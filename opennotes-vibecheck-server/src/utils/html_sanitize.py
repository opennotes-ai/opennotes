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
import urllib.parse

import trafilatura
from bs4 import BeautifulSoup, Comment
from markdown_it import MarkdownIt

_ENRICH_MAX_BYTES: int = 256 * 1024

_DISPLAY_STRIPPED_TAGS: tuple[str, ...] = ("script",)
_LLM_STRIPPED_TAGS: tuple[str, ...] = ("script", "style", "link")
_ARCHIVE_EXTRACT_MIN_CHARS = 200

_ICON_VIEWBOX_MAX_DIMENSION: float = 64.0
_ICON_FALLBACK_STYLE: str = (
    "width:1em;height:1em;max-width:1.5rem;max-height:1.5rem;vertical-align:middle"
)

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
            tokens = classes.split() if isinstance(classes, str) else list(classes)
            filtered = [t for t in tokens if t.lower() not in _SCROLL_LOCK_CLASS_FRAGMENTS]
            if filtered:
                tag["class"] = " ".join(filtered)
            else:
                del tag["class"]


def _bound_unsized_icon_svgs(soup: BeautifulSoup) -> None:  # noqa: PLR0912
    """Prepend em-relative fallback dimensions to icon-shaped SVGs that have no explicit size.

    Archive HTML lost the Tailwind utility CSS that gave class-sized icons their dimensions,
    so unsized SVGs fall back to viewBox-derived sizes that can be the full container width.
    Bound icon-shaped SVGs with em-relative defaults that page CSS (when present) can still
    override.
    """
    for svg in soup.find_all("svg"):
        if svg.get("width") or svg.get("height"):
            continue

        style = svg.get("style")
        if style and isinstance(style, str):
            style_lower = style.lower()
            if "width:" in style_lower or "height:" in style_lower:
                continue

        viewbox = svg.get("viewBox") or svg.get("viewbox")
        if viewbox and isinstance(viewbox, str):
            parts = viewbox.strip().split()
            if len(parts) == 4:
                try:
                    vb_w = float(parts[2])
                    vb_h = float(parts[3])
                    if vb_w > _ICON_VIEWBOX_MAX_DIMENSION or vb_h > _ICON_VIEWBOX_MAX_DIMENSION:
                        continue
                except ValueError:
                    pass

        skip = False
        for ancestor_count, parent in enumerate(svg.parents):
            if ancestor_count >= 3:
                break
            if not hasattr(parent, "get"):
                break
            if parent.get("width") or parent.get("height"):
                skip = True
                break
            parent_style = parent.get("style")
            if parent_style and isinstance(parent_style, str):
                ps_lower = parent_style.lower()
                if "width:" in ps_lower or "height:" in ps_lower:
                    skip = True
                    break

        if skip:
            continue

        fallback = _ICON_FALLBACK_STYLE + ";"
        existing_style = svg.get("style")
        if existing_style and isinstance(existing_style, str):
            svg["style"] = fallback + existing_style
        else:
            svg["style"] = fallback


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
    _bound_unsized_icon_svgs(soup)
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


def enrich_display_with_raw_styles(  # noqa: PLR0912
    display_html: str,
    raw_html: str | None,
    *,
    base_url: str | None,
) -> str:
    """Inject safe <style> and <link rel=stylesheet> nodes from raw_html into display_html.

    Pass-through when raw_html is falsy. Idempotent: running twice does not duplicate.
    Filters stylesheet links to https-only absolute URLs (resolves relative via base_url).
    Normalizes async-load <link media=print onload=...> patterns to media=all (no onload).
    Caps total injected style text size at _ENRICH_MAX_BYTES to avoid blowing the iframe budget.
    """
    if not raw_html or not raw_html.strip():
        return display_html

    raw_soup = BeautifulSoup(raw_html, "html.parser")
    display_soup = BeautifulSoup(display_html, "html.parser")

    existing_style_texts: set[str] = {
        str(tag.get_text()).strip()
        for tag in display_soup.find_all("style")
        if str(tag.get_text()).strip()
    }
    existing_link_hrefs: set[str] = set()
    for tag in display_soup.find_all("link"):
        rel = tag.get("rel")
        rel_tokens: list[str] = rel if isinstance(rel, list) else ([rel] if isinstance(rel, str) else [])
        if "stylesheet" not in rel_tokens:
            continue
        href = tag.get("href")
        if isinstance(href, str) and href:
            existing_link_hrefs.add(href)

    queued_links: list[dict[str, str]] = []
    queued_styles: list[str] = []
    total_style_bytes = 0

    for tag in raw_soup.find_all("link"):
        rel = tag.get("rel")
        rel_tokens = rel if isinstance(rel, list) else ([rel] if isinstance(rel, str) else [])
        if "stylesheet" not in rel_tokens:
            continue
        raw_href = tag.get("href")
        if not isinstance(raw_href, str) or not raw_href:
            continue
        href_lower = raw_href.lower()
        if href_lower.startswith("data:") or raw_href.startswith("//"):
            continue
        if raw_href.startswith("http://"):
            continue
        if raw_href.startswith("https://"):
            resolved = raw_href
        else:
            if not base_url:
                continue
            resolved = urllib.parse.urljoin(base_url, raw_href)
            if not resolved.startswith("https://"):
                continue

        if resolved in existing_link_hrefs:
            continue
        existing_link_hrefs.add(resolved)

        attrs: dict[str, str] = {"href": resolved}
        media = tag.get("media")
        onload = tag.get("onload")
        # Normalize async-load pattern: <link media="print" onload="this.media='all'"> → media="all"
        if (
            isinstance(media, str)
            and media.strip().lower() == "print"
            and isinstance(onload, str)
            and "this.media" in onload
        ):
            attrs["media"] = "all"
        elif isinstance(media, str) and media:
            attrs["media"] = media

        crossorigin = tag.get("crossorigin")
        if isinstance(crossorigin, str) and crossorigin:
            attrs["crossorigin"] = crossorigin
        integrity = tag.get("integrity")
        if isinstance(integrity, str) and integrity:
            attrs["integrity"] = integrity

        queued_links.append(attrs)

    for tag in raw_soup.find_all("style"):
        text = str(tag.get_text()).strip()
        if not text:
            continue
        if text in existing_style_texts:
            continue
        text_bytes = len(text.encode())
        if total_style_bytes + text_bytes > _ENRICH_MAX_BYTES:
            continue
        existing_style_texts.add(text)
        queued_styles.append(text)
        total_style_bytes += text_bytes

    if not queued_links and not queued_styles:
        return display_html

    head = display_soup.find("head")
    if head is None:
        head = display_soup.new_tag("head")
        body = display_soup.find("body")
        if body is not None:
            body.insert_before(head)
        else:
            display_soup.insert(0, head)

    for link_attrs in queued_links:
        new_link = display_soup.new_tag("link", attrs={"rel": "stylesheet", **link_attrs})
        head.append(new_link)

    for style_text in queued_styles:
        new_style = display_soup.new_tag("style")
        new_style.string = style_text
        head.append(new_style)

    return str(display_soup)


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
