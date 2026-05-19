from datetime import UTC, datetime

from src.firecrawl_client import ScrapeResult
from src.x.api import XConversation, XTweet
from src.x.merge import merge_x_into_scrape


def _tweet(
    tweet_id: str,
    text: str,
    *,
    parent_id: str | None,
    minute: int,
) -> XTweet:
    return XTweet(
        id=tweet_id,
        text=text,
        author_id=f"author-{tweet_id}",
        author_handle=f"user{tweet_id}",
        author_name=f"User {tweet_id}",
        created_at=datetime(2026, 5, 18, 12, minute, tzinfo=UTC),
        in_reply_to_status_id=parent_id,
    )


def test_merge_x_into_scrape_appends_threaded_replies_without_root_duplication() -> None:
    root = _tweet("100", "Root post", parent_id=None, minute=0)
    reply = _tweet("101", "Reply one", parent_id="100", minute=1)
    nested = _tweet("102", "Nested reply", parent_id="101", minute=2)
    conversation = XConversation(root=root, replies=[reply, nested], raw_count=2, truncated=False)
    scrape = ScrapeResult(
        markdown="# @alice\n\nRoot post",
        html='<article data-utterance-id="100">Root post</article>',
    )

    merged = merge_x_into_scrape(scrape, conversation)

    assert merged.html is not None
    assert '<div data-platform-comments data-platform="x">' in merged.html
    assert 'data-utterance-id="100"' in merged.html
    assert merged.html.count('data-utterance-id="100"') == 1
    assert 'data-utterance-id="101"' in merged.html
    assert 'data-utterance-id="102"' in merged.html
    assert '<ol class="opennotes-comment__replies">' in merged.html
    assert "Nested reply" in merged.html
    assert "Reply tree truncated" not in merged.html


def test_merge_x_into_scrape_marks_truncated_conversation() -> None:
    root = _tweet("100", "Root post", parent_id=None, minute=0)
    reply = _tweet("101", "Reply one", parent_id="100", minute=1)
    conversation = XConversation(root=root, replies=[reply], raw_count=10, truncated=True)

    merged = merge_x_into_scrape(ScrapeResult(html="<main>Root</main>"), conversation)

    assert merged.html is not None
    assert "Reply tree truncated at 10 replies" in merged.html
