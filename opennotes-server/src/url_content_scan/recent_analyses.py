from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from inspect import isawaitable
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text

from src.utils.url_security import InvalidURL, validate_public_http_url

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
    slots.sections,
    j.status,
    s.page_title,
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


class RecentAnalysis(BaseModel):
    job_id: UUID = Field(description="batch_jobs.id for the analysis job.")
    source_url: str
    page_title: str | None = None
    screenshot_url: str = Field(description="Signed screenshot URL for the gallery card.")
    preview_description: str = Field(description="Short non-null gallery blurb.")
    completed_at: datetime


class ScreenshotSigner(Protocol):
    def sign_screenshot_key(self, storage_key: str | None) -> str | None: ...


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
        out.append(
            RecentAnalysis(
                job_id=row["job_id"],
                source_url=sanitized_source_url,
                page_title=row.get("page_title"),
                screenshot_url=signed,
                preview_description=preview_description,
                completed_at=row["finished_at"],
            )
        )
        seen_normalized.add(normalized)
        if len(out) >= limit:
            break

    return out


__all__ = [
    "_RECENT_SQL",
    "RecentAnalysis",
    "ScreenshotSigner",
    "_has_secret_query_param",
    "_is_blocked_url",
    "_passes_partial_threshold",
    "list_recent",
]
