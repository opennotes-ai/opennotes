from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.monitoring import get_logger
from src.utils.url_security import InvalidURL, validate_public_http_url

logger = get_logger(__name__)

_CRAWLER_HEADERS = {
    "User-Agent": "Twitterbot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def fetch_x_og_image_url(url: str, *, http: httpx.AsyncClient) -> str | None:
    """Fetch an X status page and return its validated public og:image URL.

    Thumbnail discovery is best effort. X API content remains usable when the
    public page blocks, omits metadata, or advertises a URL the SSRF guard
    rejects.
    """
    try:
        response = await http.get(url, headers=_CRAWLER_HEADERS)
    except httpx.HTTPError as exc:
        logger.debug("x og image fetch failed for %s: %s", url, exc)
        return None
    if response.status_code >= 400:
        logger.debug(
            "x og image fetch failed for %s: status=%s", url, response.status_code
        )
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    tag = soup.select_one('meta[property="og:image"]') or soup.select_one(
        'meta[name="og:image"]'
    )
    if tag is None:
        return None
    content = tag.get("content")
    if not isinstance(content, str) or not content.strip():
        return None

    candidate = urljoin(url, content.strip())
    try:
        return validate_public_http_url(candidate)
    except InvalidURL:
        return None
