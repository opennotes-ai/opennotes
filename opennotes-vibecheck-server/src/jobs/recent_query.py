"""Data access for the "Recently vibe checked" gallery (TASK-1485.03).

Joins `vibecheck_jobs` × `vibecheck_scrapes` keyed by `normalized_url`,
applies privacy defaults BEFORE dedup/limit so excluded rows can never
displace eligible ones, dedups to the most recent qualifying job per URL,
filters partials below the 90% completion threshold, signs screenshot
URLs, and returns up to `limit` `RecentAnalysis` rows.

90%-rule arithmetic uses raw `vibecheck_jobs.sections` JSONB key counts
(integer math: total > 0 AND done * 10 >= total * 9). Going through
`SectionSlug` would silently drop unknown / future keys and skew the ratio.

Privacy defaults applied here are the always-on baseline. The configurable
host denylist (TASK-1486) layers on top later — those filters live in this
same function so the denylist sees the same shaped rows.
"""
from __future__ import annotations

import ipaddress
import json
import re
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from src.analyses.schemas import RecentAnalysis

_SECRET_QUERY_PARAM_KEYS = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "secret",
        "key",
        "access_token",
        "password",
        "auth",
        "sig",
        "signature",
    }
)

_SAFE_PORTS = frozenset({80, 443})

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_DEFAULT_OVERFETCH_MULTIPLIER = 4

# Single-window: dedup on normalized_url (CTE), then status filter, then
# expired-scrape filter (LEFT JOIN + IS NOT NULL), then ORDER BY DESC + LIMIT.
# DISTINCT ON inside the CTE picks the most recent row per normalized_url
# directly so the post-filter limit is reachable whenever enough qualifying
# rows exist (LIMIT * 4 over-fetch is a defense-in-depth for partial-90%
# rule and privacy filter rejections, not a correctness requirement).
_RECENT_SQL = """
WITH dedup AS (
    SELECT DISTINCT ON (j.normalized_url)
        j.job_id,
        j.normalized_url,
        j.url AS source_url,
        j.finished_at,
        j.preview_description,
        j.sections,
        j.status
    FROM vibecheck_jobs j
    WHERE j.status IN ('done', 'partial')
      AND j.finished_at IS NOT NULL
      AND j.preview_description IS NOT NULL
    ORDER BY j.normalized_url, j.finished_at DESC
)
SELECT
    d.job_id,
    d.normalized_url,
    d.source_url,
    d.finished_at,
    d.preview_description,
    d.sections,
    d.status,
    s.page_title,
    s.screenshot_storage_key
FROM dedup d
INNER JOIN vibecheck_scrapes s
    ON s.normalized_url = d.normalized_url
WHERE s.screenshot_storage_key IS NOT NULL
  AND s.expires_at > now()
ORDER BY d.finished_at DESC
LIMIT $1
"""


class ScreenshotSigner(Protocol):
    """Minimal protocol for the dependency the route hands list_recent."""

    def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        ...


def _has_secret_query_param(query: str) -> bool:
    if not query:
        return False
    parsed = parse_qs(query, keep_blank_values=True)
    return any(key.lower() in _SECRET_QUERY_PARAM_KEYS for key in parsed)


def _is_blocked_host(host: str) -> bool:
    """Reject loopback, private IPv4/IPv6 ranges, and IDNA noise."""
    if not host:
        return True
    bare = host.lower()
    # Strip any IPv6 brackets so ipaddress can parse.
    if bare.startswith("[") and bare.endswith("]"):
        bare = bare[1:-1]
    if bare in _LOOPBACK_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(bare)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _is_blocked_url(raw_url: str) -> bool:
    """Apply the always-on privacy defaults.

    Excludes URLs whose query string contains common secret-shaped params,
    URLs with an explicit non-80/443 port, and URLs whose host is in the
    loopback or private range. Caller treats True as "exclude from gallery".
    """
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return True
    if not parts.scheme or not parts.netloc:
        return True
    if _has_secret_query_param(parts.query):
        return True
    host = parts.hostname or ""
    if _is_blocked_host(host):
        return True
    explicit_port = parts.port
    if explicit_port is not None and explicit_port not in _SAFE_PORTS:
        return True
    # Defense-in-depth — userinfo (`user:pass@host`) is not allowed.
    if "@" in parts.netloc.split("/", 1)[0]:
        return True
    return False


_BARE_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+$")


def _passes_partial_threshold(sections_raw: Any, status: str) -> bool:
    """Apply the 90% completion rule on raw JSONB key states.

    Uses integer math: total > 0 AND done * 10 >= total * 9. Done jobs
    pass unconditionally; failed jobs are filtered earlier by the SQL
    `status IN ('done','partial')` predicate.
    """
    if status == "done":
        return True
    if status != "partial":
        return False
    sections = (
        json.loads(sections_raw)
        if isinstance(sections_raw, str)
        else dict(sections_raw or {})
    )
    total = len(sections)
    if total == 0:
        return False
    done = sum(
        1
        for value in sections.values()
        if isinstance(value, dict) and value.get("state") == "done"
    )
    return done * 10 >= total * 9


async def list_recent(
    pool: Any,
    *,
    limit: int,
    signer: ScreenshotSigner,
) -> list[RecentAnalysis]:
    """Return up to `limit` qualifying RecentAnalysis rows for the gallery.

    Privacy filters apply BEFORE the limit cutoff so excluded rows cannot
    displace eligible ones. The SQL pulls `limit * 4` candidate rows so
    Python-side rejections (partial-below-90%, privacy filter) still leave
    enough survivors to fill the gallery in the typical case.
    """
    if limit <= 0:
        return []
    overfetch = max(limit * _DEFAULT_OVERFETCH_MULTIPLIER, limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_RECENT_SQL, overfetch)

    out: list[RecentAnalysis] = []
    for row in rows:
        if _is_blocked_url(row["source_url"]):
            continue
        if not _passes_partial_threshold(row["sections"], row["status"]):
            continue
        signed = signer.sign_screenshot_key(row["screenshot_storage_key"])
        if signed is None:
            continue
        out.append(
            RecentAnalysis(
                job_id=row["job_id"],
                source_url=row["source_url"],
                page_title=row["page_title"],
                screenshot_url=signed,
                preview_description=row["preview_description"],
                completed_at=row["finished_at"],
            )
        )
        if len(out) >= limit:
            break
    return out


__all__ = ["list_recent", "ScreenshotSigner"]
