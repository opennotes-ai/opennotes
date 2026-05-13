"""Helpers for merging Coral comments into scraped article payloads."""

from __future__ import annotations

from src.firecrawl_client import ScrapeResult

from .graphql import CoralComments
from .render import render_comments_to_html

_COMMENTS_HEADER = "## Comments"


def merge_coral_into_scrape(scrape: ScrapeResult, comments: CoralComments) -> ScrapeResult:
    """Return a ScrapeResult with rendered Coral comments appended after article content."""
    comments_markdown = comments.comments_markdown
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
        else f"{scrape.markdown}\n\n{comments_block}"
        if scrape.markdown
        else comments_block
    )
    comments_html = render_comments_to_html(comments.nodes)
    merged_html = (
        None
        if scrape.html is None or not comments_html
        else (
            f'{scrape.html}<div data-platform-comments data-platform="coral" '
            f'data-platform-status="copied" data-coral-comments="true">{comments_html}</div>'
        )
    )

    return scrape.model_copy(update={"markdown": merged_markdown, "html": merged_html})
