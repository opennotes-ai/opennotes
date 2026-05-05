"""Submit-path DB helpers for POST /api/analyze (TASK-1498.02)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.opinions._schemas import OpinionsReport, SentimentStatsReport
from src.analyses.safety._schemas import WebRiskFinding
from src.analyses.schemas import (
    FactsClaimsSection,
    JobStatus,
    OpinionsSection,
    SafetySection,
    SidebarPayload,
    ToneDynamicsSection,
    WebRiskSection,
)
from src.analyses.tone._scd_schemas import SCDReport
from src.jobs.preview_description import DerivationContext, derive_preview_description
from src.jobs.submit_schemas import SubmitResult
from src.monitoring import get_logger
from src.monitoring_metrics import CACHE_HITS

logger = get_logger(__name__)

_CACHE_PREVIEW_FALLBACK = "Analysis complete."


async def _find_inflight_job(
    conn: Any, normalized_url: str
) -> tuple[UUID, JobStatus] | None:
    """Return `(job_id, status)` of a non-terminal job for this URL, if any.

    Surfacing the real status (not a hardcoded `pending`) lets the dedup
    response report the lifecycle stage the existing worker is actually in
    — a client that polls immediately after getting back `extracting`
    avoids the fake-pending hot-loop that codex W4 P3 flagged.
    """
    row = await conn.fetchrow(
        """
        SELECT job_id, status FROM vibecheck_jobs
        WHERE normalized_url = $1
          AND status IN ('pending', 'extracting', 'analyzing')
        LIMIT 1
        """,
        normalized_url,
    )
    if row is None:
        return None
    job_id = row["job_id"]
    status_raw = row["status"]
    if not isinstance(job_id, UUID) or not isinstance(status_raw, str):
        return None
    return job_id, JobStatus(status_raw)


async def _find_unsafe_url_job(conn: Any, normalized_url: str) -> UUID | None:
    """Return an existing unsafe_url failure for this URL, if present."""
    job_id = await conn.fetchval(
        """
        SELECT job_id FROM vibecheck_jobs
        WHERE normalized_url = $1
          AND status = 'failed'
          AND error_code = 'unsafe_url'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        normalized_url,
    )
    return job_id if isinstance(job_id, UUID) else None


async def _lookup_cache(conn: Any, normalized_url: str) -> dict[str, Any] | None:
    """Return a fresh cached sidebar_payload if one exists within TTL."""
    row = await conn.fetchval(
        """
        SELECT sidebar_payload FROM vibecheck_analyses
        WHERE url = $1 AND expires_at > now()
        """,
        normalized_url,
    )
    if row is None:
        return None
    payload = json.loads(row) if isinstance(row, str) else dict(row)
    return _strip_job_scoped_cache_fields(payload)


def _payload_has_comment_refs(payload: dict[str, Any]) -> bool:
    return '"comment-' in json.dumps(payload)


def _strip_job_scoped_cache_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop fields that are only valid for the job that generated the cache."""
    sanitized = dict(payload)
    sanitized.pop("utterances", None)
    return sanitized


def _derive_cache_preview(sidebar_payload: dict[str, Any]) -> str:
    """Derive preview_description from a cached SidebarPayload dict.

    Cache-hit rows bypass `jobs/finalize.py` entirely (TASK-1485.02 AC#6),
    so the preview must be computed inline here. The cached payload's own
    `page_title` field feeds the fallback branch; first-utterance text
    isn't queried (the cache-hit path never extracted utterances on this
    submit), so the function tolerates None for that field.

    TASK-1485.06 P1.3: tolerate stale or malformed `vibecheck_analyses`
    rows from older code versions. SidebarPayload schemas have evolved
    over the lifetime of the cache (new fields, renamed fields, removed
    fields); rolling out this PR lights up validation for cache rows
    written by prior code. A failing model_validate must not 500 the
    POST /api/analyze hot path — instead degrade to a generic preview
    so the cached row still serves its primary purpose.
    """
    try:
        payload = SidebarPayload.model_validate(sidebar_payload)
    except (ValidationError, ValueError, TypeError) as exc:
        logger.warning(
            "cached SidebarPayload failed validation, using fallback preview: %s",
            exc,
        )
        return _CACHE_PREVIEW_FALLBACK
    ctx = DerivationContext(
        page_title=payload.page_title,
        first_utterance_text=None,
    )
    try:
        return derive_preview_description(payload, ctx)
    except Exception as exc:  # defensive: never 500 the cache-hit path
        logger.warning(
            "derive_preview_description failed on cached payload: %s",
            exc,
        )
        return _CACHE_PREVIEW_FALLBACK


async def _insert_cached_done_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    sidebar_payload: dict[str, Any],
) -> UUID:
    """Insert a `status=done` job row populated from the cache.

    Cooperates with the partial UNIQUE index
    `vibecheck_jobs_unique_done_cached_normalized_url` (TASK-1473.46) so
    two concurrent submitters losing the advisory lock can both fall into
    the contended cache-hit branch without producing duplicate cached
    done-job rows. The second INSERT hits ON CONFLICT DO NOTHING and the
    caller re-fetches the surviving row by normalized_url.

    `preview_description` (TASK-1485.02) is derived inline from the cached
    payload so cache-hit rows surface in the gallery alongside fresh
    finalized rows. Without this, cache-hits would land with NULL preview
    and the dedup-by-newest order could prefer them over fresh rows that
    do carry preview text.
    """
    preview_description = _derive_cache_preview(sidebar_payload)
    job_id = await conn.fetchval(
        """
        INSERT INTO vibecheck_jobs (
            url, normalized_url, host, status, sidebar_payload,
            preview_description, cached, finished_at
        )
        VALUES ($1, $2, $3, 'done', $4::jsonb, $5, true, now())
        ON CONFLICT (normalized_url)
            WHERE status = 'done' AND cached = true
            DO NOTHING
        RETURNING job_id
        """,
        url,
        normalized_url,
        host,
        json.dumps(sidebar_payload),
        preview_description,
    )
    if job_id is None:
        # Concurrent submitter beat us to the insert. Re-fetch the
        # surviving cached done row so the response carries a real job_id.
        job_id = await conn.fetchval(
            """
            SELECT job_id FROM vibecheck_jobs
            WHERE normalized_url = $1
              AND status = 'done'
              AND cached = true
            LIMIT 1
            """,
            normalized_url,
        )
    assert isinstance(job_id, UUID)
    return job_id


def _empty_safety_section() -> SafetySection:
    return SafetySection()


def _empty_tone_dynamics_section() -> ToneDynamicsSection:
    return ToneDynamicsSection(
        scd=SCDReport(summary="", insufficient_conversation=True),
        flashpoint_matches=[],
    )


def _empty_facts_claims_section() -> FactsClaimsSection:
    return FactsClaimsSection(
        claims_report=ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0),
        known_misinformation=[],
    )


def _empty_opinions_section() -> OpinionsSection:
    return OpinionsSection(
        opinions_report=OpinionsReport(
            sentiment_stats=SentimentStatsReport(
                per_utterance=[],
                positive_pct=0.0,
                negative_pct=0.0,
                neutral_pct=0.0,
                mean_valence=0.0,
            ),
            subjective_claims=[],
        )
    )


async def _insert_unsafe_url_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    finding: WebRiskFinding,
) -> UUID:
    job_id = uuid4()
    sidebar = SidebarPayload(
        source_url=url,
        scraped_at=datetime.now(UTC),
        safety=_empty_safety_section(),
        tone_dynamics=_empty_tone_dynamics_section(),
        facts_claims=_empty_facts_claims_section(),
        opinions_sentiments=_empty_opinions_section(),
        web_risk=WebRiskSection(findings=[finding]),
    )
    await conn.execute(
        """
        INSERT INTO vibecheck_jobs (
            job_id, url, normalized_url, host, status, attempt_id,
            error_code, error_message, sections, sidebar_payload,
            cached, created_at, updated_at, finished_at
        )
        VALUES (
            $1, $2, $3, $4, 'failed', $5,
            'unsafe_url', $6, '{}'::jsonb, $7::jsonb,
            false, now(), now(), now()
        )
        """,
        job_id,
        url,
        normalized_url,
        host,
        uuid4(),
        f"page URL flagged by Web Risk: {', '.join(finding.threat_types)}",
        json.dumps(sidebar.model_dump(mode="json")),
    )
    return job_id


async def _insert_pending_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    source_type: str = "url",
    test_fail_slug: str | None = None,
) -> tuple[UUID, UUID]:
    """Insert a `status=pending` row and return `(job_id, attempt_id)`.

    `test_fail_slug` is the orchestrator-side test hook for the
    Playwright section-retry spec (TASK-1473.35). Production submits
    leave it None — the route only persists a non-None value when the
    server is started with `VIBECHECK_ALLOW_TEST_FAIL_HEADER=1`.
    """
    attempt_id = uuid4()
    job_id = await conn.fetchval(
        """
        INSERT INTO vibecheck_jobs (
            url, normalized_url, host, source_type, status, attempt_id, test_fail_slug
        )
        VALUES ($1, $2, $3, $4, 'pending', $5, $6)
        RETURNING job_id
        """,
        url,
        normalized_url,
        host,
        source_type,
        attempt_id,
        test_fail_slug,
    )
    assert isinstance(job_id, UUID)
    return job_id, attempt_id


async def _mark_job_failed_enqueue(pool: Any, job_id: UUID) -> None:
    """Flip a just-inserted job row to `failed` after a failed enqueue."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET status = 'failed',
                error_code = 'internal',
                error_message = 'enqueue failed',
                updated_at = now(),
                finished_at = now()
            WHERE job_id = $1
            """,
            job_id,
        )


async def _find_source_job_with_utterances(
    conn: Any, normalized_url: str
) -> UUID | None:
    row = await conn.fetchrow(
        """
        SELECT j.job_id
        FROM vibecheck_jobs j
        WHERE j.normalized_url = $1
          AND j.status = 'done'
          AND j.cached = false
          AND EXISTS (
              SELECT 1 FROM vibecheck_job_utterances u
              WHERE u.job_id = j.job_id
                AND u.utterance_id LIKE 'comment-%'
          )
        ORDER BY j.finished_at DESC NULLS LAST
        LIMIT 1
        """,
        normalized_url,
    )
    if row is None:
        return None
    job_id = row["job_id"]
    return job_id if isinstance(job_id, UUID) else None


async def _copy_utterances_to_job(
    conn: Any, source_job_id: UUID, target_job_id: UUID
) -> None:
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM vibecheck_job_utterances WHERE job_id = $1",
        target_job_id,
    )
    if existing and existing > 0:
        return
    await conn.execute(
        """
        INSERT INTO vibecheck_job_utterances (
            job_id, utterance_id, kind, text, author, timestamp_at,
            parent_id, position, page_title, page_kind
        )
        SELECT
            $2, utterance_id, kind, text, author, timestamp_at,
            parent_id, position, page_title, page_kind
        FROM vibecheck_job_utterances
        WHERE job_id = $1
        """,
        source_job_id,
        target_job_id,
    )


async def _evict_url_cache(conn: Any, normalized_url: str) -> None:
    await conn.execute(
        "DELETE FROM vibecheck_analyses WHERE url = $1",
        normalized_url,
    )


async def _materialize_cache_hit(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    cached_payload: dict[str, Any],
) -> SubmitResult | None:
    """Handle a cache-hit submit.

    Returns a done SubmitResult on success.
    Returns None when the cache was evicted because it references comment-*
    utterances but no source job with matching rows exists — the caller should
    fall through to the pending-job path.
    """
    if _payload_has_comment_refs(cached_payload):
        source_job_id = await _find_source_job_with_utterances(conn, normalized_url)
        if source_job_id is None:
            await _evict_url_cache(conn, normalized_url)
            logger.info(
                "evicted stale analysis cache for %s: comment refs with no source utterances",
                normalized_url,
            )
            return None
        job_id = await _insert_cached_done_job(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            sidebar_payload=cached_payload,
        )
        await _copy_utterances_to_job(conn, source_job_id, job_id)
    else:
        job_id = await _insert_cached_done_job(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            sidebar_payload=cached_payload,
        )
    CACHE_HITS.labels(tier="analysis").inc()
    return SubmitResult(job_id=job_id, status=JobStatus.DONE, cached=True)


async def handle_locked_submit(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    source_type: str = "url",
    unsafe_finding: WebRiskFinding | None,
    test_fail_slug: str | None = None,
) -> tuple[SubmitResult, UUID | None]:
    """Run the inside-lock branch logic. Returns `(result, attempt_to_enqueue)`.

    `attempt_to_enqueue` is non-None only for fresh submits — cache hits
    and dedupe returns skip the Cloud Tasks publish.
    """
    if unsafe_finding is not None and unsafe_finding.threat_types:
        existing_unsafe = await _find_unsafe_url_job(conn, normalized_url)
        if existing_unsafe is not None:
            return SubmitResult(
                job_id=existing_unsafe,
                status=JobStatus.FAILED,
                cached=False,
            ), None
        job_id = await _insert_unsafe_url_job(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            finding=unsafe_finding,
        )
        return (
            SubmitResult(job_id=job_id, status=JobStatus.FAILED, cached=False),
            None,
        )

    if source_type == "url":
        cached_payload = await _lookup_cache(conn, normalized_url)
        if cached_payload is not None:
            result = await _materialize_cache_hit(
                conn,
                url=url,
                normalized_url=normalized_url,
                host=host,
                cached_payload=cached_payload,
            )
            if result is not None:
                return result, None
            # cache was evicted; fall through to pending

    existing = await _find_inflight_job(conn, normalized_url)
    if existing is not None:
        existing_job_id, existing_status = existing
        return (
            SubmitResult(job_id=existing_job_id, status=existing_status, cached=False),
            None,
        )

    job_id, attempt_id = await _insert_pending_job(
        conn,
        url=url,
        normalized_url=normalized_url,
        host=host,
        source_type=source_type,
        test_fail_slug=test_fail_slug,
    )
    return SubmitResult(job_id=job_id, status=JobStatus.PENDING, cached=False), attempt_id
