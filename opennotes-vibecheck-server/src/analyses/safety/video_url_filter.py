from __future__ import annotations

import ipaddress
from urllib.parse import ParseResult, urlparse

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

VIDEO_HOST_SUFFIXES = (".youtube.com", ".vimeo.com")


def is_potential_video_url(url: str) -> bool:
    """Return whether a raw mentioned_videos value is fetchable video input."""
    if not url or not isinstance(url, str):
        return False

    parsed_url = _parse_public_http_url(url.strip())
    if parsed_url is None:
        return False

    parsed, normalized_host = parsed_url
    if _is_video_host(normalized_host):
        return True

    path = parsed.path.lower()
    return any(path.endswith(extension) for extension in VIDEO_FILE_EXTENSIONS)


def _parse_public_http_url(url: str) -> tuple[ParseResult, str] | None:
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or not _has_valid_netloc(parsed.netloc)
        or _is_private_host(host.lower())
    ):
        return None
    return parsed, host.lower()


def _has_valid_netloc(netloc: str) -> bool:
    return bool(netloc) and not any(char.isspace() or char == "\\" for char in netloc)


def _is_video_host(host: str) -> bool:
    return host in VIDEO_HOSTS or host.endswith(VIDEO_HOST_SUFFIXES)


def _is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return not address.is_global
