from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from src.coral.render import render_comments_to_html, render_to_markdown
from src.firecrawl_client import ScrapeResult
from src.x.api import XConversation, XTweet


@dataclass
class _XCommentAdapter:
    id: str
    body: str
    author_username: str | None
    parent_id: str | None
    created_at: datetime


def _adapt(tweet: XTweet) -> _XCommentAdapter:
    return _XCommentAdapter(
        id=tweet.id,
        body=html.escape(tweet.text, quote=True),
        author_username=tweet.author_handle,
        parent_id=tweet.in_reply_to_status_id,
        created_at=tweet.created_at,
    )


def merge_x_into_scrape(scrape: ScrapeResult, conversation: XConversation) -> ScrapeResult:
    nodes = [_adapt(tweet) for tweet in conversation.replies]
    comments_html = render_comments_to_html(nodes)
    wrapper = f'<div data-platform-comments data-platform="x">{comments_html}</div>'
    if conversation.truncated:
        wrapper += (
            '<p class="opennotes-x-truncated">'
            f"Reply tree truncated at {conversation.raw_count} replies"
            "</p>"
        )

    base_html = scrape.html or ""
    base_markdown = scrape.markdown or ""
    comments_markdown = render_to_markdown(nodes)
    return scrape.model_copy(
        update={
            "html": f"{base_html}\n{wrapper}" if base_html else wrapper,
            "markdown": (
                f"{base_markdown}\n\n{comments_markdown}"
                if base_markdown
                else comments_markdown
            ),
        }
    )
