"""Orchestrator for the async job pipeline (TASK-1473.12).

Called from the internal worker endpoint
(`POST /_internal/jobs/{job_id}/run`) once the OIDC dependency has accepted
the caller. The orchestrator is the single place that owns the pipeline
lifecycle:

    1. CAS-claim the job row by rotating `attempt_id` from pending->extracting.
       Stale redeliveries (whose `expected_attempt_id` no longer matches the
       row) are dropped silently — Cloud Tasks will not retry a 200 response.
    2. Spawn a heartbeat task that bumps `vibecheck_jobs.heartbeat_at` every
       `HEARTBEAT_INTERVAL_SEC` seconds while the pipeline runs. The sweeper
       watches heartbeat_at to reclaim orphaned jobs (.18 ticket).
    3. Scrape via Firecrawl (or hit the cache), revalidate the final URL via
       the SSRF guard (catching redirects into private space), extract
       utterances, then fan out to the ten per-section analysis slots via
       `asyncio.gather`.
    4. Finalize: `maybe_finalize_job` UPSERTs the `vibecheck_analyses` cache
       and flips the job status.

Error handling ladder (CTU + Cloud Tasks retry contract):

    TransientError        -> reset attempt_id + status=pending, return 503
                             (Cloud Tasks re-enqueues within retry config)
    TerminalError         -> status=failed + error_code/error_message, 200
                             (Cloud Tasks does NOT retry)
    any other Exception   -> log with exc_info, treat as transient (reset + 503)

`run_job` is the synchronous entrypoint the route handler awaits. The
route itself never sees exceptions — `run_job` returns a `RunResult` with
the HTTP status to emit. The heartbeat task is cancelled in every exit
path via try/finally so no background coroutine outlives the request.

Module-level constants (HEARTBEAT_INTERVAL_SEC) and factory hooks
(_build_scrape_cache, _build_firecrawl_client, _run_all_sections,
_run_pipeline) are the monkeypatch seams unit tests use; production code
paths call them directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from src.analyses.claims.dedupe_slot import run_claims_dedup
from src.analyses.claims.facts_agent import run_facts_claims_known_misinfo
from src.analyses.opinions.sentiment_slot import run_sentiment
from src.analyses.opinions.subjective_slot import run_subjective
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.safety.image_moderation_worker import run_image_moderation
from src.analyses.safety.moderation_slot import run_safety_moderation
from src.analyses.safety.recommendation_agent import (
    SafetyRecommendationInputs,
    run_safety_recommendation,
)
from src.analyses.safety.video_moderation_worker import run_video_moderation
from src.analyses.safety.web_risk_worker import run_web_risk
from src.analyses.schemas import ErrorCode, SectionSlot, SectionSlug, SectionState
from src.analyses.tone.flashpoint_slot import run_flashpoint
from src.analyses.tone.scd_slot import run_scd
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import FirecrawlClient
from src.jobs.finalize import maybe_finalize_job
from src.jobs.section_defaults import empty_section_data as _empty_section_data
from src.jobs.slots import mark_slot_done, mark_slot_failed, write_slot
from src.jobs.utterance_writes import (
    UtterancePersistenceSuperseded,
    persist_utterances,
)
from src.monitoring import bind_contextvars, clear_contextvars, get_logger
from src.monitoring_metrics import (
    ACTIVE_JOBS,
    CLOUD_TASKS_REDELIVERIES,
    JOB_DURATION,
    SECTION_DURATION,
    SECTION_FAILURES,
    classify_error,
)
from src.utils.url_security import InvalidURL, revalidate_redirect_target
from src.utterances.extractor import extract_utterances

logger = get_logger(__name__)


HEARTBEAT_INTERVAL_SEC: float = 5.0
"""Heartbeat bump cadence. Tests override to a shorter interval."""


class TransientError(Exception):
    """Retryable error — the handler resets the job row and returns 503."""


class TerminalError(Exception):
    """Non-retryable error with a classified `error_code`.

    The handler writes `status=failed`, `error_code`, and
    `error_message` to the job row and returns 200 so Cloud Tasks does
    not retry. Callers pass the stable `ErrorCode` enum; the message is
    free-form prose for log surfacing.
    """

    def __init__(self, error_code: ErrorCode, error_detail: str) -> None:
        super().__init__(error_detail)
        self.error_code = error_code
        self.error_detail = error_detail


class HandlerSuperseded(Exception):  # noqa: N818 — matches spec terminology; not raised as an "Error"
    """Raised when a mid-pipeline CAS guard detects the attempt rotated
    out from under us. The handler returns 200 and lets the newer worker
    own the job."""


@dataclass
class RunResult:
    """What the route handler emits after orchestration completes."""

    status_code: int
    """200 for success / terminal / superseded, 503 for transient."""


# ---------------------------------------------------------------------------
# Claim + reset helpers (CAS on `attempt_id`).
# ---------------------------------------------------------------------------

_CLAIM_SQL = """
UPDATE vibecheck_jobs
SET status = 'extracting',
    attempt_id = $2,
    heartbeat_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
  AND status = 'pending'
RETURNING attempt_id, url, test_fail_slug
"""

_RESET_SQL = """
UPDATE vibecheck_jobs
SET status = 'pending',
    attempt_id = $2,
    heartbeat_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""

_MARK_FAILED_SQL = """
UPDATE vibecheck_jobs
SET status = 'failed',
    error_code = $2,
    error_message = $3,
    finished_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $4
"""

_SET_ANALYZING_SQL = """
UPDATE vibecheck_jobs
SET status = 'analyzing',
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $2
"""

_HEARTBEAT_SQL = """
UPDATE vibecheck_jobs
SET heartbeat_at = now()
WHERE job_id = $1
  AND attempt_id = $2
"""

_LOAD_SAFETY_SECTIONS_SQL = """
SELECT sections
FROM vibecheck_jobs
WHERE job_id = $1
  AND attempt_id = $2
"""

_WRITE_SAFETY_RECOMMENDATION_SQL = """
UPDATE vibecheck_jobs
SET safety_recommendation = $2::jsonb,
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""


async def _claim_job(
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
) -> tuple[UUID, str, str | None] | None:
    """Atomically rotate attempt_id and set status=extracting.

    Returns (new_attempt_id, url, test_fail_slug) on success, None when
    the CAS fails (stale expected_attempt_id or status already moved).
    `test_fail_slug` is the e2e Playwright hook (TASK-1473.35);
    always-None in production where the env flag defaults off. Cloud
    Tasks redeliveries of a superseded enqueue fall into the None
    branch; the caller returns 200 no-op.
    """
    new_attempt = uuid4()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _CLAIM_SQL, job_id, new_attempt, expected_attempt_id
        )
    if row is None:
        return None
    return row["attempt_id"], row["url"], row["test_fail_slug"]


async def _reset_for_retry(
    pool: Any,
    job_id: UUID,
    *,
    task_attempt: UUID,
    expected_attempt_id: UUID,
) -> None:
    """Revert status to pending and restore the caller's envelope attempt_id.

    Cloud Tasks will retry with the *same* body payload (same
    expected_attempt_id), so the reset puts that value back in the row —
    the next delivery can re-claim cleanly.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            _RESET_SQL, job_id, expected_attempt_id, task_attempt
        )


async def _mark_failed(
    pool: Any,
    job_id: UUID,
    *,
    task_attempt: UUID,
    error_code: ErrorCode,
    error_message: str,
) -> None:
    """Flip the job row to status=failed with the classified error_code."""
    async with pool.acquire() as conn:
        await conn.execute(
            _MARK_FAILED_SQL,
            job_id,
            error_code.value,
            error_message,
            task_attempt,
        )


async def _set_analyzing(pool: Any, job_id: UUID, task_attempt: UUID) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SET_ANALYZING_SQL, job_id, task_attempt)


# ---------------------------------------------------------------------------
# Heartbeat loop.
# ---------------------------------------------------------------------------


async def _heartbeat_loop(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    *,
    interval_sec: float,
) -> None:
    """Periodically bump `heartbeat_at` while the pipeline runs.

    The loop exits via CancelledError when the pipeline returns. Each
    bump CAS-guards on `attempt_id = task_attempt` so a heartbeat from a
    stale worker cannot keep a reclaimed job's row looking fresh.
    """
    try:
        while True:
            await asyncio.sleep(interval_sec)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(_HEARTBEAT_SQL, job_id, task_attempt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A heartbeat that can't reach the DB shouldn't tear
                # down the pipeline — the sweeper will reclaim if
                # needed. Log and continue.
                logger.warning(
                    "heartbeat update failed for job %s: %s", job_id, exc
                )
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# Scrape + revalidate + extract.
# ---------------------------------------------------------------------------


def _build_scrape_cache(settings: Settings) -> SupabaseScrapeCache:
    """Factory seam so tests can inject a fake cache.

    In production this wires a real Supabase client against the configured
    URL + service-role key. The scrape cache tables are RLS-locked down
    to service_role (see src/cache/schema.sql header), so anon-keyed
    clients 42501 on every get/put. Fall back to anon if service_role
    isn't configured so dev envs without the lockdown keep working.

    Screenshot blobs live in GCS (`VIBECHECK_GCS_SCREENSHOT_BUCKET`); when
    unset (dev/test), the cache falls back to an in-memory store so the
    DB leg still works and `screenshot_storage_key` rows just stay null.
    """
    from supabase import create_client  # noqa: PLC0415

    from src.cache.screenshot_store import (  # noqa: PLC0415
        GCSScreenshotStore,
        InMemoryScreenshotStore,
        ScreenshotStore,
    )

    key = (
        settings.VIBECHECK_SUPABASE_SERVICE_ROLE_KEY
        or settings.VIBECHECK_SUPABASE_ANON_KEY
    )
    client = create_client(settings.VIBECHECK_SUPABASE_URL, key)
    store: ScreenshotStore
    if settings.VIBECHECK_GCS_SCREENSHOT_BUCKET:
        store = GCSScreenshotStore(settings.VIBECHECK_GCS_SCREENSHOT_BUCKET)
    else:
        store = InMemoryScreenshotStore()
    return SupabaseScrapeCache(client, store, ttl_hours=settings.CACHE_TTL_HOURS)


def _build_firecrawl_client(settings: Settings) -> FirecrawlClient:
    """Factory seam mirroring `_build_scrape_cache` above."""
    return FirecrawlClient(api_key=settings.FIRECRAWL_API_KEY)


async def _scrape_step(
    url: str,
    client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
) -> CachedScrape:
    """Cache-hit → return; miss → fetch + put.

    Returns the `CachedScrape` the caller will hand to `extract_utterances`.
    A failure in Firecrawl itself is TransientError (try again); a scrape
    that returns no markdown is TerminalError extraction_failed (the
    content is unparseable no matter how many times we retry).
    """
    cached = await scrape_cache.get(url)
    if cached is not None:
        return cached

    try:
        fresh = await client.scrape(
            url,
            formats=["markdown", "html", "screenshot@fullPage"],
            only_main_content=True,
        )
    except Exception as exc:
        raise TransientError(f"firecrawl scrape failed: {exc}") from exc

    try:
        return await scrape_cache.put(url, fresh)
    except Exception as exc:
        # DB upsert failed but we still have the fresh bundle. Fall back
        # to a keyless CachedScrape so the extractor's downstream reads
        # have usable markdown/html; next retry will re-upload.
        logger.warning("scrape cache put failed for %s: %s", url, exc)
        return CachedScrape(
            markdown=fresh.markdown,
            html=fresh.html,
            raw_html=fresh.raw_html,
            screenshot=fresh.screenshot,
            links=fresh.links,
            metadata=fresh.metadata,
            warning=fresh.warning,
            storage_key=None,
        )


async def _revalidate_final_url(
    scrape: CachedScrape,
    *,
    url: str,
    scrape_cache: SupabaseScrapeCache,
) -> None:
    """Post-scrape SSRF re-check (codex P1-3).

    Firecrawl follows redirects transparently, so `metadata.source_url` may
    point at a host we would never have accepted on the POST. Re-run the
    validator; on rejection, evict the cached scrape so a subsequent retry
    fetches fresh input rather than replaying the poisoned entry, then
    raise TerminalError invalid_url.
    """
    final = scrape.metadata.source_url if scrape.metadata else None
    if not final:
        return
    try:
        revalidate_redirect_target(final)
    except InvalidURL:
        try:
            await scrape_cache.evict(url)
        except Exception as exc:
            logger.warning(
                "scrape cache evict failed after redirect-block for %s: %s",
                url,
                exc,
            )
        raise TerminalError(
            ErrorCode.INVALID_URL, "redirect to private host"
        )


# ---------------------------------------------------------------------------
# Section fan-out stub.
# ---------------------------------------------------------------------------


async def _run_section(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    slug: SectionSlug,
    payload: Any,
    settings: Settings,
    *,
    test_fail_slug: str | None = None,
) -> None:
    """Run a single analysis slot and persist its output.

    Slugs registered in `_SECTION_HANDLERS` invoke the real analyzer and
    persist its returned payload. The empty-success fallback remains only
    as a defensive shape guard for future slugs during development.

    A slot failure is NOT a job failure: we call `mark_slot_failed` and
    return normally. `maybe_finalize_job` notices the failed slot later
    and waits (or the sweeper does) — terminal assembly happens only
    when every slot is done.

    `test_fail_slug` is the e2e Playwright hook (TASK-1473.35). When it
    matches `slug.value`, the handler is short-circuited and the slot is
    written as failed with a recognizable error string, letting the
    section-retry spec drive a real round-trip.
    """
    slot_attempt = uuid4()
    handler = _SECTION_HANDLERS.get(slug)
    slot_state = SectionState.DONE
    slot_error: str | None = None
    if test_fail_slug is not None and test_fail_slug == slug.value:
        slot_state = SectionState.FAILED
        slot_error = "synthetic test failure (X-Vibecheck-Test-Fail-Slug)"
        data: dict[str, Any] = {}
    elif handler is not None:
        try:
            data = await handler(pool, job_id, task_attempt, payload, settings)
        except Exception as exc:
            logger.exception(
                "section %s handler failed for job %s: %s",
                slug.value, job_id, exc,
            )
            slot_state = SectionState.FAILED
            slot_error = str(exc)
            data = {}
    else:
        data = _empty_section_data(slug)

    # write_slot (not mark_slot_failed) works for the terminal write here
    # because its CAS only checks job.attempt_id — no pre-existing slot row
    # required. mark_slot_failed requires slot.state='running' in the DB,
    # which _run_section never sets (it writes the terminal state directly).
    slot = SectionSlot(
        state=slot_state,
        attempt_id=slot_attempt,
        data=data if slot_state == SectionState.DONE else None,
        error=slot_error,
    )
    section_tokens = bind_contextvars(slug=slug)
    started = time.monotonic()
    try:
        try:
            rowcount = await write_slot(pool, job_id, task_attempt, slug, slot)
        except Exception as exc:
            logger.exception(
                "section %s failed for job %s: %s", slug.value, job_id, exc
            )
            SECTION_FAILURES.labels(
                slug=slug.value, error_type=classify_error(exc)
            ).inc()
            try:
                failed_rowcount = await mark_slot_failed(
                    pool,
                    job_id,
                    slug,
                    slot_attempt,
                    error=str(exc),
                    expected_task_attempt=task_attempt,
                )
                del failed_rowcount
            except Exception as mark_exc:
                logger.exception(
                    "section %s: mark_slot_failed also failed for job %s: %s",
                    slug.value, job_id, mark_exc,
                )
            raise TransientError(
                f"write_slot failed for job={job_id} slug={slug.value}: {exc}"
            ) from exc
        else:
            if rowcount == 0:
                raise TransientError(
                    f"write_slot CAS returned rowcount=0 for job={job_id} slug={slug.value}"
                )
        finally:
            SECTION_DURATION.labels(slug=slug.value).observe(
                time.monotonic() - started
            )
    finally:
        clear_contextvars(section_tokens)


_SECTION_HANDLERS: dict[SectionSlug, Any] = {
    SectionSlug.SAFETY_MODERATION: run_safety_moderation,
    SectionSlug.SAFETY_WEB_RISK: run_web_risk,
    SectionSlug.SAFETY_IMAGE_MODERATION: run_image_moderation,
    SectionSlug.SAFETY_VIDEO_MODERATION: run_video_moderation,
    SectionSlug.TONE_DYNAMICS_FLASHPOINT: run_flashpoint,
    SectionSlug.TONE_DYNAMICS_SCD: run_scd,
    SectionSlug.FACTS_CLAIMS_DEDUP: run_claims_dedup,
    SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: run_facts_claims_known_misinfo,
    SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: run_sentiment,
    SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: run_subjective,
}


async def _run_all_sections(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
    *,
    test_fail_slug: str | None = None,
) -> None:
    """Fan out every section in parallel; aggregate via `asyncio.gather`.

    Per-section handler failures are caught inside `_run_section` and
    persisted as a failed slot, so handler exceptions don't surface here.
    Anything that DOES surface — `TransientError` from a CAS-missed slot
    write, a DB pool exhaustion, etc. — must propagate so `run_job` can
    classify it (TransientError → 503 → Cloud Tasks redeliver). Previous
    `return_exceptions=True` discarded these silently and led to jobs
    that 200'd back to Cloud Tasks while leaving slots unwritten
    (TASK-1473.41).
    """
    await asyncio.gather(
        *[
            _run_section(
                pool, job_id, task_attempt, slug, payload, settings,
                test_fail_slug=test_fail_slug,
            )
            for slug in SectionSlug
        ],
    )


def _parse_sections(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def _done_slot_data(
    sections: dict[str, Any],
    slug: SectionSlug,
    unavailable_inputs: list[str],
    unavailable_name: str,
) -> dict[str, Any]:
    raw = sections.get(slug.value)
    if raw is None:
        unavailable_inputs.append(unavailable_name)
        return {}
    slot = SectionSlot.model_validate(raw)
    if slot.state != SectionState.DONE or slot.data is None:
        unavailable_inputs.append(unavailable_name)
        return {}
    return slot.data


def _build_safety_recommendation_inputs(
    sections: dict[str, Any],
) -> SafetyRecommendationInputs:
    unavailable_inputs: list[str] = []
    moderation_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_MODERATION,
        unavailable_inputs,
        "moderation",
    )
    web_risk_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_WEB_RISK,
        unavailable_inputs,
        "web_risk",
    )
    image_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_IMAGE_MODERATION,
        unavailable_inputs,
        "image_moderation",
    )
    video_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_VIDEO_MODERATION,
        unavailable_inputs,
        "video_moderation",
    )
    return SafetyRecommendationInputs(
        harmful_content_matches=[
            HarmfulContentMatch.model_validate(match)
            for match in moderation_data.get("harmful_content_matches", [])
        ],
        web_risk_findings=[
            WebRiskFinding.model_validate(finding)
            for finding in web_risk_data.get("findings", [])
        ],
        image_moderation_matches=[
            ImageModerationMatch.model_validate(match)
            for match in image_data.get("matches", [])
        ],
        video_moderation_matches=[
            VideoModerationMatch.model_validate(match)
            for match in video_data.get("matches", [])
        ],
        unavailable_inputs=unavailable_inputs,
    )


async def _run_safety_recommendation_step(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    settings: Settings,
) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOAD_SAFETY_SECTIONS_SQL, job_id, task_attempt)
    if row is None:
        return

    try:
        inputs = _build_safety_recommendation_inputs(_parse_sections(row["sections"]))
        recommendation = await run_safety_recommendation(inputs, settings)
    except Exception:
        logger.exception(
            "safety recommendation step failed for job %s attempt %s",
            job_id,
            task_attempt,
        )
        return

    recommendation_json = json.dumps(recommendation.model_dump(mode="json"))
    async with pool.acquire() as conn:
        await conn.execute(
            _WRITE_SAFETY_RECOMMENDATION_SQL,
            job_id,
            recommendation_json,
            task_attempt,
        )


# ---------------------------------------------------------------------------
# Pipeline body.
# ---------------------------------------------------------------------------


async def _run_pipeline(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    url: str,
    settings: Settings,
    *,
    test_fail_slug: str | None = None,
) -> None:
    """The scrape->extract->analyze sequence, error-classified.

    Isolated from the top-level `run_job` so unit tests can substitute an
    `AsyncMock` on this function to exercise the handler's error-handling
    without booting Firecrawl/Gemini/OpenAI.
    """
    scrape_cache = _build_scrape_cache(settings)
    client = _build_firecrawl_client(settings)

    # Scrape (cache or fresh).
    try:
        scrape = await _scrape_step(url, client, scrape_cache)
    except TransientError:
        raise
    except Exception as exc:
        raise TransientError(f"scrape step failed: {exc}") from exc

    # Post-scrape revalidate: reject redirects into private space.
    await _revalidate_final_url(scrape, url=url, scrape_cache=scrape_cache)

    # Extract utterances from the scrape bundle.
    try:
        payload = await extract_utterances(
            url, client, scrape_cache, settings=settings
        )
    except Exception as exc:
        # Extraction is a modeling failure, not a flake — don't retry
        # forever. Terminal so the UI surfaces a clear "we couldn't read
        # this page" error.
        raise TerminalError(
            ErrorCode.EXTRACTION_FAILED, f"extraction failed: {exc}"
        ) from exc

    try:
        await persist_utterances(pool, job_id, task_attempt, payload)
    except UtterancePersistenceSuperseded as exc:
        logger.info(
            "pipeline: utterance persistence superseded for job %s: %s",
            job_id, exc,
        )
        raise HandlerSuperseded() from exc

    # Flip status to analyzing before fan-out so the poll endpoint
    # returns the right cadence hint.
    await _set_analyzing(pool, job_id, task_attempt)

    # Fan out per-section analysis. Slot-level failures are written by
    # `_run_section` itself; this await only raises on orchestrator
    # infrastructure errors.
    await _run_all_sections(
        pool, job_id, task_attempt, payload, settings,
        test_fail_slug=test_fail_slug,
    )

    await _run_safety_recommendation_step(pool, job_id, task_attempt, settings)

    # Finalize: UPSERT the sidebar_payload cache if every slot is done.
    # When finalize returns False the job is intentionally NOT cached yet
    # (e.g. a slot is still in pending/running, attempt_id rotated, or the
    # job already moved to a terminal status owned by the error path).
    # Log so operators can correlate stuck jobs with the upstream cause —
    # the worker still returns 200 so Cloud Tasks doesn't redeliver
    # (TASK-1473.41).
    finalized = await maybe_finalize_job(
        pool, job_id, expected_task_attempt=task_attempt
    )
    if not finalized:
        logger.info(
            "maybe_finalize_job returned False after _run_all_sections "
            "for job %s (attempt %s) — slots not yet all done or attempt "
            "was rotated",
            job_id,
            task_attempt,
        )


# ---------------------------------------------------------------------------
# Top-level entrypoint.
# ---------------------------------------------------------------------------


async def run_job(
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
    settings: Settings,
) -> RunResult:
    """Drive one Cloud Tasks delivery through the pipeline.

    Returns a `RunResult` with the HTTP status the caller should emit:
    200 on success, stale-claim (no-op), or TerminalError (failed),
    503 on TransientError or any unclassified Exception.

    The heartbeat task is spawned after the claim and cancelled in
    `finally` so no background work outlives the handler's response.
    """
    claim = await _claim_job(pool, job_id, expected_attempt_id)
    if claim is None:
        # Stale redelivery — the job has already been picked up by a
        # fresher attempt, or the status moved on. 200 so Cloud Tasks
        # doesn't retry.
        CLOUD_TASKS_REDELIVERIES.inc()
        job_tokens = bind_contextvars(
            job_id=job_id, attempt_id=expected_attempt_id
        )
        try:
            logger.info(
                "worker: stale claim for job %s expected_attempt=%s — no-op",
                job_id,
                expected_attempt_id,
            )
        finally:
            clear_contextvars(job_tokens)
        return RunResult(status_code=200)

    task_attempt, url, test_fail_slug = claim
    job_tokens = bind_contextvars(job_id=job_id, attempt_id=task_attempt)
    heartbeat = asyncio.create_task(
        _heartbeat_loop(
            pool, job_id, task_attempt, interval_sec=HEARTBEAT_INTERVAL_SEC
        )
    )
    ACTIVE_JOBS.inc()
    started = time.monotonic()
    terminal_status = "done"

    try:
        try:
            await _run_pipeline(
                pool, job_id, task_attempt, url, settings,
                test_fail_slug=test_fail_slug,
            )
        except TransientError as exc:
            terminal_status = "pending"
            logger.warning(
                "worker: transient failure for job %s: %s", job_id, exc
            )
            await _reset_for_retry(
                pool,
                job_id,
                task_attempt=task_attempt,
                expected_attempt_id=expected_attempt_id,
            )
            return RunResult(status_code=503)
        except TerminalError as exc:
            terminal_status = "failed"
            logger.warning(
                "worker: terminal failure for job %s: error_code=%s detail=%s",
                job_id,
                exc.error_code.value,
                exc.error_detail,
            )
            await _mark_failed(
                pool,
                job_id,
                task_attempt=task_attempt,
                error_code=exc.error_code,
                error_message=exc.error_detail,
            )
            return RunResult(status_code=200)
        except HandlerSuperseded:
            # A mid-pipeline step detected the attempt rotated; nothing
            # else to do — the newer worker owns the row.
            terminal_status = "superseded"
            logger.info("worker: handler superseded for job %s", job_id)
            return RunResult(status_code=200)
        except Exception:
            # Unclassified — log with traceback so operators can see the
            # underlying bug, but treat as transient (reset + 503).
            terminal_status = "pending"
            logger.log(
                logging.ERROR,
                "worker: unclassified failure for job %s",
                job_id,
                exc_info=True,
            )
            await _reset_for_retry(
                pool,
                job_id,
                task_attempt=task_attempt,
                expected_attempt_id=expected_attempt_id,
            )
            return RunResult(status_code=503)

        return RunResult(status_code=200)
    finally:
        ACTIVE_JOBS.dec()
        JOB_DURATION.labels(status=terminal_status).observe(
            time.monotonic() - started
        )
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("heartbeat cancellation raised: %s", exc)
        clear_contextvars(job_tokens)


# ---------------------------------------------------------------------------
# Section-retry entrypoint (TASK-1473.13).
# ---------------------------------------------------------------------------


_LOAD_JOB_ATTEMPT_SQL = """
SELECT attempt_id, sections -> $2::text AS slot
FROM vibecheck_jobs
WHERE job_id = $1
"""


async def _load_job_attempt_and_slot(
    pool: Any,
    job_id: UUID,
    slug: SectionSlug,
) -> tuple[UUID, dict[str, Any]] | None:
    """Read the job's current `attempt_id` and the target slot JSON.

    Returns None when the job row is missing or the slot isn't present —
    the caller treats that as a stale redelivery and returns 200 no-op.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOAD_JOB_ATTEMPT_SQL, job_id, slug.value)
    if row is None:
        return None
    slot_raw = row["slot"]
    if slot_raw is None:
        return None
    import json as _json  # noqa: PLC0415

    slot = (
        _json.loads(slot_raw)
        if isinstance(slot_raw, str)
        else dict(slot_raw)
    )
    if not isinstance(row["attempt_id"], UUID):
        return None
    return row["attempt_id"], slot


async def run_section_retry(
    pool: Any,
    job_id: UUID,
    slug: SectionSlug,
    expected_slot_attempt_id: UUID,
    settings: Settings,
) -> RunResult:
    """Drive one section-retry Cloud Tasks delivery.

    Semantics:
      1. Load `(job.attempt_id, slot)`. Missing job or missing slot → 200
         idempotent no-op (a prune or re-submit happened after enqueue).
      2. If the slot's current attempt_id no longer matches
         `expected_slot_attempt_id`, or the slot is no longer `running`,
         a newer retry already claimed the slot. Return 200 no-op.
      3. Run the per-slug analysis. Registered handlers reload any persisted
         inputs they need from `vibecheck_job_utterances`.
      4. `mark_slot_done` with `expected_task_attempt=job.attempt_id`.
         If the CAS fails (stale job attempt, or job moved terminal out
         from under us), we return 200 no-op — the newer owner will
         handle finalization.
      5. `maybe_finalize_job(expected_task_attempt=job.attempt_id)`. If
         every slot is now `done`, the sidebar_payload cache is UPSERTed.
      6. Unclassified exceptions are treated as transient: write a failed
         slot (best-effort) and return 503 so Cloud Tasks retries.
    """
    retry_tokens = bind_contextvars(job_id=job_id, slug=slug)
    try:
        loaded = await _load_job_attempt_and_slot(pool, job_id, slug)
        if loaded is None:
            CLOUD_TASKS_REDELIVERIES.inc()
            logger.info(
                "section-retry: job or slot missing for job=%s slug=%s — no-op",
                job_id,
                slug.value,
            )
            return RunResult(status_code=200)
        task_attempt, slot = loaded
        attempt_tokens = bind_contextvars(attempt_id=task_attempt)

        try:
            slot_state = slot.get("state")
            slot_attempt_str = str(slot.get("attempt_id") or "")
            if slot_state != "running" or slot_attempt_str != str(expected_slot_attempt_id):
                CLOUD_TASKS_REDELIVERIES.inc()
                logger.info(
                    "section-retry: stale slot for job=%s slug=%s expected=%s "
                    "current=%s state=%s — no-op",
                    job_id,
                    slug.value,
                    expected_slot_attempt_id,
                    slot_attempt_str,
                    slot_state,
                )
                return RunResult(status_code=200)

            # TASK-1474.27: doubled per-section timeouts (e.g. video sampler
            # 60s download + 30s extract per video, x N videos) push a single
            # section retry well past the sweeper's 30s heartbeat window.
            # Mirror run_job's heartbeat lifecycle so the retry cannot be
            # marked stale mid-flight.
            heartbeat = asyncio.create_task(
                _heartbeat_loop(
                    pool,
                    job_id,
                    task_attempt,
                    interval_sec=HEARTBEAT_INTERVAL_SEC,
                )
            )
            section_started = time.monotonic()
            try:
                handler = _SECTION_HANDLERS.get(slug)
                if handler is None:
                    data = _empty_section_data(slug)
                else:
                    data = await handler(pool, job_id, task_attempt, None, settings)
                rows = await mark_slot_done(
                    pool,
                    job_id,
                    slug,
                    expected_slot_attempt_id,
                    data,
                    expected_task_attempt=task_attempt,
                )
                if rows == 0:
                    CLOUD_TASKS_REDELIVERIES.inc()
                    logger.info(
                        "section-retry: mark_slot_done CAS failed for job=%s slug=%s — no-op",
                        job_id,
                        slug.value,
                    )
                    return RunResult(status_code=200)

                await maybe_finalize_job(
                    pool, job_id, expected_task_attempt=task_attempt
                )
                return RunResult(status_code=200)
            except Exception as exc:
                SECTION_FAILURES.labels(
                    slug=slug.value, error_type=classify_error(exc)
                ).inc()
                logger.log(
                    logging.ERROR,
                    "section-retry: unclassified failure for job=%s slug=%s",
                    job_id,
                    slug.value,
                    exc_info=True,
                )
                try:
                    await mark_slot_failed(
                        pool,
                        job_id,
                        slug,
                        expected_slot_attempt_id,
                        error=str(exc),
                        expected_task_attempt=task_attempt,
                    )
                except Exception as inner:
                    logger.warning(
                        "section-retry: mark_slot_failed also raised for job=%s slug=%s: %s",
                        job_id,
                        slug.value,
                        inner,
                    )
                return RunResult(status_code=503)
            finally:
                SECTION_DURATION.labels(slug=slug.value).observe(
                    time.monotonic() - section_started
                )
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.warning(
                        "section-retry: heartbeat cancellation raised: %s", exc
                    )
        finally:
            clear_contextvars(attempt_tokens)
    finally:
        clear_contextvars(retry_tokens)


__all__ = [
    "HEARTBEAT_INTERVAL_SEC",
    "HandlerSuperseded",
    "RunResult",
    "TerminalError",
    "TransientError",
    "run_job",
    "run_section_retry",
]
