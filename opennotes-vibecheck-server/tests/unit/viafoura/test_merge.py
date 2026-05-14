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
                actor_uuid=None,
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


def test_merge_viafoura_preserves_article_html_when_comment_nodes_are_empty() -> None:
    scrape = ScrapeResult(
        markdown="Article body.",
        html="<article>Article body.</article>",
    )
    comments = ViafouraComments(
        comments_markdown="## Comments\n- [abc] author=alice created_at=2026-05-08T12:00:00+00:00 parent=null\n  Useful comment.",
        nodes=[],
        raw_count=0,
        fetched_at=datetime(2026, 5, 8, 12, 1, tzinfo=UTC),
        more_available=False,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert (
        merged.markdown
        == "Article body.\n\n## Comments\n- [abc] author=alice created_at=2026-05-08T12:00:00+00:00 parent=null\n  Useful comment."
    )
    assert merged.html == "<article>Article body.</article>"


def test_merge_single_vf3_comment_overwrites_author_and_removes_article() -> None:
    scrape_html = (
        '<main><p>Article body.</p>'
        '<article class="vf3-comment" aria-label="Comment by Mikeee.">'
        '<div class="vf3-comment-content">Hello there.</div>'
        '</article></main>'
    )
    scrape = ScrapeResult(markdown="Article body.", html=scrape_html)
    comments = ViafouraComments(
        comments_markdown="## Comments\n- [node1] author=user-abcd1234 created_at=2026-05-14T10:00:00+00:00 parent=null\n  Hello there.",
        nodes=[
            ViafouraCommentNode(
                id="node1",
                body="<p>Hello there.</p>",
                author_username="user-abcd1234",
                parent_id=None,
                created_at=datetime(2026, 5, 14, 10, 0, tzinfo=UTC),
                actor_uuid="abcd1234-0000-0000-0000-000000000000",
            )
        ],
        raw_count=1,
        fetched_at=datetime(2026, 5, 14, 10, 1, tzinfo=UTC),
        more_available=False,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "author=Mikeee" in merged.markdown
    assert "user-abcd1234" not in merged.markdown

    soup = BeautifulSoup(merged.html or "", "html.parser")
    platform_wrapper = soup.find(attrs={"data-platform-comments": True})
    assert platform_wrapper is not None
    author_span = platform_wrapper.find(class_="opennotes-comment__author")
    assert author_span is not None
    assert author_span.get_text() == "Mikeee"

    article_body_html = merged.html or ""
    before_platform = article_body_html.split('<div data-platform-comments')[0]
    assert 'vf3-comment' not in before_platform


def test_merge_unmatched_vf3_comment_preserves_pseudonym_and_article() -> None:
    scrape_html = (
        '<main><p>Article body.</p>'
        '<article class="vf3-comment" aria-label="Comment by Alice.">'
        '<div class="vf3-comment-content">other body</div>'
        '</article></main>'
    )
    scrape = ScrapeResult(markdown="Article body.", html=scrape_html)
    comments = ViafouraComments(
        comments_markdown="## Comments\n- [node2] author=user-abcd1234 created_at=2026-05-14T10:00:00+00:00 parent=null\n  completely different text",
        nodes=[
            ViafouraCommentNode(
                id="node2",
                body="<p>completely different text</p>",
                author_username="user-abcd1234",
                parent_id=None,
                created_at=datetime(2026, 5, 14, 10, 0, tzinfo=UTC),
                actor_uuid="abcd1234-0000-0000-0000-000000000000",
            )
        ],
        raw_count=1,
        fetched_at=datetime(2026, 5, 14, 10, 1, tzinfo=UTC),
        more_available=False,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "author=user-abcd1234" in merged.markdown

    article_body_html = merged.html or ""
    before_platform = article_body_html.split('<div data-platform-comments')[0]
    assert 'vf3-comment' in before_platform


def test_merge_multiple_vf3_comments_all_matched_dedup_all() -> None:
    scrape_html = (
        '<main><p>Article body.</p>'
        '<article class="vf3-comment" aria-label="Comment by Mikeee.">'
        '<div class="vf3-comment-content">First comment text.</div>'
        '</article>'
        '<article class="vf3-comment" aria-label="Comment by Bear0678.">'
        '<div class="vf3-comment-content">Second comment text.</div>'
        '</article>'
        '<article class="vf3-comment" aria-label="Comment by MargaretO.">'
        '<div class="vf3-comment-content">Third comment text.</div>'
        '</article>'
        '<article class="vf3-comment" aria-label="Comment by Lostagain.">'
        '<div class="vf3-comment-content">Fourth comment text.</div>'
        '</article>'
        '</main>'
    )
    scrape = ScrapeResult(markdown="Article body.", html=scrape_html)
    comments = ViafouraComments(
        comments_markdown=(
            "## Comments\n"
            "- [n1] author=user-aaaa1111 created_at=2026-05-14T10:00:00+00:00 parent=null\n  First comment text.\n"
            "- [n2] author=user-bbbb2222 created_at=2026-05-14T10:01:00+00:00 parent=null\n  Second comment text.\n"
            "- [n3] author=user-cccc3333 created_at=2026-05-14T10:02:00+00:00 parent=null\n  Third comment text.\n"
            "- [n4] author=user-dddd4444 created_at=2026-05-14T10:03:00+00:00 parent=null\n  Fourth comment text."
        ),
        nodes=[
            ViafouraCommentNode(
                id="n1",
                body="<p>First comment text.</p>",
                author_username="user-aaaa1111",
                parent_id=None,
                created_at=datetime(2026, 5, 14, 10, 0, tzinfo=UTC),
                actor_uuid="aaaa1111-0000-0000-0000-000000000000",
            ),
            ViafouraCommentNode(
                id="n2",
                body="<p>Second comment text.</p>",
                author_username="user-bbbb2222",
                parent_id=None,
                created_at=datetime(2026, 5, 14, 10, 1, tzinfo=UTC),
                actor_uuid="bbbb2222-0000-0000-0000-000000000000",
            ),
            ViafouraCommentNode(
                id="n3",
                body="<p>Third comment text.</p>",
                author_username="user-cccc3333",
                parent_id=None,
                created_at=datetime(2026, 5, 14, 10, 2, tzinfo=UTC),
                actor_uuid="cccc3333-0000-0000-0000-000000000000",
            ),
            ViafouraCommentNode(
                id="n4",
                body="<p>Fourth comment text.</p>",
                author_username="user-dddd4444",
                parent_id=None,
                created_at=datetime(2026, 5, 14, 10, 3, tzinfo=UTC),
                actor_uuid="dddd4444-0000-0000-0000-000000000000",
            ),
        ],
        raw_count=4,
        fetched_at=datetime(2026, 5, 14, 10, 4, tzinfo=UTC),
        more_available=False,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.markdown is not None
    assert "author=Mikeee" in merged.markdown
    assert "author=Bear0678" in merged.markdown
    assert "author=MargaretO" in merged.markdown
    assert "author=Lostagain" in merged.markdown
    assert "user-aaaa1111" not in merged.markdown
    assert "user-bbbb2222" not in merged.markdown
    assert "user-cccc3333" not in merged.markdown
    assert "user-dddd4444" not in merged.markdown

    article_body_html = merged.html or ""
    before_platform = article_body_html.split('<div data-platform-comments')[0]
    assert 'vf3-comment' not in before_platform


def test_merge_vf3_comment_with_scrape_html_none_unchanged() -> None:
    scrape = ScrapeResult(markdown="Article body.", html=None)
    node = ViafouraCommentNode(
        id="node5",
        body="<p>Hello.</p>",
        author_username="user-eeee5555",
        parent_id=None,
        created_at=datetime(2026, 5, 14, 10, 0, tzinfo=UTC),
        actor_uuid="eeee5555-0000-0000-0000-000000000000",
    )
    comments = ViafouraComments(
        comments_markdown="## Comments\n- [node5] author=user-eeee5555 created_at=2026-05-14T10:00:00+00:00 parent=null\n  Hello.",
        nodes=[node],
        raw_count=1,
        fetched_at=datetime(2026, 5, 14, 10, 1, tzinfo=UTC),
        more_available=False,
    )

    merged = merge_viafoura_into_scrape(scrape, comments)

    assert merged.html is None
    assert merged.markdown is not None
    assert "author=user-eeee5555" in merged.markdown
