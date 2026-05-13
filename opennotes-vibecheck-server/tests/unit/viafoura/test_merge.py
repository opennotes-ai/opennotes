"""Viafoura comment merge tests."""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.firecrawl_client import ScrapeResult
from src.viafoura import ViafouraCommentNode, ViafouraComments, merge_viafoura_into_scrape


def test_merge_viafoura_into_scrape_appends_platform_marker_html() -> None:
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
    )
    comments_markdown = "## Comments\n- [abc] author=alice created_at=2026-05-08T12:00:00+00:00 parent=null\n  Useful comment."
    comments = ViafouraComments(
        comments_markdown=comments_markdown,
        nodes=[
            ViafouraCommentNode(
                id="abc",
                body="<p>Useful comment.</p>",
                author_username="alice",
                parent_id=None,
                created_at=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            )
        ],
        raw_count=1,
        fetched_at=datetime(2026, 5, 8, 12, 1, tzinfo=UTC),
        more_available=False,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)
    soup = BeautifulSoup(merged.html or "", "html.parser")

    assert merged.markdown == f"Article body.\n\n{comments_markdown}"
    assert scrape.html is not None
    wrapper = soup.find(attrs={"data-platform-comments": True})
    assert wrapper is not None
    assert wrapper["data-platform"] == "viafoura"
    assert wrapper["data-platform-status"] == "copied"
    article = wrapper.find("article", id="cmt-abc")
    assert article is not None
    assert article["data-utterance-id"] == "abc"
    assert article.get_text(" ", strip=True).endswith("Useful comment.")


def test_merge_viafoura_into_scrape_is_noop_for_empty_comments() -> None:
    scrape = ScrapeResult(markdown="Article body.", html="<article>Article body.</article>")

    comments = ViafouraComments(
        comments_markdown="  \n",
        nodes=[],
        raw_count=0,
        fetched_at=datetime(2026, 5, 8, 12, 1, tzinfo=UTC),
        more_available=False,
    )

    assert merge_viafoura_into_scrape(scrape, comments) == scrape
