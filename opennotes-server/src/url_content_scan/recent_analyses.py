from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from inspect import isawaitable
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from src.url_content_scan.analyses.synthesis.weather_report_schemas import WeatherReport
from src.url_content_scan.safety_schemas import SafetyLevel, SafetyRecommendation
from src.utils.url_security import InvalidURL, validate_public_http_url

logger = logging.getLogger(__name__)

_HEADLINE_PREVIEW_MAX_LEN = 140
_ELLIPSIS = "…"

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

_RECENT_SQL_BODY = """
SELECT
    j.id AS job_id,
    st.normalized_url,
    st.source_url,
    COALESCE(st.finished_at, j.completed_at) AS finished_at,
    COALESCE(
        st.sidebar_payload #>> '{headline,text}',
        st.page_title
    ) AS preview_description,
    st.sidebar_payload #>> '{x_og_thumbnail}' AS x_og_thumbnail_url,
    st.sidebar_payload #>> '{headline,text}' AS headline_summary_text,
    st.sidebar_payload -> 'weather_report' AS weather_report_json,
    st.sidebar_payload -> 'safety' -> 'recommendation' AS safety_recommendation_json,
    slots.sections,
    j.status,
    st.page_title,
    st.page_kind,
    s.screenshot_storage_key
FROM batch_jobs j
INNER JOIN url_scan_state st
    ON st.job_id = j.id
INNER JOIN (
    SELECT
        job_id,
        jsonb_object_agg(
            slug,
            jsonb_build_object('state', lower(state))
        ) AS sections
    FROM url_scan_section_slots
    GROUP BY job_id
) slots ON slots.job_id = j.id
INNER JOIN (
    SELECT DISTINCT ON (normalized_url)
        normalized_url,
        page_title,
        screenshot_storage_key,
        expires_at
    FROM url_scan_scrapes
    WHERE screenshot_storage_key IS NOT NULL
      AND expires_at > now()
    ORDER BY normalized_url,
             CASE WHEN tier = 'interact' THEN 0 ELSE 1 END,
             scraped_at DESC
) s ON s.normalized_url = st.normalized_url
WHERE j.status IN ('completed', 'partial')
  AND COALESCE(st.finished_at, j.completed_at) IS NOT NULL
  AND st.deleted_at IS NULL
  AND (
    j.status = 'completed'
    OR (
      j.status = 'partial'
      AND EXISTS (
        SELECT 1
        FROM url_scan_section_slots uss
        WHERE uss.job_id = j.id
      )
      AND (
        SELECT COUNT(*) FILTER (WHERE lower(uss.state) = 'done') * 10
        FROM url_scan_section_slots uss
        WHERE uss.job_id = j.id
      ) >= (
        SELECT COUNT(*)
        FROM url_scan_section_slots uss
        WHERE uss.job_id = j.id
      ) * 9
    )
  )
ORDER BY COALESCE(st.finished_at, j.completed_at) DESC
"""
_RECENT_SQL = f"{_RECENT_SQL_BODY}\nLIMIT $1"
_RECENT_SQL_SQLALCHEMY = f"{_RECENT_SQL_BODY}\nLIMIT :limit"

_RECENT_UNFILTERED_SQL_BODY = """
SELECT
    j.id AS job_id,
    st.normalized_url,
    st.source_url,
    COALESCE(st.finished_at, j.completed_at) AS finished_at,
    COALESCE(
        st.sidebar_payload #>> '{headline,text}',
        st.page_title
    ) AS preview_description,
    st.sidebar_payload #>> '{x_og_thumbnail}' AS x_og_thumbnail_url,
    st.sidebar_payload #>> '{headline,text}' AS headline_summary_text,
    st.sidebar_payload -> 'weather_report' AS weather_report_json,
    st.sidebar_payload -> 'safety' -> 'recommendation' AS safety_recommendation_json,
    j.status,
    st.page_title,
    st.page_kind,
    s.screenshot_storage_key
FROM batch_jobs j
INNER JOIN url_scan_state st
    ON st.job_id = j.id
LEFT JOIN (
    SELECT DISTINCT ON (normalized_url)
        normalized_url,
        screenshot_storage_key,
        expires_at
    FROM url_scan_scrapes
    WHERE screenshot_storage_key IS NOT NULL
      AND expires_at > now()
    ORDER BY normalized_url,
             CASE WHEN tier = 'interact' THEN 0 ELSE 1 END,
             scraped_at DESC
) s ON s.normalized_url = st.normalized_url
WHERE j.status IN ('completed', 'partial')
  AND COALESCE(st.finished_at, j.completed_at) IS NOT NULL
  AND st.deleted_at IS NULL
ORDER BY COALESCE(st.finished_at, j.completed_at) DESC
"""
_RECENT_UNFILTERED_SQL = f"{_RECENT_UNFILTERED_SQL_BODY}\nLIMIT $1"
_RECENT_UNFILTERED_SQL_SQLALCHEMY = f"{_RECENT_UNFILTERED_SQL_BODY}\nLIMIT :limit"


class SafetyRowPreview(BaseModel):
    level: SafetyLevel = Field(description="Safety level: safe, caution, or unsafe.")


class RecentAnalysis(BaseModel):
    job_id: UUID = Field(description="batch_jobs.id for the analysis job.")
    source_url: str
    page_title: str | None = None
    screenshot_url: str = Field(description="Signed screenshot URL for the gallery card.")
    preview_description: str = Field(description="Short non-null gallery blurb.")
    og_thumbnail_url: str | None = Field(
        default=None,
        description="X (Twitter) OG thumbnail URL stored during scan; None for non-X URLs.",
    )
    headline_preview: str | None = Field(
        default=None,
        description="Truncated headline summary text from sidebar_payload; None when absent.",
    )
    weather_preview: str | None = Field(
        default=None,
        description=(
            "Compact weather-report label string (truth · relevance · sentiment); None when absent."
        ),
    )
    safety_row: SafetyRowPreview | None = Field(
        default=None,
        description="Minimal safety summary for gallery row; None when no recommendation stored.",
    )
    completed_at: datetime


class InternalRecentAnalysis(BaseModel):
    job_id: UUID = Field(description="batch_jobs.id for the analysis job.")
    source_url: str
    page_title: str | None = None
    screenshot_url: str | None = Field(
        default=None,
        description="Signed screenshot URL when available; None for jobs without a scrape.",
    )
    preview_description: str | None = Field(
        default=None,
        description="Gallery blurb when available; None if no headline or page title.",
    )
    og_thumbnail_url: str | None = Field(
        default=None,
        description="X (Twitter) OG thumbnail URL stored during scan; None for non-X URLs.",
    )
    headline_preview: str | None = Field(
        default=None,
        description="Truncated headline summary text from sidebar_payload; None when absent.",
    )
    weather_preview: str | None = Field(
        default=None,
        description=(
            "Compact weather-report label string (truth · relevance · sentiment); None when absent."
        ),
    )
    safety_row: SafetyRowPreview | None = Field(
        default=None,
        description="Minimal safety summary for gallery row; None when no recommendation stored.",
    )
    status: str = Field(description="batch_jobs.status (completed or partial).")
    completed_at: datetime


class ScreenshotSigner(Protocol):
    def sign_screenshot_key(self, storage_key: str | None) -> str | None: ...


def _truncate_preview(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    if len(text) <= _HEADLINE_PREVIEW_MAX_LEN:
        return text
    return text[: _HEADLINE_PREVIEW_MAX_LEN - 1].rstrip() + _ELLIPSIS


def _headline_preview_from_row(value: Any) -> str | None:
    if not value:
        return None
    truncated = _truncate_preview(str(value))
    return truncated if truncated else None


def _weather_preview_from_row(value: Any, *, job_id: UUID) -> str | None:
    if value is None:
        return None
    data = json.loads(value) if isinstance(value, str) else value
    try:
        report = WeatherReport.model_validate(data)
    except ValidationError:
        logger.warning(
            "Invalid weather_report payload on job %s; omitting weather_preview.",
            job_id,
        )
        return None
    return f"{report.truth.label} · {report.relevance.label} · {report.sentiment.label}"


def _safety_row_from_row(value: Any, *, job_id: UUID) -> SafetyRowPreview | None:
    if value is None:
        return None
    data = json.loads(value) if isinstance(value, str) else value
    try:
        rec = SafetyRecommendation.model_validate(data)
    except ValidationError:
        logger.warning(
            "Invalid safety recommendation payload on job %s; omitting safety_row.",
            job_id,
        )
        return None
    return SafetyRowPreview(level=rec.level)


def _has_secret_query_param(query: str) -> bool:
    if not query:
        return False
    parsed = parse_qs(query, keep_blank_values=True)
    return any(key.lower() in _SECRET_QUERY_PARAM_KEYS for key in parsed)


def _sanitize_recent_source_url(raw_url: str) -> str | None:
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return None
    blocked = not parts.scheme or not parts.netloc or _has_secret_query_param(parts.query)
    netloc_host_part = parts.netloc.split("/", 1)[0]
    blocked = blocked or "@" in netloc_host_part
    explicit_port: int | None
    try:
        explicit_port = parts.port
    except ValueError:
        blocked = True
        explicit_port = None
    blocked = blocked or (explicit_port is not None and explicit_port not in _SAFE_PORTS)
    if blocked:
        return None
    try:
        return validate_public_http_url(raw_url)
    except InvalidURL:
        return None


def _is_blocked_url(raw_url: str) -> bool:
    return _sanitize_recent_source_url(raw_url) is None


def _passes_partial_threshold(sections_raw: Any, status: str) -> bool:
    if status == "completed":
        return True
    if status != "partial":
        return False
    if isinstance(sections_raw, str):
        sections = json.loads(sections_raw)
    elif isinstance(sections_raw, Mapping):
        sections = dict(sections_raw)
    else:
        sections = dict(sections_raw or {})
    total = len(sections)
    if total == 0:
        return False
    done = sum(
        1
        for value in sections.values()
        if isinstance(value, Mapping) and str(value.get("state", "")).lower() == "done"
    )
    return done * 10 >= total * 9


async def _fetch_rows(pool_or_session: Any, *, overfetch: int) -> list[Mapping[str, Any]]:
    if hasattr(pool_or_session, "acquire"):
        async with pool_or_session.acquire() as conn:
            rows = await conn.fetch(_RECENT_SQL, overfetch)
            return [dict(row) for row in rows]
    if hasattr(pool_or_session, "fetch"):
        rows = await pool_or_session.fetch(_RECENT_SQL, overfetch)
        return [dict(row) for row in rows]
    if hasattr(pool_or_session, "execute"):
        result = await pool_or_session.execute(text(_RECENT_SQL_SQLALCHEMY), {"limit": overfetch})
        return [dict(row) for row in result.mappings().all()]
    raise TypeError(
        "list_recent requires an asyncpg-style pool/connection or SQLAlchemy async session"
    )


async def list_recent(
    pool_or_session: Any,
    *,
    limit: int,
    signer: ScreenshotSigner,
) -> list[RecentAnalysis]:
    if limit <= 0:
        return []

    overfetch = max(limit * _DEFAULT_OVERFETCH_MULTIPLIER, limit)
    rows = await _fetch_rows(pool_or_session, overfetch=overfetch)

    out: list[RecentAnalysis] = []
    seen_normalized: set[str] = set()
    for row in rows:
        if row.get("deleted_at") is not None:
            continue
        normalized = str(row["normalized_url"])
        if normalized in seen_normalized:
            continue
        source_url = str(row["source_url"])
        sanitized_source_url = _sanitize_recent_source_url(source_url)
        if sanitized_source_url is None:
            continue
        if not _passes_partial_threshold(row.get("sections"), str(row["status"])):
            continue
        signed_result = signer.sign_screenshot_key(row.get("screenshot_storage_key"))
        signed = await signed_result if isawaitable(signed_result) else signed_result
        if signed is None:
            continue
        raw_preview_description = row.get("preview_description") or row.get("page_title")
        preview_description = (
            sanitized_source_url
            if str(raw_preview_description or "") == source_url
            else str(raw_preview_description or sanitized_source_url)
        )
        raw_og_thumbnail = row.get("x_og_thumbnail_url")
        og_thumbnail_url = str(raw_og_thumbnail) if raw_og_thumbnail else None
        job_id: UUID = row["job_id"]
        out.append(
            RecentAnalysis(
                job_id=job_id,
                source_url=sanitized_source_url,
                page_title=row.get("page_title"),
                screenshot_url=signed,
                preview_description=preview_description,
                og_thumbnail_url=og_thumbnail_url,
                headline_preview=_headline_preview_from_row(row.get("headline_summary_text")),
                weather_preview=_weather_preview_from_row(
                    row.get("weather_report_json"), job_id=job_id
                ),
                safety_row=_safety_row_from_row(
                    row.get("safety_recommendation_json"), job_id=job_id
                ),
                completed_at=row["finished_at"],
            )
        )
        seen_normalized.add(normalized)
        if len(out) >= limit:
            break

    return out


async def _fetch_rows_unfiltered(pool_or_session: Any, *, limit: int) -> list[Mapping[str, Any]]:
    if hasattr(pool_or_session, "acquire"):
        async with pool_or_session.acquire() as conn:
            rows = await conn.fetch(_RECENT_UNFILTERED_SQL, limit)
            return [dict(row) for row in rows]
    if hasattr(pool_or_session, "fetch"):
        rows = await pool_or_session.fetch(_RECENT_UNFILTERED_SQL, limit)
        return [dict(row) for row in rows]
    if hasattr(pool_or_session, "execute"):
        result = await pool_or_session.execute(
            text(_RECENT_UNFILTERED_SQL_SQLALCHEMY), {"limit": limit}
        )
        return [dict(row) for row in result.mappings().all()]
    raise TypeError(
        "list_recent_unfiltered requires an asyncpg-style pool/connection or SQLAlchemy async session"
    )


async def list_recent_unfiltered(
    pool_or_session: Any,
    *,
    limit: int,
    signer: ScreenshotSigner,
) -> list[InternalRecentAnalysis]:
    if limit <= 0:
        return []

    rows = await _fetch_rows_unfiltered(pool_or_session, limit=limit)

    out: list[InternalRecentAnalysis] = []
    for row in rows:
        storage_key = row.get("screenshot_storage_key")
        signed_url: str | None = None
        if storage_key:
            signed_result = signer.sign_screenshot_key(storage_key)
            signed_url = await signed_result if isawaitable(signed_result) else signed_result
        raw_og_thumbnail = row.get("x_og_thumbnail_url")
        og_thumbnail_url = str(raw_og_thumbnail) if raw_og_thumbnail else None
        raw_preview = row.get("preview_description")
        preview_description = str(raw_preview) if raw_preview else None
        job_id: UUID = row["job_id"]
        out.append(
            InternalRecentAnalysis(
                job_id=job_id,
                source_url=str(row["source_url"]),
                page_title=row.get("page_title"),
                screenshot_url=signed_url,
                preview_description=preview_description,
                og_thumbnail_url=og_thumbnail_url,
                headline_preview=_headline_preview_from_row(row.get("headline_summary_text")),
                weather_preview=_weather_preview_from_row(
                    row.get("weather_report_json"), job_id=job_id
                ),
                safety_row=_safety_row_from_row(
                    row.get("safety_recommendation_json"), job_id=job_id
                ),
                status=str(row["status"]),
                completed_at=row["finished_at"],
            )
        )

    return out


__all__ = [
    "_RECENT_SQL",
    "_RECENT_UNFILTERED_SQL",
    "InternalRecentAnalysis",
    "RecentAnalysis",
    "SafetyRowPreview",
    "ScreenshotSigner",
    "_has_secret_query_param",
    "_is_blocked_url",
    "_passes_partial_threshold",
    "list_recent",
    "list_recent_unfiltered",
]
