from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.services.firecrawl_client import ScrapeResult
from src.url_content_scan.coral.graphql import CoralComments, CoralFetchError
from src.url_content_scan.schemas import PageKind
from src.url_content_scan.utterances.extractor import extract_utterances

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_case(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text())


@pytest.mark.unit
@pytest.mark.parametrize(
    "case_name",
    [
        "blog_post",
        "forum_thread",
        "hierarchical_thread",
        "blog_index",
        "article",
        "other",
        "generic_heading_page",
    ],
)
def test_extract_utterances_matches_expected_fixture_shape(case_name: str) -> None:
    case = _load_case(case_name)

    payload = extract_utterances(
        ScrapeResult.model_validate(case["scrape"]),
        source_url=case["source_url"],
    )

    expected = case["expected"]
    assert payload.source_url == case["source_url"]
    assert payload.page_title == expected["page_title"]
    assert payload.page_kind is PageKind(expected["page_kind"])
    assert len(payload.utterances) == expected["utterance_count"]
    assert [item.kind for item in payload.utterances] == expected["kinds"]
    assert [item.parent_id for item in payload.utterances] == expected["parent_ids"]
    assert [item.author for item in payload.utterances] == expected["authors"]

    if "images" in expected:
        assert [item.mentioned_images for item in payload.utterances] == expected["images"]
    if "videos" in expected:
        assert [item.mentioned_videos for item in payload.utterances] == expected["videos"]
    if "urls" in expected:
        assert [item.mentioned_urls for item in payload.utterances] == expected["urls"]


@pytest.mark.unit
def test_extract_utterances_keeps_anchor_compatible_stable_ids() -> None:
    case = _load_case("hierarchical_thread")

    payload = extract_utterances(
        ScrapeResult.model_validate(case["scrape"]),
        source_url=case["source_url"],
    )

    assert [item.utterance_id for item in payload.utterances] == ["root-1", "reply-1", "reply-2"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case_name", "expected_kind"),
    [
        ("blog_post", PageKind.BLOG_POST),
        ("forum_thread", PageKind.FORUM_THREAD),
        ("hierarchical_thread", PageKind.HIERARCHICAL_THREAD),
        ("blog_index", PageKind.BLOG_INDEX),
        ("article", PageKind.ARTICLE),
        ("generic_heading_page", PageKind.OTHER),
    ],
)
def test_extract_utterances_infers_page_kind_without_data_page_kind(
    case_name: str,
    expected_kind: PageKind,
) -> None:
    case = _load_case(case_name)
    scrape = ScrapeResult.model_validate(case["scrape"])
    for page_kind in ("blog_post", "forum_thread", "hierarchical_thread", "blog_index", "article"):
        scrape.html = (scrape.html or "").replace(f' data-page-kind="{page_kind}"', "")

    payload = extract_utterances(scrape, source_url=case["source_url"])

    assert payload.page_kind is expected_kind


@pytest.mark.unit
def test_extract_utterances_backfills_deterministic_ids_and_parent_links() -> None:
    blog_scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Launch thread\n\nTop level\n\nFirst comment\n\nNested reply",
            "html": """
            <html><body>
              <section>
                <article data-role="post">
                  <h1>Launch thread</h1>
                  <p data-author>root_author</p>
                  <p>Top level</p>
                </article>
                <section data-comments>
                  <article>
                    <p data-author>commenter</p>
                    <p>First comment</p>
                    <article>
                      <p data-author>replier</p>
                      <p>Nested reply</p>
                    </article>
                  </article>
                </section>
              </section>
            </body></html>
            """,
            "metadata": {
                "title": "Launch thread",
                "sourceURL": "https://example.com/launch-thread",
            },
        }
    )

    blog_payload = extract_utterances(blog_scrape, "https://example.com/launch-thread")

    assert [item.utterance_id is not None for item in blog_payload.utterances] == [True, True, True]
    assert blog_payload.utterances[1].parent_id == blog_payload.utterances[0].utterance_id
    assert blog_payload.utterances[2].parent_id == blog_payload.utterances[1].utterance_id

    forum_scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Launch thread\n\nTop level\n\nThread reply\n\nSecond thread reply",
            "html": """
            <html><body>
              <section>
                <article data-role="post">
                  <h1>Launch thread</h1>
                  <p data-author>root_author</p>
                  <p>Top level</p>
                </article>
                <div>
                  <p data-author>child_author</p>
                  <p>Thread reply</p>
                </div>
                <div>
                  <p data-author>grandchild_author</p>
                  <p>Second thread reply</p>
                </div>
              </section>
            </body></html>
            """,
            "metadata": {
                "title": "Launch thread",
                "sourceURL": "https://example.com/launch-thread",
            },
        }
    )

    forum_payload = extract_utterances(forum_scrape, "https://example.com/launch-thread")

    assert [item.utterance_id is not None for item in forum_payload.utterances] == [
        True,
        True,
        True,
    ]
    assert forum_payload.utterances[1].parent_id == forum_payload.utterances[0].utterance_id
    assert forum_payload.utterances[2].parent_id == forum_payload.utterances[0].utterance_id

    thread_scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Launch thread\n\nTop level\n\nThread reply\n\nNested thread reply",
            "html": """
            <html><body>
              <section data-page-kind="hierarchical_thread">
                <article data-role="post">
                  <h1>Launch thread</h1>
                  <p data-author>root_author</p>
                  <p>Top level</p>
                </article>
                <ul>
                  <li>
                    <p data-author>child_author</p>
                    <p>Thread reply</p>
                    <ul>
                      <li>
                        <p data-author>grandchild_author</p>
                        <p>Nested thread reply</p>
                      </li>
                    </ul>
                  </li>
                </ul>
              </section>
            </body></html>
            """,
            "metadata": {
                "title": "Launch thread",
                "sourceURL": "https://example.com/launch-thread",
            },
        }
    )

    thread_payload = extract_utterances(thread_scrape, "https://example.com/launch-thread")

    assert [item.utterance_id is not None for item in thread_payload.utterances] == [
        True,
        True,
        True,
    ]
    assert thread_payload.utterances[1].parent_id == thread_payload.utterances[0].utterance_id
    assert thread_payload.utterances[2].parent_id == thread_payload.utterances[1].utterance_id


@pytest.mark.unit
def test_extract_utterances_does_not_inherit_descendant_media_or_links() -> None:
    scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Nested discussion\n\nTop level post\n\nParent comment\n\nChild reply",
            "html": """
            <html><body>
              <article data-role="post" data-utterance-id="post-1">
                <h1>Nested discussion</h1>
                <p data-author>root</p>
                <p>Top level post</p>
              </article>
              <section data-comments>
                <article data-comment-id="comment-1">
                  <p data-author>parent</p>
                  <p>Parent comment</p>
                  <article data-comment-id="reply-1" data-parent-id="comment-1">
                    <p data-author>child</p>
                    <p>Child reply</p>
                    <a href="/reply/link">child link</a>
                    <img src="/reply/image.png" />
                    <video src="/reply/video.mp4"></video>
                  </article>
                </article>
              </section>
            </body></html>
            """,
            "metadata": {
                "title": "Nested discussion",
                "sourceURL": "https://example.com/discussions/1",
            },
        }
    )

    payload = extract_utterances(scrape, "https://example.com/discussions/1")

    assert [item.mentioned_urls for item in payload.utterances] == [
        [],
        [],
        ["https://example.com/reply/link"],
    ]
    assert [item.mentioned_images for item in payload.utterances] == [
        [],
        [],
        ["https://example.com/reply/image.png"],
    ]
    assert [item.mentioned_videos for item in payload.utterances] == [
        [],
        [],
        ["https://example.com/reply/video.mp4"],
    ]


@pytest.mark.unit
def test_extract_utterances_merges_graphql_coral_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Article title\n\nArticle body.",
            "html": """
            <html><body>
              <article data-role="post" data-utterance-id="post-1">
                <h1>Article title</h1>
                <p>Article body.</p>
              </article>
              <iframe
                class="coral-talk-stream"
                src="https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fexample.com%2Farticle"
              ></iframe>
            </body></html>
            """,
            "metadata": {
                "title": "Article title",
                "sourceURL": "https://example.com/article",
            },
        }
    )
    fetch_mock = AsyncMock(
        return_value=CoralComments(
            comments_markdown=(
                "## Comments\n"
                "- [comment-1] author=alice created_at=2026-04-29T12:00:00+00:00 parent=null\n"
                "  Great discussion.\n"
                "  https://example.com/ref\n"
                "  - [comment-2] author=bob created_at=2026-04-29T12:05:00+00:00 parent=comment-1\n"
                "    Reply text."
            ),
            raw_count=2,
            fetched_at=datetime.now(UTC),
        )
    )
    monkeypatch.setattr(
        "src.url_content_scan.utterances.extractor.fetch_coral_comments", fetch_mock
    )

    payload = extract_utterances(scrape, "https://example.com/article")

    assert fetch_mock.await_count == 1
    assert [item.kind for item in payload.utterances] == ["post", "comment", "reply"]
    assert payload.utterances[1].parent_id == "post-1"
    assert payload.utterances[2].parent_id == "comment-1"
    assert "Great discussion." in payload.utterances[1].text


@pytest.mark.unit
def test_extract_utterances_parses_encoded_coral_author_with_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Article title\n\nArticle body.",
            "html": """
            <html><body>
              <article data-role="post" data-utterance-id="post-1">
                <h1>Article title</h1>
                <p>Article body.</p>
              </article>
              <iframe
                class="coral-talk-stream"
                src="https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fexample.com%2Farticle"
              ></iframe>
            </body></html>
            """,
            "metadata": {
                "title": "Article title",
                "sourceURL": "https://example.com/article",
            },
        }
    )
    fetch_mock = AsyncMock(
        return_value=CoralComments(
            comments_markdown=(
                "## Comments\n"
                "- [comment-1] author=Alice%20Smith created_at=2026-04-29T12:00:00+00:00 parent=null\n"
                "  Great discussion."
            ),
            raw_count=1,
            fetched_at=datetime.now(UTC),
        )
    )
    monkeypatch.setattr(
        "src.url_content_scan.utterances.extractor.fetch_coral_comments", fetch_mock
    )

    payload = extract_utterances(scrape, "https://example.com/article")

    assert [item.kind for item in payload.utterances] == ["post", "comment"]
    assert payload.utterances[1].author == "Alice Smith"
    assert payload.utterances[1].parent_id == "post-1"


@pytest.mark.unit
def test_extract_utterances_falls_back_when_coral_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scrape = ScrapeResult.model_validate(
        {
            "markdown": "# Article title\n\nArticle body.",
            "html": """
            <html><body>
              <article data-role="post" data-utterance-id="post-1">
                <h1>Article title</h1>
                <p>Article body.</p>
              </article>
              <iframe
                class="coral-talk-stream"
                src="https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fexample.com%2Farticle"
              ></iframe>
            </body></html>
            """,
            "metadata": {"title": "Article title", "sourceURL": "https://example.com/article"},
        }
    )
    monkeypatch.setattr(
        "src.url_content_scan.utterances.extractor.fetch_coral_comments",
        AsyncMock(side_effect=CoralFetchError("timed out")),
    )

    payload = extract_utterances(scrape, "https://example.com/article")

    assert [item.kind for item in payload.utterances] == ["post"]


@pytest.mark.unit
def test_extract_utterances_reads_latimes_style_copied_coral_comments() -> None:
    scrape = ScrapeResult.model_validate(
        {
            "markdown": "# LA Times article\n\nArticle body.",
            "html": """
            <html><body>
              <article data-role="post" data-utterance-id="post-1">
                <h1>LA Times article</h1>
                <p>Article body.</p>
              </article>
              <ps-comments
                id="coral_talk_stream"
                data-embed-url="https://latimes.coral.coralproject.net/assets/js/embed.js"
                data-env-url="https://latimes.coral.coralproject.net"
                data-story-id="story-123"
              >Show Comments</ps-comments>
              <section data-coral-comments="true" data-coral-status="copied">
                <article class="comment" id="comment-1">
                  <header>Alice</header>
                  <p>First LA Times comment.</p>
                  <article class="comment" id="comment-2" data-parent-id="comment-1">
                    <header>Bob</header>
                    <p>Nested reply.</p>
                  </article>
                </article>
              </section>
            </body></html>
            """,
            "metadata": {
                "title": "LA Times article",
                "sourceURL": "https://www.latimes.com/example",
            },
        }
    )

    payload = extract_utterances(scrape, "https://www.latimes.com/example")

    assert [item.kind for item in payload.utterances] == ["post", "comment", "reply"]
    assert payload.utterances[1].author == "Alice"
    assert payload.utterances[1].parent_id == "post-1"
    assert payload.utterances[2].author == "Bob"
    assert payload.utterances[2].parent_id == "comment-1"
