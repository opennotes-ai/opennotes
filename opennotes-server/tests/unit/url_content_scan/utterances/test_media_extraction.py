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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("extractor", "content"),
    [
        (
            extract_image_urls,
            """
            <img src="javascript:alert(1)" />
            <img src="http://localhost/secret.png" />
            <img src="http://10.0.0.7/secret.png" />
            <img src="http://[fd00::1]/secret.png" />
            """,
        ),
        (
            extract_video_urls,
            """
            <video src="javascript:alert(1)"></video>
            <video src="http://localhost/secret.mp4"></video>
            <video src="http://10.0.0.7/secret.mp4"></video>
            <iframe src="http://[fd00::1]/secret.mp4"></iframe>
            """,
        ),
    ],
)
def test_extract_media_urls_rejects_non_public_targets(
    extractor: callable,
    content: str,
) -> None:
    assert extractor(content, "https://example.com/blog/post") == []
