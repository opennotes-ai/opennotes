"""Shared URL normalization used by both the sidebar cache and scrape cache.

Two caches key off normalized URLs: `vibecheck_analyses` (sidebar, TASK-1471)
and `vibecheck_scrapes` (scrape bundles, TASK-1473). They must agree on
normalization — if one strips a tracking param and the other doesn't, the
dedup invariant breaks and the same URL can be scraped twice. Keeping the
implementation in one module enforces that invariant.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
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
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))
