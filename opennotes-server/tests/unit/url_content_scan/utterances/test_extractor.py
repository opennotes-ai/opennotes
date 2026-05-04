from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.firecrawl_client import ScrapeResult
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
              <section data-page-kind="forum_thread">
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

    assert [item.utterance_id is not None for item in forum_payload.utterances] == [True, True, True]
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

    assert [item.utterance_id is not None for item in thread_payload.utterances] == [True, True, True]
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
