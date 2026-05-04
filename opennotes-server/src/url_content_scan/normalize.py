from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.utils.url_security import validate_public_http_url

_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in _TRACKING_PARAMS
        and not key.lower().startswith("mc_")
    ]
    query = urlencode(query_pairs)
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def canonical_cache_key(raw_url: str) -> str:
    return normalize_url(validate_public_http_url(raw_url))
