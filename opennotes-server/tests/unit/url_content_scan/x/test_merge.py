from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.services.firecrawl_client import ScrapeResult
from src.url_content_scan.x.api import XConversation, XTweet
from src.url_content_scan.x.merge import merge_x_into_scrape

pytestmark = pytest.mark.unit

_TS = datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)


def _make_tweet(
    tweet_id: str,
    text: str,
    *,
    author_handle: str = "user",
    author_name: str = "User",
    in_reply_to: str | None = None,
) -> XTweet:
    return XTweet(
        id=tweet_id,
        text=text,
        author_id="999",
        author_handle=author_handle,
        author_name=author_name,
        created_at=_TS,
        in_reply_to_status_id=in_reply_to,
    )


def _make_scrape(html: str = "<p>Article</p>", markdown: str = "Article") -> ScrapeResult:
    return ScrapeResult(html=html, markdown=markdown, raw_html=html, screenshot=None, metadata=None)


class TestMergeXIntoScrape:
    def test_appends_x_conversation_html(self) -> None:
        root = _make_tweet("111", "Root post")
        reply = _make_tweet("222", "First reply", in_reply_to="111")
        conversation = XConversation(root=root, replies=[reply], raw_count=1, truncated=False)
        scrape = _make_scrape()

        result = merge_x_into_scrape(scrape, conversation)

        assert result.html is not None
        assert 'data-platform="x"' in result.html
        assert "First reply" in result.html

    def test_appends_x_conversation_markdown(self) -> None:
        root = _make_tweet("111", "Root post")
        reply = _make_tweet("222", "Reply text", author_handle="alice")
        conversation = XConversation(root=root, replies=[reply], raw_count=1, truncated=False)
        scrape = _make_scrape()

        result = merge_x_into_scrape(scrape, conversation)

        assert result.markdown is not None
        assert "Reply text" in result.markdown

    def test_adds_truncation_notice_when_truncated(self) -> None:
        root = _make_tweet("111", "Root")
        reply = _make_tweet("222", "Reply")
        conversation = XConversation(root=root, replies=[reply], raw_count=500, truncated=True)
        scrape = _make_scrape()

        result = merge_x_into_scrape(scrape, conversation)

        assert result.html is not None
        assert "truncated" in result.html
        assert "500" in result.html

    def test_handles_empty_replies(self) -> None:
        root = _make_tweet("111", "Root")
        conversation = XConversation(root=root, replies=[], raw_count=0, truncated=False)
        scrape = _make_scrape("<p>Body</p>", "Body")

        result = merge_x_into_scrape(scrape, conversation)

        assert result.html is not None
        assert "<p>Body</p>" in result.html

    def test_preserves_base_html(self) -> None:
        root = _make_tweet("111", "Root")
        reply = _make_tweet("222", "Reply")
        conversation = XConversation(root=root, replies=[reply], raw_count=1, truncated=False)
        base_html = "<article><p>Original content</p></article>"
        scrape = _make_scrape(html=base_html)

        result = merge_x_into_scrape(scrape, conversation)

        assert result.html is not None
        assert "<article><p>Original content</p></article>" in result.html


class TestMergeXMissingCredentials:
    def test_extractor_skips_when_bearer_absent(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from src.config import Settings
        from src.url_content_scan.utterances.extractor import _merge_x_conversations_if_available

        scrape = _make_scrape()
        settings = Settings()
        original = settings.X_API_BEARER_TOKEN
        object.__setattr__(settings, "X_API_BEARER_TOKEN", None)

        try:
            with caplog.at_level(logging.WARNING):
                result = _merge_x_conversations_if_available(
                    scrape,
                    "https://x.com/user/status/123456789",
                    settings=settings,
                )
        finally:
            object.__setattr__(settings, "X_API_BEARER_TOKEN", original)

        assert result is scrape
        assert any("x_augmentation_skipped" in r.message for r in caplog.records)
