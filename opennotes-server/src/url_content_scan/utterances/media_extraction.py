from __future__ import annotations

import re
from urllib.parse import urljoin

from src.url_content_scan.normalize import normalize_url
from src.utils.url_security import InvalidURL, validate_public_http_url

_IMG_TAG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"'](?P<url>[^\"']+)[\"']", re.IGNORECASE)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*]\((?P<url>[^)]+)\)")
_VIDEO_TAG_RE = re.compile(
    r"<(?:video|source|iframe)\b[^>]*\bsrc=[\"'](?P<url>[^\"']+)[\"']",
    re.IGNORECASE,
)
_MD_LINK_RE = re.compile(r"\[[^\]]+]\((?P<url>[^)]+)\)")
_VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".m3u8", ".avi")


def normalize_public_url(candidate: str, source_url: str) -> str | None:
    url = candidate.strip()
    if not url:
        return None
    try:
        public_url = validate_public_http_url(urljoin(source_url, url))
    except InvalidURL:
        return None
    return normalize_url(public_url)


def _append_unique(values: list[str], candidate: str, source_url: str) -> None:
    normalized = normalize_public_url(candidate, source_url)
    if normalized is None:
        return
    if normalized not in values:
        values.append(normalized)


def extract_image_urls(content: str | None, source_url: str) -> list[str]:
    if not content:
        return []

    urls: list[str] = []
    for match in _IMG_TAG_RE.finditer(content):
        _append_unique(urls, match.group("url"), source_url)
    for match in _MD_IMAGE_RE.finditer(content):
        _append_unique(urls, match.group("url"), source_url)
    return urls


def extract_video_urls(content: str | None, source_url: str) -> list[str]:
    if not content:
        return []

    urls: list[str] = []
    for match in _VIDEO_TAG_RE.finditer(content):
        _append_unique(urls, match.group("url"), source_url)
    for match in _MD_LINK_RE.finditer(content):
        url = match.group("url").strip()
        lowered = url.lower()
        if lowered.startswith(
            ("https://www.youtube.com/embed/", "https://player.vimeo.com/video/")
        ) or lowered.endswith(_VIDEO_EXTENSIONS):
            _append_unique(urls, url, source_url)
    return urls
