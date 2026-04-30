"""POST /api/analyze — async job handoff (TASK-1473.11 rewrite).

The old synchronous pipeline moved into per-section workers (see
`src/jobs/` + the forthcoming orchestrator in TASK-1473.12). This handler's
job is now:

  1. Validate the URL (SSRF guard + normalization) — rejects on 400.
  2. Take a Postgres advisory xact lock keyed on `hashtext(normalized_url)`
     so concurrent submits for the same URL serialize at the DB layer.
     `pg_try_advisory_xact_lock` + one retry with a 1s gap keeps the
     critical path bounded; if contention persists with no in-flight row
     we 503 + Retry-After.
  3. Inside the locked transaction:
     a. Look up `vibecheck_analyses` within TTL — cache hit short-circuits
        with a `status=done` job row and `cached=true`.
     b. Look up any non-terminal `vibecheck_jobs` row for the same
        normalized_url — single-flight dedup returns the existing job_id.
     c. Fresh submit: INSERT a `pending` row with a freshly-minted
        `attempt_id` and commit.
  4. POST-commit: publish a Cloud Task via `enqueue_job`. If enqueue
     throws, UPDATE the just-inserted row to `status=failed,
     error_code=internal, error_message='enqueue failed'` and return 500
     so the caller sees the failure synchronously. Marking failed
     post-hoc (rather than rolling back the INSERT) preserves the
     observable job_id for log correlation and matches the spec's
     "visible failure card" UX.

The advisory lock is released automatically when the transaction commits
or rolls back, so nothing leaks on error.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.opinions._schemas import OpinionsReport, SentimentStatsReport
from src.analyses.safety._schemas import WebRiskFinding
from src.analyses.safety.web_risk import WebRiskTransientError, check_urls
from src.analyses.schemas import (
    FactsClaimsSection,
    JobState,
    JobStatus,
    OpinionsSection,
    PageKind,
    RecentAnalysis,
    SafetySection,
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
    ToneDynamicsSection,
    WebRiskSection,
)
from src.analyses.tone._scd_schemas import SCDReport
from src.cache.scrape_cache import canonical_cache_key
from src.config import Settings, get_settings
from src.jobs.enqueue import enqueue_job, enqueue_section_retry
from src.jobs.preview_description import (
    DerivationContext,
    derive_preview_description,
)
from src.jobs.recent_cache import _AsyncTTLCache, cache_key, is_cache_disabled
from src.jobs.recent_query import ScreenshotSigner, list_recent
from src.jobs.sidebar_payload import assemble_sidebar_payload
from src.jobs.slots import retry_claim_slot
from src.monitoring import get_logger
from src.monitoring_metrics import CACHE_HITS, SINGLE_FLIGHT_LOCK_WAITS
from src.utils.url_security import InvalidURL

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])

limiter = Limiter(key_func=get_remote_address)


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="HTTP(S) URL of the page to analyze")


class AnalyzeResponse(BaseModel):
    """202 handoff payload.

    The response shape is intentionally minimal: the client uses `job_id` to
    poll `GET /api/analyze/{job_id}` (TASK-1473.14) for progressive fill.
    `cached=true` signals that the pipeline was skipped because a fresh
    `vibecheck_analyses` row was already available — the polled job will
    reach `status=done` immediately.
    """

    job_id: UUID
    status: JobStatus
    cached: bool


def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a JSONResponse with a stable `error_code` slug at the top level.

    FastAPI's default HTTPException would wrap the body as `{"detail": ...}`
    — we want `{"error_code": ..., "message": ...}` so the frontend can
    branch on the slug without string-matching nested keys.
    """
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message},
        headers=headers,
    )


class _AnalyzeRouteError(Exception):
    """Carrier for `_error_response` payloads raised from helpers.

    Helpers like `_get_db_pool` and `_poll_rate_check` cannot return a
    JSONResponse to a route that promises a typed pydantic model, so they
    raise this exception and the route layer translates it back to the
    documented `{error_code, message}` body via `_error_response`. Direct
    `HTTPException` would wrap the payload as `{"detail": {...}}` which
    breaks the frontend's parseErrorBody contract (TASK-1473.38).
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"{status_code} {error_code}: {message}")
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.headers = headers

    def to_response(self) -> JSONResponse:
        return _error_response(
            self.status_code,
            self.error_code,
            self.message,
            headers=self.headers,
        )


def _host_of(normalized_url: str) -> str:
    """Extract host from the already-validated normalized URL.

    `validate_public_http_url` guarantees the netloc is present and
    IDNA-encoded, so a plain split is safe.
    """
    # scheme://host[:port]/path — netloc is between '://' and the next '/'.
    without_scheme = normalized_url.split("://", 1)[1]
    netloc = without_scheme.split("/", 1)[0]
    # Strip userinfo if any; strip port if any.
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if netloc.startswith("["):
        bracket_end = netloc.find("]")
        if bracket_end != -1:
            return netloc[1:bracket_end]
    if ":" in netloc:
        netloc = netloc.rsplit(":", 1)[0]
    return netloc


def _get_db_pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        # Missing pool is a deploy-time misconfiguration — surface as 503
        # with the same `{error_code, message}` body shape clients see for
        # all other errors (TASK-1473.38).
        raise _AnalyzeRouteError(503, "internal", "database pool not initialized")
    return pool


def _rate_limit_value() -> str:
    return f"{get_settings().RATE_LIMIT_PER_IP_PER_HOUR}/hour"


async def _try_advisory_lock(conn: Any, normalized_url: str) -> bool:
    """Try to acquire the pg advisory xact lock keyed on `hashtext(url)`.

    Returns the boolean result of `pg_try_advisory_xact_lock`. The lock
    is held for the remainder of the transaction.
    """
    return bool(
        await conn.fetchval("SELECT pg_try_advisory_xact_lock(hashtext($1))", normalized_url)
    )


async def _find_inflight_job(conn: Any, normalized_url: str) -> tuple[UUID, JobStatus] | None:
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


def _strip_job_scoped_cache_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop fields that are only valid for the job that generated the cache."""
    sanitized = dict(payload)
    sanitized.pop("utterances", None)
    return sanitized


_CACHE_PREVIEW_FALLBACK = "Analysis complete."


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
    finding: Any,
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
            url, normalized_url, host, status, attempt_id, test_fail_slug
        )
        VALUES ($1, $2, $3, 'pending', $4, $5)
        RETURNING job_id
        """,
        url,
        normalized_url,
        host,
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


async def _handle_locked_submit(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    unsafe_finding: WebRiskFinding | None,
    test_fail_slug: str | None = None,
) -> tuple[AnalyzeResponse, UUID | None]:
    """Run the inside-lock branch logic. Returns `(response, attempt_to_enqueue)`.

    `attempt_to_enqueue` is non-None only for fresh submits — cache hits
    and dedupe returns skip the Cloud Tasks publish.
    """
    if unsafe_finding is not None and unsafe_finding.threat_types:
        existing_unsafe = await _find_unsafe_url_job(conn, normalized_url)
        if existing_unsafe is not None:
            return (
                AnalyzeResponse(job_id=existing_unsafe, status=JobStatus.FAILED, cached=False),
                None,
            )
        job_id = await _insert_unsafe_url_job(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            finding=unsafe_finding,
        )
        return (
            AnalyzeResponse(job_id=job_id, status=JobStatus.FAILED, cached=False),
            None,
        )

    cached_payload = await _lookup_cache(conn, normalized_url)
    if cached_payload is not None:
        job_id = await _insert_cached_done_job(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            sidebar_payload=cached_payload,
        )
        CACHE_HITS.labels(tier="analysis").inc()
        return (
            AnalyzeResponse(job_id=job_id, status=JobStatus.DONE, cached=True),
            None,
        )

    existing = await _find_inflight_job(conn, normalized_url)
    if existing is not None:
        existing_job_id, existing_status = existing
        return (
            AnalyzeResponse(
                job_id=existing_job_id,
                status=existing_status,
                cached=False,
            ),
            None,
        )

    job_id, attempt_id = await _insert_pending_job(
        conn,
        url=url,
        normalized_url=normalized_url,
        host=host,
        test_fail_slug=test_fail_slug,
    )
    return (
        AnalyzeResponse(job_id=job_id, status=JobStatus.PENDING, cached=False),
        attempt_id,
    )


@router.post(
    "/analyze",
    status_code=202,
    response_model=AnalyzeResponse,
)
@limiter.limit(_rate_limit_value)
async def analyze(request: Request, body: AnalyzeRequest) -> Any:  # noqa: PLR0911
    """Async handoff for `POST /api/analyze`.

    Returns `AnalyzeResponse` on the success path. On SSRF-guard failure,
    advisory-lock contention, or a post-commit enqueue failure, returns a
    `JSONResponse` whose body shape is `{error_code, message}` and whose
    status mirrors the failure category (400, 503, 500 respectively). We
    return a response object (rather than raising HTTPException) so the
    body has a stable top-level `error_code` slug — `{"detail": ...}`
    would force the client to string-match.
    """
    settings = get_settings()

    # TASK-1473.35: e2e test hook. When the env flag is set the route
    # extracts X-Vibecheck-Test-Fail-Slug from the request and persists
    # it on the job row; the orchestrator's _run_section turns it into
    # a synthetic failure so Playwright can drive a real round-trip
    # retry. Default-off in production.
    test_fail_slug: str | None = None
    if settings.VIBECHECK_ALLOW_TEST_FAIL_HEADER:
        candidate = request.headers.get("X-Vibecheck-Test-Fail-Slug")
        if candidate:
            valid_slugs = {s.value for s in SectionSlug}
            if candidate in valid_slugs:
                test_fail_slug = candidate
            else:
                logger.info(
                    "ignoring X-Vibecheck-Test-Fail-Slug=%s (unknown slug)",
                    candidate,
                )

    # 1. SSRF guard + canonical normalization.
    # `canonical_cache_key` funnels `validate_public_http_url` (SSRF + public
    # host form) and then `normalize_url` (strip tracking params + trailing
    # slash). We key the advisory lock, cache lookup, in-flight dedup, and
    # job-row insert on this canonical form so `?utm_source=x` variants share
    # a dedup identity with the bare URL. Composing the two passes inline
    # would re-introduce the drift codex W4 P1 flagged — route through the
    # helper instead.
    if not body.url:
        return _error_response(400, "invalid_url", "url is required")
    try:
        normalized_url = canonical_cache_key(body.url)
    except InvalidURL as exc:
        logger.info("POST /api/analyze rejected url: reason=%s", exc.reason)
        return _error_response(400, "invalid_url", f"url rejected: {exc.reason}")

    host = _host_of(normalized_url)
    try:
        pool = _get_db_pool(request)
    except _AnalyzeRouteError as exc:
        return exc.to_response()

    # 2. Web Risk page-URL gate.
    async with httpx.AsyncClient(timeout=10.0) as hx:
        try:
            gate_findings = await check_urls(
                [normalized_url],
                pool=pool,
                httpx_client=hx,
                ttl_hours=settings.WEB_RISK_CACHE_TTL_HOURS,
            )
        except WebRiskTransientError:
            return _error_response(
                503,
                "rate_limited",
                "web risk scan temporarily unavailable",
                headers={"Retry-After": "5"},
            )
    page_finding = gate_findings.get(normalized_url)

    # 3. Locked DB transaction: cache-check -> dedup-check -> INSERT pending.
    async def run_locked() -> tuple[AnalyzeResponse | None, UUID | None, bool]:
        """Returns (response_or_None, attempt_to_enqueue, lock_acquired).

        `response_or_None` is None when the lock was NOT acquired and no
        existing in-flight row was found; the caller retries.
        """
        async with pool.acquire() as conn, conn.transaction():
            got_lock = await _try_advisory_lock(conn, normalized_url)
            if not got_lock:
                SINGLE_FLIGHT_LOCK_WAITS.inc()
                # Contended branch: another submitter holds the lock. Do a
                # non-locking cache check BEFORE falling back to in-flight
                # lookup — a fresh `vibecheck_analyses` row must still win
                # even if a stale non-terminal job row exists for the same
                # URL (codex W4 P2-1). Cache hit inserts a fresh done-job
                # row outside the contended lock; the race is benign because
                # `vibecheck_analyses` is the source of truth within TTL.
                cached_payload = await _lookup_cache(conn, normalized_url)
                if cached_payload is not None:
                    cached_job_id = await _insert_cached_done_job(
                        conn,
                        url=body.url,
                        normalized_url=normalized_url,
                        host=host,
                        sidebar_payload=cached_payload,
                    )
                    CACHE_HITS.labels(tier="analysis").inc()
                    return (
                        AnalyzeResponse(
                            job_id=cached_job_id,
                            status=JobStatus.DONE,
                            cached=True,
                        ),
                        None,
                        True,
                    )
                existing = await _find_inflight_job(conn, normalized_url)
                if existing is not None:
                    existing_job_id, existing_status = existing
                    return (
                        AnalyzeResponse(
                            job_id=existing_job_id,
                            status=existing_status,
                            cached=False,
                        ),
                        None,
                        True,
                    )
                if page_finding is not None and page_finding.threat_types:
                    existing_unsafe = await _find_unsafe_url_job(conn, normalized_url)
                    if existing_unsafe is not None:
                        return (
                            AnalyzeResponse(
                                job_id=existing_unsafe,
                                status=JobStatus.FAILED,
                                cached=False,
                            ),
                            None,
                            True,
                        )
                return None, None, False
            response, attempt = await _handle_locked_submit(
                conn,
                url=body.url,
                normalized_url=normalized_url,
                host=host,
                unsafe_finding=page_finding,
                test_fail_slug=test_fail_slug,
            )
            return response, attempt, True

    response, attempt_to_enqueue, got_lock = await run_locked()
    if not got_lock:
        # One retry per spec (bounded wait budget ~2s total).
        await asyncio.sleep(1.0)
        response, attempt_to_enqueue, got_lock = await run_locked()
    if not got_lock or response is None:
        # Still contended and no existing row to return — 503 + Retry-After.
        return _error_response(
            503,
            "rate_limited",
            "advisory lock contended; retry shortly",
            headers={"Retry-After": "2"},
        )

    # 3. Post-commit enqueue (fresh submits only).
    if attempt_to_enqueue is not None:
        try:
            await enqueue_job(response.job_id, attempt_to_enqueue, settings)
        except Exception as exc:
            logger.warning("enqueue_job failed for job %s: %s", response.job_id, exc)
            await _mark_job_failed_enqueue(pool, response.job_id)
            return _error_response(500, "internal", "enqueue failed")

    return JSONResponse(
        status_code=202,
        content=response.model_dump(mode="json"),
        headers={"X-Vibecheck-Job-Id": str(response.job_id)},
    )


# =========================================================================
# GET /api/analyze/{job_id} — polling endpoint (TASK-1473.14)
# =========================================================================
#
# Pure read: single SELECT with explicit projection, no mutation. The handler
# assembles a `JobState` from the row and a server-suggested `next_poll_ms`
# hint so the client's polling cadence adapts to lifecycle stage.
#
# Rate limiting uses a second Limiter instance keyed on the composite
# `(ip, job_id)` tuple so a client that polls one job aggressively does not
# starve their polls of another. Both a per-second burst and a per-minute
# sustained budget apply (slowapi stacks the decorators).
#
# We intentionally do NOT touch orphan detection here — pg_cron sweeps
# those via `vibecheck_sweep_orphan_jobs()`. The GET path is read-only so
# polling never produces writes that could race the sweeper.


def _ip_and_job_id_key(request: Request) -> str:
    """Composite slowapi key so the burst budget scopes to (ip, job_id)."""
    raw_job = request.path_params.get("job_id", "")
    return f"{get_remote_address(request)}:{raw_job}"


# A dedicated Limiter instance so the POST limiter's storage does not
# cross-contaminate the GET budget. Storage defaults to in-process memory,
# which matches slowapi's single-process Cloud Run deployment model.
#
# We construct our own `MovingWindowRateLimiter` backed by an in-memory
# storage so the poll handler can emit a Retry-After header on reject
# without tangling with slowapi's header-injection path (which assumes a
# Response-typed handler return and conflicts with pydantic response
# models). The Limiter wrapper is retained only for ergonomic storage
# construction — the actual check happens inline via `_poll_rate_check`.
poll_limiter = Limiter(key_func=_ip_and_job_id_key)

from limits import parse as _parse_limit  # noqa: E402  — kept near the consumers
from limits.aio.storage import MemoryStorage as _AsyncMemoryStorage  # noqa: E402
from limits.aio.strategies import (  # noqa: E402
    MovingWindowRateLimiter as _AsyncMovingWindowRateLimiter,
)

_poll_storage = _AsyncMemoryStorage()
_poll_strategy = _AsyncMovingWindowRateLimiter(_poll_storage)


def _poll_burst_limit_str() -> str:
    return f"{get_settings().RATE_LIMIT_POLL_BURST}/second"


def _poll_sustained_limit_str() -> str:
    return f"{get_settings().RATE_LIMIT_POLL_SUSTAINED}/minute"


async def _poll_rate_check(request: Request) -> None:
    """Enforce the composite (ip, job_id) rate budget.

    Raises `HTTPException(429, headers={"Retry-After": <seconds>})` when
    either the per-second burst or the per-minute sustained budget is
    exceeded. Both budgets share a single `(ip, job_id)` key so a burst
    hit triggers regardless of which window the client is inside.

    The inline implementation (rather than `@poll_limiter.limit`) is
    driven by slowapi's header-injection wrapper: it insists the
    decorated handler returns a starlette `Response` and also forces
    headers onto the success path. Doing the check here keeps the
    handler free to return a pydantic model and keeps Retry-After on
    the 429 only.

    Retry-After is computed from the moving window's reset timestamp so a
    client blocked by the 300/min bucket actually waits until the window
    slides (up to ~60s) — not the prior hardcoded `1s` that produced a
    60s hot-loop (codex W4 P2-3). Floor at 1 so we never emit
    `Retry-After: 0`; cap at the limit's window size so clock skew can't
    return a hostile value.
    """
    key = _ip_and_job_id_key(request)
    for limit_str in (_poll_burst_limit_str(), _poll_sustained_limit_str()):
        item = _parse_limit(limit_str)
        allowed = await _poll_strategy.hit(item, key)
        if not allowed:
            try:
                stats = await _poll_strategy.get_window_stats(item, key)
                # `+1` so a fractional-sub-second remainder (reset 0.3s away)
                # rounds up to a Retry-After of at least 1s.
                reset_in = int(stats.reset_time - time.time()) + 1
            except Exception:
                reset_in = 1
            # Window length = `multiples * granularity_seconds`. Computing
            # via `multiples` makes the cap correct for `300/minute` (60s
            # cap), `5/minute` (60s cap), or `2/30 second` (60s cap)
            # without relying on the parser surface that used to vary
            # across `limits` versions (TASK-1473.51).
            window_seconds = int(item.multiples) * int(item.GRANULARITY.seconds)
            reset_in = max(1, min(reset_in, window_seconds))
            raise _AnalyzeRouteError(
                429,
                "rate_limited",
                "poll rate exceeded",
                headers={"Retry-After": str(reset_in)},
            )


def poll_rate_reset() -> None:
    """Drop all in-process poll rate state. Used by tests between cases."""
    try:
        _poll_storage.storage.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        _poll_storage.events.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


# next_poll_ms ladder (spec AC#4):
#   pending   -> 500   (extraction has not started; fast re-poll)
#   extracting-> 500   (keep cadence tight during the short extract phase)
#   analyzing -> 1500  (long phase; back off to reduce DB load)
#   done      -> 0     (terminal — client stops polling)
#   partial   -> 0     (terminal — client stops polling)
#   failed    -> 0     (terminal — client stops polling)
_POLL_DELAY_BY_STATUS: dict[JobStatus, int] = {
    JobStatus.PENDING: 500,
    JobStatus.EXTRACTING: 500,
    JobStatus.ANALYZING: 1500,
    JobStatus.DONE: 0,
    JobStatus.PARTIAL: 0,
    JobStatus.FAILED: 0,
}

# Explicit projection — never SELECT * on this read path. See brief:
# the GET endpoint must pick exact columns so adding a new column to
# vibecheck_jobs doesn't silently widen the response and leak fields.
#
# Page metadata (page_title, page_kind) comes from vibecheck_job_utterances
# via a LEFT JOIN LATERAL ordered by position so both fields always come from
# the SAME utterance row. TASK-1473.60: the prior two unordered correlated
# subqueries could mix title from row A and kind from row B; after
# persist_utterances (1473.57) every row carries identical metadata so
# grabbing position-0 deterministically returns the payload's metadata.
# A job with zero utterance rows gets meta.page_title=NULL, meta.page_kind=NULL
# via the LEFT JOIN — the poll response treats both fields as absent.
# utterance_count remains a separate scalar subquery to avoid a GROUP BY.
# Codex W4 P2-2; defensive row.keys() checks in _row_to_job_state are now
# no-ops (LATERAL always projects the alias) but retained for safety.
_SELECT_JOB_SQL = """
SELECT
    j.job_id,
    j.url,
    j.status,
    j.attempt_id,
    j.error_code,
    j.error_message,
    j.error_host,
    j.sections,
    j.sidebar_payload,
    j.cached,
    j.created_at,
    j.updated_at,
    j.safety_recommendation,
    j.headline_summary,
    j.last_stage,
    j.heartbeat_at,
    meta.page_title,
    meta.page_kind,
    (
        SELECT COUNT(*)
        FROM vibecheck_job_utterances u
        WHERE u.job_id = j.job_id
    ) AS utterance_count
FROM vibecheck_jobs j
LEFT JOIN LATERAL (
    SELECT u.page_title, u.page_kind
    FROM vibecheck_job_utterances u
    WHERE u.job_id = j.job_id
    ORDER BY u.position
    LIMIT 1
) AS meta ON TRUE
WHERE j.job_id = $1
"""


def _parse_jsonb(raw: Any) -> Any:
    """asyncpg may hand back a JSON string or a pre-decoded value."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _parse_sections(raw: Any) -> dict[SectionSlug, SectionSlot]:
    """Parse the `sections` JSONB into typed SectionSlot per known slug.

    Unknown keys are dropped silently — the schema anchor only emits the
    seven documented slugs and the frontend must not branch on ad-hoc
    payloads that might appear mid-migration.
    """
    decoded = _parse_jsonb(raw) or {}
    if not isinstance(decoded, dict):
        return {}
    out: dict[SectionSlug, SectionSlot] = {}
    for slug in SectionSlug:
        entry = decoded.get(slug.value)
        if entry is None:
            continue
        out[slug] = SectionSlot.model_validate(entry)
    return out


_NON_TERMINAL_STATUSES_POLL = frozenset({"pending", "extracting", "analyzing"})


def _row_to_job_state(row: Any) -> JobState:
    status = JobStatus(row["status"])
    is_non_terminal = status.value in _NON_TERMINAL_STATUSES_POLL
    sections = _parse_sections(row["sections"])
    sidebar_raw = None if is_non_terminal else _parse_jsonb(row["sidebar_payload"])
    if status in {JobStatus.DONE, JobStatus.PARTIAL} and sidebar_raw is not None:
        sidebar_payload = SidebarPayload.model_validate(sidebar_raw)
        sidebar_payload_complete = True
    elif not is_non_terminal and sidebar_raw is not None:
        sidebar_payload = SidebarPayload.model_validate(sidebar_raw)
        sidebar_payload_complete = False
    elif is_non_terminal and any(
        slot.state == SectionState.DONE and slot.data is not None for slot in sections.values()
    ):
        sidebar_payload = assemble_sidebar_payload(
            row["url"],
            sections,
            safety_recommendation=row.get("safety_recommendation", None),
            headline_summary=row.get("headline_summary", None),
            utterances=[],
        )
        sidebar_payload_complete = False
    else:
        sidebar_payload = None
        sidebar_payload_complete = False

    page_kind_raw = row.get("page_kind", None)
    page_kind = PageKind(page_kind_raw) if isinstance(page_kind_raw, str) else None
    utterance_count_raw = row.get("utterance_count", 0)

    if is_non_terminal:
        activity_at = row.get("heartbeat_at", None)
        stage = row.get("last_stage", None)
        if stage is None and status is JobStatus.EXTRACTING:
            stage = "extracting"
        activity_label = _activity_label_for_stage(stage)
    else:
        activity_at = None
        activity_label = None

    return JobState(
        job_id=row["job_id"],
        url=row["url"],
        status=status,
        attempt_id=row["attempt_id"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        error_host=row["error_host"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        sections=sections,
        sidebar_payload=sidebar_payload,
        sidebar_payload_complete=sidebar_payload_complete,
        activity_at=activity_at,
        activity_label=activity_label,
        cached=bool(row["cached"]),
        next_poll_ms=_POLL_DELAY_BY_STATUS[status],
        page_title=row.get("page_title", None),
        page_kind=page_kind,
        utterance_count=int(utterance_count_raw or 0),
    )


_STAGE_LABEL_MAP: dict[str, str] = {
    "extracting": "Extracting page content",
    "persist_utterances": "Saving page content",
    "set_analyzing": "Preparing analysis",
    "run_sections": "Running section analyses",
    "safety_recommendation": "Computing safety guidance",
    "headline_summary": "Writing summary",
    "finalize": "Finalizing results",
}


def _activity_label_for_stage(stage: str | None) -> str | None:
    """Map internal last_stage keys to user-facing activity copy.

    Unknown stage values degrade to a neutral fallback so clients never
    surface raw internal keys in the UI (TASK-1473.65.10).
    """
    if stage is None:
        return None
    return _STAGE_LABEL_MAP.get(stage, "Running analysis")


@router.get(
    "/analyze/{job_id}",
    response_model=JobState,
    summary="Poll an async vibecheck job",
)
async def poll(job_id: UUID, request: Request, response: Response) -> JobState | JSONResponse:
    """Read-only polling endpoint.

    Returns the current `JobState` including the `sections` dict (per-slot
    progress), `sidebar_payload` once terminal, and a `next_poll_ms` hint.
    404 when `job_id` is not found. Rate-limited to
    `RATE_LIMIT_POLL_BURST` req/s + `RATE_LIMIT_POLL_SUSTAINED` req/min
    per `(ip, job_id)` tuple — exceeding either returns 429 with a
    `Retry-After` header.

    The return type is `JobState | JSONResponse` because the 404 / 429 /
    503 error paths emit `_error_response(...)` whose body is the
    documented `{error_code, message}` shape rather than the FastAPI
    default `{"detail": ...}` (TASK-1473.38).
    """
    try:
        await _poll_rate_check(request)
        pool = _get_db_pool(request)
    except _AnalyzeRouteError as exc:
        return exc.to_response()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_JOB_SQL, job_id)
    if row is None:
        return _error_response(404, "not_found", "job not found")
    response.headers["X-Vibecheck-Job-Id"] = str(job_id)
    return _row_to_job_state(row)


# =========================================================================
# POST /api/analyze/{job_id}/retry/{slug} — section retry (TASK-1473.13)
# =========================================================================
#
# Retry is a slot-scoped rotation: the public handler verifies the gate
# (job terminal + slot failed + utterances exist), CAS-flips the slot via
# `retry_claim_slot`, and enqueues a per-section Cloud Task. The heavy
# work happens in the internal worker target
# (`/_internal/jobs/{job_id}/sections/{slug}/run`).
#
# Rate limiting shares the poll endpoint's composite (ip, job_id) key so
# a client that mashes Retry doesn't starve its own poll budget on a
# different job. We use slowapi's `@limiter.limit` decorator with the
# same `_ip_and_job_id_key` key function as the GET poll bucket — both
# limits are per-hour with the configured POST budget so retry clicks
# count against the same bucket as fresh submits.
#
# Error-code slugs (stable for frontend branching, no string-matching):
#   not_found                               -> 404 (unknown job_id)
#   can_only_retry_after_extraction_succeeds -> 409 (no utterances)
#   cannot_retry_while_running               -> 409 (job is pending/extracting/analyzing)
#   slot_not_in_retryable_state              -> 409 (slot missing or not 'failed')
#   concurrent_retry_already_claimed         -> 409 (CAS lost to a concurrent click)
#   internal                                 -> 500 (post-CAS enqueue failure)


class RetryResponse(BaseModel):
    """202 handoff payload for a successful retry CAS."""

    job_id: UUID
    slug: SectionSlug
    slot_attempt_id: UUID


_LOAD_RETRY_STATE_SQL = """
SELECT
    j.status,
    j.sections -> $2::text AS slot,
    EXISTS (
        SELECT 1 FROM vibecheck_job_utterances u WHERE u.job_id = j.job_id
    ) AS has_utterances
FROM vibecheck_jobs j
WHERE j.job_id = $1
"""


async def _revert_slot_after_enqueue_failure(
    pool: Any,
    job_id: UUID,
    slug: SectionSlug,
    new_slot_attempt: UUID,
    prior_slot: dict[str, Any],
) -> None:
    """Restore a just-claimed retry slot to its prior failed snapshot.

    Narrowed from the previous `_mark_slot_failed_internal` (TASK-1473.47):
    that helper unconditionally flipped the entire job to
    `status=failed/error_code=internal/error_message='enqueue failed'`,
    wiping prior error context, prematurely declaring the job terminal,
    and (worst) clobbering a concurrent retry of a sibling slot that had
    already moved the job back to `analyzing`.

    The new contract: only the slot rotation is reverted, CAS-keyed on
    the new slot attempt_id so a concurrent worker that already advanced
    the slot is left alone. Job-level fields (`status`, `error_code`,
    `error_message`, `error_host`, `finished_at`) stay as `retry_claim_slot`
    set them. The orphan sweeper reclaims the job if no worker ever picks
    it up; sibling-slot retries continue to drive the job forward.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET sections = sections || jsonb_build_object($2::text, $3::jsonb),
                updated_at = now()
            WHERE job_id = $1
              AND sections ? $2::text
              AND sections -> $2::text ->> 'attempt_id' = $4::text
              AND status NOT IN ('done', 'partial', 'failed')
            """,
            job_id,
            slug.value,
            json.dumps(prior_slot),
            str(new_slot_attempt),
        )


@router.post(
    "/analyze/{job_id}/retry/{slug}",
    status_code=202,
    response_model=RetryResponse,
)
@limiter.limit(_rate_limit_value, key_func=_ip_and_job_id_key)
async def retry_section(  # noqa: PLR0911
    request: Request, job_id: UUID, slug: SectionSlug
) -> Any:
    """Retry one failed slot of a terminal job.

    Gate order (strict — each step assumes the prior one passed):
      1. Job must exist (404 otherwise).
      2. Utterances must have been extracted (409 otherwise — retry is
         meaningless if extraction itself failed; the user should resubmit).
      3. Job status must be terminal (`done`/`partial`/`failed`) — running phases
         get 409 `cannot_retry_while_running`.
      4. The requested slot must exist and be in `failed` state.
      5. CAS on the slot's prior attempt_id; a concurrent click loses
         with 409 `concurrent_retry_already_claimed`.
      6. Post-CAS enqueue. On failure revert the slot to `failed` and
         flip the job back to `failed/internal` — the user sees a stable
         error card instead of a phantom `analyzing` state.
    """
    try:
        pool = _get_db_pool(request)
    except _AnalyzeRouteError as exc:
        return exc.to_response()
    settings = get_settings()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOAD_RETRY_STATE_SQL, job_id, slug.value)

    if row is None:
        return _error_response(404, "not_found", "job not found")

    has_utterances = bool(row["has_utterances"])
    if not has_utterances:
        return _error_response(
            409,
            "can_only_retry_after_extraction_succeeds",
            "job has no utterances; resubmit the URL instead of retrying a slot",
        )

    status_raw = row["status"]
    if status_raw not in ("done", "partial", "failed"):
        return _error_response(
            409,
            "cannot_retry_while_running",
            f"job status={status_raw}; retry only after done/partial/failed",
        )

    slot_raw = row["slot"]
    slot_data = (
        json.loads(slot_raw)
        if isinstance(slot_raw, str)
        else (dict(slot_raw) if slot_raw is not None else None)
    )
    if slot_data is None or slot_data.get("state") != "failed":
        return _error_response(
            409,
            "slot_not_in_retryable_state",
            "target slot is not in 'failed' state",
        )

    try:
        prior_slot_attempt_id = UUID(str(slot_data["attempt_id"]))
    except (KeyError, ValueError, TypeError):
        # Defensive: a slot row without a parseable attempt_id cannot CAS.
        return _error_response(409, "slot_not_in_retryable_state", "slot missing attempt_id")

    new_slot_attempt = await retry_claim_slot(pool, job_id, slug, prior_slot_attempt_id)
    if new_slot_attempt is None:
        return _error_response(
            409,
            "concurrent_retry_already_claimed",
            "another retry click already rotated this slot",
        )

    try:
        await enqueue_section_retry(job_id, slug, new_slot_attempt, settings)
    except Exception as exc:
        logger.warning(
            "enqueue_section_retry failed for job %s slug %s: %s",
            job_id,
            slug.value,
            exc,
        )
        await _revert_slot_after_enqueue_failure(
            pool,
            job_id,
            slug,
            new_slot_attempt,
            prior_slot=slot_data,
        )
        return _error_response(500, "internal", "enqueue failed")

    return RetryResponse(job_id=job_id, slug=slug, slot_attempt_id=new_slot_attempt)


_recent_cache_singleton: _AsyncTTLCache[list[RecentAnalysis]] | None = None


def _get_recent_cache(settings: Settings) -> _AsyncTTLCache[list[RecentAnalysis]]:
    """Lazily build the in-process TTL cache.

    Sized to the configured TTL at first access. Tests reach for this via
    `_reset_recent_cache_for_testing` to drop state between cases.
    """
    global _recent_cache_singleton  # noqa: PLW0603
    if _recent_cache_singleton is None:
        _recent_cache_singleton = _AsyncTTLCache(
            ttl_seconds=settings.VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS
        )
    return _recent_cache_singleton


def _reset_recent_cache_for_testing() -> None:
    """Test-only hook so unit tests can verify TTL behavior deterministically."""
    global _recent_cache_singleton  # noqa: PLW0603
    _recent_cache_singleton = None


def _build_recent_signer() -> ScreenshotSigner:
    """Construct the per-request screenshot URL signer.

    Reuses the same factory that scrape-revival routes use so production
    wiring is identical. Tests inject a fake via `app.state.recent_signer`.
    """
    from src.routes.frame import get_scrape_cache  # noqa: PLC0415

    return get_scrape_cache()


@router.get(
    "/analyses/recent",
    response_model=list[RecentAnalysis],
    summary="Recently vibe checked gallery",
)
async def list_recent_analyses(request: Request) -> list[RecentAnalysis]:
    """Public, anon-accessible read of the latest qualifying analyses.

    Each card carries a 15-min signed screenshot URL, the page title (when
    extracted), a deterministic preview blurb, and the underlying job_id so
    cards link to /analyze?job=<id>. Inclusion: status='done', or
    status='partial' with >=90% of own-section keys done. Privacy defaults
    drop URLs with secret-shaped query strings, loopback/private hosts, or
    explicit non-80/443 ports — applied before cache so excluded rows
    cannot poison the cached payload.

    Wrapped in an in-process TTL cache (default 60s, validated < 900s so
    cached signed URLs cannot outlive their signature).
    """
    settings = get_settings()
    limit = settings.VIBECHECK_RECENT_ANALYSES_LIMIT
    if limit <= 0:
        return []

    pool = _get_db_pool(request)
    signer: ScreenshotSigner = (
        getattr(request.app.state, "recent_signer", None) or _build_recent_signer()
    )

    async def _load() -> list[RecentAnalysis]:
        return await list_recent(pool, limit=limit, signer=signer)

    if is_cache_disabled(limit):
        return await _load()

    cache = _get_recent_cache(settings)
    return await cache.get_or_load(cache_key(limit), _load)


__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "RetryResponse",
    "enqueue_job",
    "enqueue_section_retry",
    "limiter",
    "poll_limiter",
    "router",
]
