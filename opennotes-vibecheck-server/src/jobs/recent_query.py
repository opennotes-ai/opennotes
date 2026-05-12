"""Data access for the "Recently vibe checked" gallery (TASK-1485.03).

Joins `vibecheck_jobs` x `vibecheck_scrapes` keyed by `normalized_url`,
applies privacy defaults, dedups to the most recent surviving job per URL,
signs screenshot URLs, and returns up to `limit` `RecentAnalysis` rows.

The 90% completion rule for partial jobs is enforced in SQL so the
candidate set the route sees never includes sub-threshold partials. This
removes the displacement hazard where a newer <90% partial would shadow
an older qualifying done job for the same URL (TASK-1485.06 P1.1).

Privacy filters run in Python AFTER fetch but BEFORE dedup. Dedup picks
the newest row that survived all filters, so a newer privacy-rejected
duplicate cannot hide an older qualifying duplicate of the same
normalized URL (TASK-1485.06 P1.1).

Privacy filtering composes the repo-wide SSRF guard
`src/utils/url_security.py::validate_public_http_url` (TASK-1485.06 P1.2)
plus query-string secret detection and explicit-port rejection. The SSRF
guard handles IDNA, trailing-dot normalization, IP literals, blocked
suffixes (.internal/.local), and DNS resolution to non-private IPs. Pure
local checks (literals, suffixes, blocklist, query-string secrets) need
no DNS; non-literal hosts incur one getaddrinfo per row at refresh time
(60s TTL cache amortizes this in the route layer).

90%-rule arithmetic uses raw `vibecheck_jobs.sections` JSONB key counts
(integer math: total > 0 AND done * 10 >= total * 9). Going through
`SectionSlug` would silently drop unknown / future keys and skew the ratio.

The configurable host denylist (TASK-1486) layers on top later — those
filters live in this same function so the denylist sees the same shaped rows.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from pydantic import ValidationError

from src.analyses.safety._schemas import SafetyRecommendation
from src.analyses.schemas import RecentAnalysis
from src.analyses.synthesis._weather_schemas import WeatherReport
from src.utils.url_security import InvalidURL, validate_public_http_url

logger = logging.getLogger(__name__)

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

_DEFAULT_OVERFETCH_MULTIPLIER = 8

# 90% rule lives in SQL so DISTINCT-ON-equivalent dedup is never offered
# a sub-threshold partial as the "newest" row for a normalized_url. The
# subqueries against jsonb_each over `sections` are bounded (the dict is
# tiny — one entry per SectionSlug) so the cost is negligible.
#
# We deliberately do NOT push the privacy filter into SQL (the SSRF guard's
# IDNA + DNS-resolution checks don't translate cleanly), so the over-fetch
# multiplier handles the privacy rejection rate. The Python layer then
# dedups by normalized_url AFTER privacy filtering, picking the newest
# survivor per URL — which prevents a newer privacy-rejected duplicate
# from hiding an older qualifying one.
_RECENT_SQL = """
SELECT
    j.job_id,
    j.normalized_url,
    j.url AS source_url,
    j.finished_at,
    j.preview_description,
    j.sidebar_payload->'headline'->>'text' AS headline_summary_text,
    j.sidebar_payload->'weather_report' AS weather_report_json,
    j.sidebar_payload->'safety'->'recommendation' AS safety_recommendation_json,
    j.sections,
    j.status,
    j.page_title,
    s.screenshot_storage_key
FROM vibecheck_jobs j
INNER JOIN (
    -- TASK-1488.16: when both tier='scrape' and tier='interact' rows
    -- exist for the same normalized_url, the gallery must surface the
    -- interact-tier asset (Tier 2 success) rather than the cached
    -- interstitial that triggered the escalation. DISTINCT ON over
    -- the tier-priority ordering picks one viable row per URL,
    -- preferring 'interact' over 'scrape'. Filtering on viable rows
    -- (`screenshot_storage_key IS NOT NULL`, `expires_at > now()`)
    -- inside the subquery keeps an unviable interact row from
    -- shadowing a viable scrape row.
    SELECT DISTINCT ON (normalized_url)
        normalized_url,
        screenshot_storage_key,
        expires_at
    FROM vibecheck_scrapes
    WHERE screenshot_storage_key IS NOT NULL
      AND expires_at > now()
    ORDER BY normalized_url,
             CASE WHEN tier = 'interact' THEN 0 ELSE 1 END
) s ON s.normalized_url = j.normalized_url
WHERE j.status IN ('done', 'partial')
  AND (j.source_type IS NULL OR j.source_type = 'url')
  AND j.finished_at IS NOT NULL
  AND j.preview_description IS NOT NULL
  AND j.expired_at IS NULL
  AND s.screenshot_storage_key IS NOT NULL
  AND s.expires_at > now()
  AND (
    j.status = 'done'
    OR (
      j.status = 'partial'
      AND jsonb_typeof(j.sections) = 'object'
      AND (SELECT COUNT(*) FROM jsonb_each(j.sections)) > 0
      AND (
        SELECT COUNT(*) FILTER (
          WHERE jsonb_typeof(value) = 'object'
          AND value->>'state' = 'done'
        ) * 10
        FROM jsonb_each(j.sections)
      ) >= (
        SELECT COUNT(*) FROM jsonb_each(j.sections)
      ) * 9
    )
  )
ORDER BY j.finished_at DESC
LIMIT $1
"""

_RECENT_UNFILTERED_SQL = """
SELECT
    j.job_id,
    j.normalized_url,
    j.url AS source_url,
    j.finished_at,
    j.preview_description,
    j.sidebar_payload->'headline'->>'text' AS headline_summary_text,
    j.sidebar_payload->'weather_report' AS weather_report_json,
    j.sidebar_payload->'safety'->'recommendation' AS safety_recommendation_json,
    j.sections,
    j.status,
    j.page_title,
    s.screenshot_storage_key
FROM vibecheck_jobs j
INNER JOIN (
    SELECT DISTINCT ON (normalized_url)
        normalized_url,
        screenshot_storage_key,
        expires_at
    FROM vibecheck_scrapes
    WHERE screenshot_storage_key IS NOT NULL
      AND expires_at > now()
    ORDER BY normalized_url,
             CASE WHEN tier = 'interact' THEN 0 ELSE 1 END
) s ON s.normalized_url = j.normalized_url
WHERE j.status IN ('done', 'partial')
  AND (j.source_type IS NULL OR j.source_type = 'url')
  AND j.finished_at IS NOT NULL
  AND j.preview_description IS NOT NULL
  AND j.expired_at IS NULL
  AND s.screenshot_storage_key IS NOT NULL
  AND s.expires_at > now()
ORDER BY j.finished_at DESC
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


def _is_blocked_url(raw_url: str) -> bool:  # noqa: PLR0911
    """Apply the always-on privacy defaults.

    Composes the repo-wide SSRF guard `validate_public_http_url`
    (handles scheme/host/IDNA/IP-literal/suffix/private-resolving IP)
    with three gallery-specific checks the SSRF guard does not do:
    secret-shaped query params, explicit non-80/443 ports, and userinfo.

    Returns True (block) on any malformed URL — including malformed ports
    that would otherwise raise ValueError from `urlsplit().port` and
    propagate to the caller as a 500 (TASK-1485.06 P1.2).
    """
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return True
    if not parts.scheme or not parts.netloc:
        return True
    if _has_secret_query_param(parts.query):
        return True
    # Userinfo defense-in-depth — `user:pass@host` leaks creds in card UI.
    netloc_host_part = parts.netloc.split("/", 1)[0]
    if "@" in netloc_host_part:
        return True
    # Explicit non-safe port. `.port` raises ValueError on malformed input
    # (e.g. `https://host:abc/x`); without this guard a single bad DB row
    # would 500 the entire gallery (TASK-1485.06 P1.2).
    try:
        explicit_port = parts.port
    except ValueError:
        return True
    if explicit_port is not None and explicit_port not in _SAFE_PORTS:
        return True
    # Repo-wide SSRF guard: scheme allowlist, IDNA + trailing-dot, IP
    # literals (catches IPv4 octal/decimal/compressed via getaddrinfo),
    # blocked suffixes (.internal/.local), DNS resolution to non-private
    # IP. Bypasses Codex empirically verified before this change:
    # localhost., 127.1, 0177.0.0.1, 2130706433, [::ffff:127.0.0.1],
    # [fe80::1%25en0] — all now rejected.
    try:
        validate_public_http_url(raw_url)
    except InvalidURL:
        return True
    return False


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


def _weather_report_from_row(value: Any, *, job_id: UUID) -> WeatherReport | None:
    """Parse a weather_report JSONB column, tolerating schema drift.

    Pre-existing rows can carry weather payloads from older label sets. A
    raised ValidationError here would 500 the gallery for one bad row, so
    log and degrade to None instead — the caller still surfaces the row
    without a weather strip.
    """
    if value is None:
        return None
    data = json.loads(value) if isinstance(value, str) else value
    try:
        return WeatherReport.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "Invalid weather_report payload on job %s; surfacing row without "
            "weather strip. errors=%s",
            job_id,
            exc.errors(include_url=False, include_context=False),
        )
        return None


def _safety_recommendation_from_row(
    value: Any, *, job_id: UUID
) -> SafetyRecommendation | None:
    """Parse a safety recommendation JSONB column, tolerating schema drift.

    Pre-existing rows may carry safety payloads from older label sets. A
    raised ValidationError here would 500 the gallery for one bad row, so
    log and degrade to None instead — the caller still surfaces the row
    without a safety recommendation strip.
    """
    if value is None:
        return None
    data = json.loads(value) if isinstance(value, str) else value
    try:
        return SafetyRecommendation.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "Invalid safety recommendation payload on job %s; surfacing row without "
            "safety recommendation. errors=%s",
            job_id,
            exc.errors(include_url=False, include_context=False),
        )
        return None


def _recent_analysis_from_row(
    row: Any, *, signer: ScreenshotSigner
) -> RecentAnalysis | None:
    signed = signer.sign_screenshot_key(row["screenshot_storage_key"])
    if signed is None:
        return None
    return RecentAnalysis(
        job_id=row["job_id"],
        source_url=row["source_url"],
        page_title=row["page_title"],
        screenshot_url=signed,
        preview_description=row["preview_description"],
        headline_summary=row["headline_summary_text"],
        weather_report=_weather_report_from_row(
            row["weather_report_json"], job_id=row["job_id"]
        ),
        safety_recommendation=_safety_recommendation_from_row(
            row["safety_recommendation_json"], job_id=row["job_id"]
        ),
        completed_at=row["finished_at"],
    )


async def list_recent(
    pool: Any,
    *,
    limit: int,
    signer: ScreenshotSigner,
) -> list[RecentAnalysis]:
    """Return up to `limit` qualifying RecentAnalysis rows for the gallery.

    SQL emits rows ordered by finished_at DESC. The route iterates and
    keeps the FIRST surviving row per normalized_url after applying
    privacy + signer filters; this is dedup-after-filter, so a newer
    privacy-rejected row cannot hide an older qualifying row of the
    same normalized URL (TASK-1485.06 P1.1).

    The 90% threshold is enforced in SQL, so `_passes_partial_threshold`
    here is defensive only — it costs nothing on rows that already
    passed the SQL filter and prevents a future SQL-bug regression
    from leaking sub-threshold partials into the gallery.

    Over-fetch (`limit * 8`) gives the privacy filter headroom to drop
    rejection candidates without underfilling. A pathological deny rate
    would still underfill, but that's preferable to either (a) doing N
    DNS lookups per filter pass and growing super-linearly with rejection
    rate, or (b) re-querying when underfilled (re-query lacks pagination
    state and would return the same rows).
    """
    if limit <= 0:
        return []
    overfetch = max(limit * _DEFAULT_OVERFETCH_MULTIPLIER, limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_RECENT_SQL, overfetch)

    out: list[RecentAnalysis] = []
    seen_normalized: set[str] = set()
    for row in rows:
        normalized = row["normalized_url"]
        if normalized in seen_normalized:
            # A newer surviving row already represents this URL.
            continue
        if _is_blocked_url(row["source_url"]):
            # Don't claim the dedup slot — older qualifying duplicate may
            # still be in the candidate set.
            continue
        if not _passes_partial_threshold(row["sections"], row["status"]):
            continue
        recent_analysis = _recent_analysis_from_row(row, signer=signer)
        if recent_analysis is None:
            continue
        out.append(recent_analysis)
        seen_normalized.add(normalized)
        if len(out) >= limit:
            break
    return out


async def list_recent_unfiltered(
    pool: Any,
    *,
    limit: int,
    signer: ScreenshotSigner,
) -> list[RecentAnalysis]:
    """Return latest rows for the internal gallery without public filters."""
    if limit <= 0:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(_RECENT_UNFILTERED_SQL, limit)

    out: list[RecentAnalysis] = []
    for row in rows:
        recent_analysis = _recent_analysis_from_row(row, signer=signer)
        if recent_analysis is not None:
            out.append(recent_analysis)
    return out


__all__ = ["ScreenshotSigner", "list_recent", "list_recent_unfiltered"]
