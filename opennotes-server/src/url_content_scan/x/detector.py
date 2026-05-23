from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel

_ALLOWED_HOSTS = {
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
_TWITTER_HOSTS = {"twitter.com", "www.twitter.com", "mobile.twitter.com"}


class XStatusRef(BaseModel):
    post_id: str
    host: Literal["x.com", "twitter.com"]
    canonical_url: str


def _parse_url(raw_url: str):
    parsed = urlparse(raw_url)
    if not parsed.netloc:
        parsed = urlparse(f"https://{raw_url}")
    return parsed


def detect_x_status_url(url: str) -> XStatusRef | None:
    parsed = _parse_url(url)
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    post_id: str | None = None
    if len(segments) >= 3 and segments[1] == "status":
        post_id = segments[2]
    elif len(segments) >= 4 and segments[:3] == ["i", "web", "status"]:
        post_id = segments[3]
    if post_id is None or not post_id.isdigit():
        return None

    source_host: Literal["x.com", "twitter.com"] = (
        "twitter.com" if host in _TWITTER_HOSTS else "x.com"
    )
    return XStatusRef(
        post_id=post_id,
        host=source_host,
        canonical_url=f"https://x.com/i/status/{post_id}",
    )


__all__ = ["XStatusRef", "detect_x_status_url"]
