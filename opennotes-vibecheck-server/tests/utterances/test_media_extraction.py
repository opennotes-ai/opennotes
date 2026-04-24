"""Unit tests for per-utterance media attribution (TASK-1474.05).

Covers `attribute_media` (mutating helper) and `page_level_media` (synthesis
helper) from `src.utterances.media_extraction`.
"""
from __future__ import annotations

from src.utterances.media_extraction import attribute_media, page_level_media
from src.utterances.schema import Utterance


def _utterance(
    kind: str = "post",
    text: str = "the post body",
    utterance_id: str | None = None,
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind=kind,  # pyright: ignore[reportArgumentType]
        text=text,
    )


# ---------------------------------------------------------------------------
# test 1 — per-utterance <img> attribution in separate DOM regions
# ---------------------------------------------------------------------------


def test_attribute_media_populates_per_utterance_images() -> None:
    """Two <div> blocks each containing one <img>; each utterance gets its own."""
    html = """
    <div>
      <p>The post body content here.</p>
      <img src="https://example.com/post.png" alt="post image">
    </div>
    <div>
      <p>A reply with different content.</p>
      <img src="https://example.com/reply.png" alt="reply image">
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")
    reply = _utterance(kind="reply", text="A reply with different content.")

    attribute_media(html, [post, reply])

    assert post.mentioned_images == ["https://example.com/post.png"]
    assert reply.mentioned_images == ["https://example.com/reply.png"]
    assert post.mentioned_urls == []
    assert reply.mentioned_urls == []


# ---------------------------------------------------------------------------
# test 2 — <a href> anchor attribution
# ---------------------------------------------------------------------------


def test_attribute_media_populates_mentioned_urls_from_anchor_hrefs() -> None:
    """<a href> links are attributed to the utterance whose text best matches."""
    html = """
    <div>
      <p>The post body content here.</p>
      <a href="https://example.com/link1">click here</a>
    </div>
    <div>
      <p>A reply with different content.</p>
      <a href="https://example.com/link2">another link</a>
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")
    reply = _utterance(kind="reply", text="A reply with different content.")

    attribute_media(html, [post, reply])

    assert post.mentioned_urls == ["https://example.com/link1"]
    assert reply.mentioned_urls == ["https://example.com/link2"]


# ---------------------------------------------------------------------------
# test 3 — YouTube iframe attributed as video
# ---------------------------------------------------------------------------


def test_attribute_media_extracts_youtube_iframe_as_video() -> None:
    """A YouTube iframe src is placed in mentioned_videos."""
    html = """
    <div>
      <p>The post body content here.</p>
      <iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" width="560" height="315"></iframe>
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")

    attribute_media(html, [post])

    assert "https://www.youtube.com/embed/dQw4w9WgXcQ" in post.mentioned_videos
    assert post.mentioned_images == []


# ---------------------------------------------------------------------------
# test 4 — non-allowlisted iframe ignored
# ---------------------------------------------------------------------------


def test_attribute_media_ignores_non_allowlisted_iframes() -> None:
    """An Instagram iframe should not appear in any utterance's mentioned_videos."""
    html = """
    <div>
      <p>The post body content here.</p>
      <iframe src="https://www.instagram.com/p/ABC123/embed/" width="400"></iframe>
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")

    attribute_media(html, [post])

    assert post.mentioned_videos == []


# ---------------------------------------------------------------------------
# test 5 — empty html is a no-op
# ---------------------------------------------------------------------------


def test_attribute_media_handles_empty_html() -> None:
    """Empty HTML string: no mutation, no exception."""
    post = _utterance(kind="post", text="The post body content here.")
    reply = _utterance(kind="reply", text="Some reply.")

    attribute_media("", [post, reply])

    assert post.mentioned_urls == []
    assert post.mentioned_images == []
    assert post.mentioned_videos == []
    assert reply.mentioned_urls == []
    assert reply.mentioned_images == []
    assert reply.mentioned_videos == []


# ---------------------------------------------------------------------------
# test 6 — html with no media elements: all lists stay empty
# ---------------------------------------------------------------------------


def test_attribute_media_handles_html_with_no_media() -> None:
    """HTML that has no <a>/<img>/<video>/<iframe>: all media lists empty."""
    html = """
    <div>
      <p>The post body content here.</p>
      <p>More text with no links or images.</p>
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")

    attribute_media(html, [post])

    assert post.mentioned_urls == []
    assert post.mentioned_images == []
    assert post.mentioned_videos == []


# ---------------------------------------------------------------------------
# test 7 — deduplication within utterance
# ---------------------------------------------------------------------------


def test_attribute_media_deduplicates_within_utterance() -> None:
    """Same <img> URL appearing twice in one region → single entry."""
    html = """
    <div>
      <p>The post body content here.</p>
      <img src="https://example.com/img.png">
      <img src="https://example.com/img.png">
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")

    attribute_media(html, [post])

    assert post.mentioned_images == ["https://example.com/img.png"]
    assert len(post.mentioned_images) == 1


# ---------------------------------------------------------------------------
# test 8 — unmatched media falls back to first kind="post" utterance
# ---------------------------------------------------------------------------


def test_attribute_media_attributes_unmatched_media_to_first_post() -> None:
    """An orphaned <img> with no matching DOM text → first kind='post' utterance."""
    html = """
    <div>
      <p>Completely unrelated DOM text xyz123.</p>
      <img src="https://example.com/orphan.png">
    </div>
    """
    post = _utterance(kind="post", text="The post body content here.")
    reply = _utterance(kind="reply", text="Some reply text.")

    attribute_media(html, [post, reply])

    assert "https://example.com/orphan.png" in post.mentioned_images
    assert reply.mentioned_images == []


# ---------------------------------------------------------------------------
# test 9 — page_level_media deduplicates and sorts across utterances
# ---------------------------------------------------------------------------


def test_page_level_media_dedup_across_utterances() -> None:
    """Shared media across utterances is deduped and sorted in page-level output."""
    post = _utterance(kind="post", text="Post text.")
    post.mentioned_urls = ["https://b.com", "https://a.com"]
    post.mentioned_images = ["https://img1.com/a.png"]
    post.mentioned_videos = []

    reply = _utterance(kind="reply", text="Reply text.")
    reply.mentioned_urls = ["https://a.com", "https://c.com"]
    reply.mentioned_images = ["https://img1.com/a.png", "https://img2.com/b.png"]
    reply.mentioned_videos = ["https://www.youtube.com/embed/xyz"]

    result = page_level_media([post, reply])

    assert result["urls"] == sorted({"https://a.com", "https://b.com", "https://c.com"})
    assert result["images"] == sorted({"https://img1.com/a.png", "https://img2.com/b.png"})
    assert result["videos"] == ["https://www.youtube.com/embed/xyz"]


def test_page_level_media_canonicalizes_before_deduping() -> None:
    post = _utterance(kind="post", text="Post text.")
    post.mentioned_urls = [
        "https://example.com/path/#one",
        "https://example.com/path?utm_source=x#two",
    ]
    post.mentioned_images = [
        "https://cdn.example.com/img.png#one",
        "https://cdn.example.com/img.png/#two",
    ]
    post.mentioned_videos = [
        "https://www.youtube.com/embed/xyz#t=1",
        "https://www.youtube.com/embed/xyz/",
    ]

    result = page_level_media([post])

    assert result["urls"] == ["https://example.com/path"]
    assert result["images"] == ["https://cdn.example.com/img.png"]
    assert result["videos"] == ["https://www.youtube.com/embed/xyz"]


# ---------------------------------------------------------------------------
# test 10 — page_level_media with empty utterances list
# ---------------------------------------------------------------------------


def test_page_level_media_with_empty_utterances() -> None:
    """No utterances → all three lists are empty."""
    result = page_level_media([])

    assert result == {"urls": [], "images": [], "videos": []}
