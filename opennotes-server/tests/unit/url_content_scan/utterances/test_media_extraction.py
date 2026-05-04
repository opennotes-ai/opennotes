from __future__ import annotations

import pytest

from src.url_content_scan.utterances.media_extraction import (
    extract_image_urls,
    extract_video_urls,
)


@pytest.mark.unit
def test_extract_image_urls_normalizes_relative_paths_from_html_and_markdown() -> None:
    content = """
    <img src="/images/hero.png" />
    ![diagram](../assets/diagram.jpg)
    """

    assert extract_image_urls(content, "https://example.com/blog/post") == [
        "https://example.com/images/hero.png",
        "https://example.com/assets/diagram.jpg",
    ]


@pytest.mark.unit
def test_extract_video_urls_normalizes_relative_paths_and_embeds() -> None:
    content = """
    <video src="/videos/demo.mp4"></video>
    <iframe src="https://www.youtube.com/embed/demo123"></iframe>
    [clip](../media/clip.webm)
    """

    assert extract_video_urls(content, "https://example.com/articles/launch") == [
        "https://example.com/videos/demo.mp4",
        "https://www.youtube.com/embed/demo123",
        "https://example.com/media/clip.webm",
    ]
