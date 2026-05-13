from __future__ import annotations

from urllib.parse import urlparse

VIDEO_FILE_EXTENSIONS = frozenset(
    {
        ".avi",
        ".m3u8",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".webm",
    }
)

VIDEO_HOSTS = frozenset(
    {
        "player.vimeo.com",
        "vimeo.com",
        "www.youtube.com",
        "youtu.be",
        "youtube.com",
    }
)


def is_potential_video_url(url: str) -> bool:
    """Return whether a raw mentioned_videos value is fetchable video input."""
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname
    if not host:
        return False
    if host.lower() in VIDEO_HOSTS:
        return True

    path = parsed.path.lower()
    return any(path.endswith(extension) for extension in VIDEO_FILE_EXTENSIONS)
