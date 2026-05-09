"""Helpers for merging Viafoura comments into scraped article payloads."""

from __future__ import annotations

import html

from src.firecrawl_client import ScrapeResult

_COMMENTS_HEADER = "## Comments"


def merge_viafoura_into_scrape(
    scrape: ScrapeResult,
    comments_markdown: str,
) -> ScrapeResult:
    """Return a ScrapeResult with rendered Viafoura comments appended."""
    if not comments_markdown or not comments_markdown.strip():
        return scrape

    comments_block = (
        comments_markdown
        if comments_markdown.startswith(_COMMENTS_HEADER)
        else f"{_COMMENTS_HEADER}\n{comments_markdown}"
    )

    merged_markdown = (
        comments_block
        if scrape.markdown is None
        else f"{scrape.markdown}\n\n{comments_block}" if scrape.markdown else comments_block
    )
    merged_html = (
        None
        if scrape.html is None
        else (
            f'{scrape.html}<div data-platform-comments data-platform="viafoura" '
            f'data-platform-status="copied">{html.escape(comments_block)}</div>'
        )
    )

    return scrape.model_copy(update={"markdown": merged_markdown, "html": merged_html})


__all__ = ["merge_viafoura_into_scrape"]
