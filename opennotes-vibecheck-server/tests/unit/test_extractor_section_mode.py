"""Tests for section-mode ExtractorDeps and tool surface (TASK-1649.04).

Covers:
- AC1: ExtractorDeps.section_mode + section_html field additions
- AC2: get_screenshot omitted from tool schema via _prepare_screenshot callback
- AC3: _get_html_impl full-page behavior unchanged in normal mode
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai.tools import ToolDefinition

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.cache.scrape_cache import CachedScrape
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.utterances.extractor import (
    ExtractorDeps,
    _get_html_impl,
    _prepare_screenshot,
)


def _fake_scrape_cache() -> MagicMock:
    return MagicMock()


def _cached_scrape(*, html: str | None = "<p>full page</p>") -> CachedScrape:
    return CachedScrape(
        markdown="# Page",
        html=html,
        screenshot=None,
        metadata=ScrapeMetadata(source_url="https://example.com", title="T"),
        storage_key=None,
    )


def _tool_def() -> ToolDefinition:
    return ToolDefinition(name="get_screenshot", description="desc", parameters_json_schema={})


def _section_deps(section_html: str = "<p>section</p>") -> ExtractorDeps:
    return ExtractorDeps(
        scrape=_cached_scrape(),
        scrape_cache=_fake_scrape_cache(),
        section_mode=True,
        section_html=section_html,
        parent_page_kind=PageKind.BLOG_POST,
        parent_utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        parent_page_title="Parent Title",
    )


def _normal_deps(html: str = "<p>full page</p>") -> ExtractorDeps:
    return ExtractorDeps(
        scrape=_cached_scrape(html=html),
        scrape_cache=_fake_scrape_cache(),
    )


# ---------------------------------------------------------------------------
# AC1 + AC3: ExtractorDeps fields and _get_html_impl behavior
# ---------------------------------------------------------------------------


def test_extractor_deps_section_mode_defaults_to_false() -> None:
    """New fields exist and default to False/None (AC1: preserves existing call sites)."""
    deps = ExtractorDeps(
        scrape=_cached_scrape(),
        scrape_cache=_fake_scrape_cache(),
    )
    assert deps.section_mode is False
    assert deps.section_html is None
    assert deps.parent_page_kind is None
    assert deps.parent_utterance_stream_type is None
    assert deps.parent_page_title is None


def test_get_html_impl_returns_section_html_in_section_mode() -> None:
    """In section mode, _get_html_impl returns section_html verbatim (AC1/AC3)."""
    deps = _section_deps(section_html="<p>SECTION ONLY</p>")
    result = _get_html_impl(deps)
    assert result == "<p>SECTION ONLY</p>"


def test_get_html_impl_returns_empty_when_section_html_is_none() -> None:
    """In section mode with no section_html, returns empty string not None."""
    deps = ExtractorDeps(
        scrape=_cached_scrape(html="<p>ignored</p>"),
        scrape_cache=_fake_scrape_cache(),
        section_mode=True,
        section_html=None,
    )
    result = _get_html_impl(deps)
    assert result == ""


def test_get_html_impl_sanitizes_full_page_in_normal_mode() -> None:
    """Normal mode: HTML is sanitized (scripts stripped), not section_html (AC3)."""
    raw_html = "<html><head><script>bad()</script></head><body><p>good</p></body></html>"
    deps = _normal_deps(html=raw_html)
    result = _get_html_impl(deps)
    assert "script" not in result
    assert "good" in result


# ---------------------------------------------------------------------------
# AC2: get_screenshot prepare callback hides tool in section mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_screenshot_returns_none_in_section_mode() -> None:
    """_prepare_screenshot returns None (omit tool) when section_mode is True (AC2)."""
    ctx = MagicMock()
    ctx.deps = _section_deps()
    tool_def = _tool_def()
    result = await _prepare_screenshot(ctx, tool_def)
    assert result is None


@pytest.mark.asyncio
async def test_prepare_screenshot_returns_tool_def_in_normal_mode() -> None:
    """_prepare_screenshot returns the ToolDefinition unchanged in normal mode (AC2)."""
    ctx = MagicMock()
    ctx.deps = _normal_deps()
    tool_def = _tool_def()
    result = await _prepare_screenshot(ctx, tool_def)
    assert result is tool_def
