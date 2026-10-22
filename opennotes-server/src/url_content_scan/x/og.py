from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

from src.utils.url_security import InvalidURL, validate_public_http_url

logger = logging.getLogger(__name__)

_CRAWLER_HEADERS = {
    "User-Agent": "Twitterbot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_og_image_url(html_text: str, page_url: str) -> str | None:
    try:
        root = lxml_html.fromstring(html_text)
    except Exception:
        return None
    for meta in root.xpath('//meta[@property="og:image" or @name="og:image"]'):
        content = meta.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        candidate = urljoin(page_url, content.strip())
        try:
            return validate_public_http_url(candidate)
        except InvalidURL:
            return None
    return None


async def fetch_x_og_image_url(url: str, *, http: httpx.AsyncClient) -> str | None:
    try:
        response = await http.get(url, headers=_CRAWLER_HEADERS)
    except httpx.HTTPError as exc:
        logger.debug("x og image fetch failed for %s: %s", url, exc)
        return None
    if response.status_code >= 400:
        logger.debug("x og image fetch failed for %s: status=%s", url, response.status_code)
        return None
    return _extract_og_image_url(response.text, url)


__all__ = ["fetch_x_og_image_url"]
