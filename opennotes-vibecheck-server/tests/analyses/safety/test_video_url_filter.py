from __future__ import annotations

import pytest

from src.analyses.safety.video_url_filter import is_potential_video_url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "blob:https://example.com/uuid",
        "data:video/mp4;base64,AAAA",
        "javascript:alert(1)",
        "ftp://example.com/video.mp4",
        "https://",
        "not a url",
    ],
)
def test_rejects_non_fetchable_video_urls(url: str) -> None:
    assert is_potential_video_url(url) is False


def test_rejects_generic_http_url_without_video_signal() -> None:
    assert is_potential_video_url("https://example.com/article") is False


def test_accepts_video_extension_with_query_and_fragment() -> None:
    assert is_potential_video_url("https://cdn.example.com/video.mp4?token=1#t=5") is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://player.vimeo.com/video/123",
    ],
)
def test_accepts_allowlisted_video_hosts(url: str) -> None:
    assert is_potential_video_url(url) is True
