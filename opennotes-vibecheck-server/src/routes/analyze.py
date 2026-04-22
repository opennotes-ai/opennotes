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
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.analyses.schemas import JobStatus
from src.config import get_settings
from src.jobs.enqueue import enqueue_job
from src.monitoring import get_logger
from src.utils.url_security import InvalidURL, validate_public_http_url

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
        # The handler's early-return path surfaces this as a 503 with the
        # `internal` slug — missing pool is a deploy-time misconfiguration.
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "internal",
                "message": "database pool not initialized",
            },
        )
    return pool


def _rate_limit_value() -> str:
    return f"{get_settings().RATE_LIMIT_PER_IP_PER_HOUR}/hour"


async def _try_advisory_lock(conn: Any, normalized_url: str) -> bool:
    """Try to acquire the pg advisory xact lock keyed on `hashtext(url)`.

    Returns the boolean result of `pg_try_advisory_xact_lock`. The lock
    is held for the remainder of the transaction.
    """
    return bool(
        await conn.fetchval(
            "SELECT pg_try_advisory_xact_lock(hashtext($1))", normalized_url
        )
    )


async def _find_inflight_job(conn: Any, normalized_url: str) -> UUID | None:
    """Return the job_id of a non-terminal job for this normalized_url, if any."""
    row = await conn.fetchval(
        """
        SELECT job_id FROM vibecheck_jobs
        WHERE normalized_url = $1
          AND status IN ('pending', 'extracting', 'analyzing')
        LIMIT 1
        """,
        normalized_url,
    )
    return row if isinstance(row, UUID) else None


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
    if isinstance(row, str):
        return json.loads(row)
    return dict(row)


async def _insert_cached_done_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
    sidebar_payload: dict[str, Any],
) -> UUID:
    """Insert a `status=done` job row populated from the cache."""
    job_id = await conn.fetchval(
        """
        INSERT INTO vibecheck_jobs (
            url, normalized_url, host, status, sidebar_payload, cached, finished_at
        )
        VALUES ($1, $2, $3, 'done', $4::jsonb, true, now())
        RETURNING job_id
        """,
        url,
        normalized_url,
        host,
        json.dumps(sidebar_payload),
    )
    assert isinstance(job_id, UUID)
    return job_id


async def _insert_pending_job(
    conn: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
) -> tuple[UUID, UUID]:
    """Insert a `status=pending` row and return `(job_id, attempt_id)`."""
    attempt_id = uuid4()
    job_id = await conn.fetchval(
        """
        INSERT INTO vibecheck_jobs (
            url, normalized_url, host, status, attempt_id
        )
        VALUES ($1, $2, $3, 'pending', $4)
        RETURNING job_id
        """,
        url,
        normalized_url,
        host,
        attempt_id,
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
) -> tuple[AnalyzeResponse, UUID | None]:
    """Run the inside-lock branch logic. Returns `(response, attempt_to_enqueue)`.

    `attempt_to_enqueue` is non-None only for fresh submits — cache hits
    and dedupe returns skip the Cloud Tasks publish.
    """
    cached_payload = await _lookup_cache(conn, normalized_url)
    if cached_payload is not None:
        job_id = await _insert_cached_done_job(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            sidebar_payload=cached_payload,
        )
        return (
            AnalyzeResponse(job_id=job_id, status=JobStatus.DONE, cached=True),
            None,
        )

    existing = await _find_inflight_job(conn, normalized_url)
    if existing is not None:
        return (
            AnalyzeResponse(
                job_id=existing, status=JobStatus.PENDING, cached=False
            ),
            None,
        )

    job_id, attempt_id = await _insert_pending_job(
        conn, url=url, normalized_url=normalized_url, host=host
    )
    return (
        AnalyzeResponse(
            job_id=job_id, status=JobStatus.PENDING, cached=False
        ),
        attempt_id,
    )


@router.post(
    "/analyze",
    status_code=202,
    response_model=AnalyzeResponse,
)
@limiter.limit(_rate_limit_value)
async def analyze(request: Request, body: AnalyzeRequest) -> Any:
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

    # 1. SSRF guard + normalization.
    if not body.url:
        return _error_response(400, "invalid_url", "url is required")
    try:
        normalized_url = validate_public_http_url(body.url)
    except InvalidURL as exc:
        logger.info("POST /api/analyze rejected url: reason=%s", exc.reason)
        return _error_response(
            400, "invalid_url", f"url rejected: {exc.reason}"
        )

    host = _host_of(normalized_url)
    pool = _get_db_pool(request)

    # 2. Locked DB transaction: cache-check -> dedup-check -> INSERT pending.
    async def run_locked() -> tuple[AnalyzeResponse | None, UUID | None, bool]:
        """Returns (response_or_None, attempt_to_enqueue, lock_acquired).

        `response_or_None` is None when the lock was NOT acquired and no
        existing in-flight row was found; the caller retries.
        """
        async with pool.acquire() as conn, conn.transaction():
            got_lock = await _try_advisory_lock(conn, normalized_url)
            if not got_lock:
                existing = await _find_inflight_job(conn, normalized_url)
                if existing is not None:
                    return (
                        AnalyzeResponse(
                            job_id=existing,
                            status=JobStatus.PENDING,
                            cached=False,
                        ),
                        None,
                        True,
                    )
                return None, None, False
            response, attempt = await _handle_locked_submit(
                conn,
                url=normalized_url,
                normalized_url=normalized_url,
                host=host,
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
            await enqueue_job(
                response.job_id, attempt_to_enqueue, settings
            )
        except Exception as exc:
            logger.warning(
                "enqueue_job failed for job %s: %s", response.job_id, exc
            )
            await _mark_job_failed_enqueue(pool, response.job_id)
            return _error_response(500, "internal", "enqueue failed")

    return response


__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "enqueue_job",
    "limiter",
    "router",
]
