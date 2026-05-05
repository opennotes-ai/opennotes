from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from inspect import isawaitable
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobStatus
from src.dbos_workflows.url_scan_workflow import dispatch_url_scan_workflow
from src.url_content_scan.analyses.safety.web_risk import run_pre_enqueue_web_risk
from src.url_content_scan.models import (
    UrlScanSectionSlot,
    UrlScanSidebarCache,
    UrlScanState,
    UrlScanWebRiskLookup,
)
from src.url_content_scan.normalize import canonical_cache_key
from src.url_content_scan.safety_schemas import WebRiskFinding
from src.url_content_scan.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ErrorCode,
    FactsClaimsSection,
    JobStatus,
    OpinionsSection,
    PageKind,
    SafetySection,
    SectionSlug,
    SidebarPayload,
    ToneDynamicsSection,
    WebRiskSection,
)
from src.utils.url_security import InvalidURL, validate_public_http_url

_LOCK_RETRY_DELAY_SECONDS = 1.0
_URL_SCAN_JOB_TYPE = "url_scan"
_LOCK_SQL = text("SELECT pg_try_advisory_xact_lock(hashtext(:normalized_url))")
_NONTERMINAL_BATCH_STATUSES = (
    BatchJobStatus.PENDING.value,
    BatchJobStatus.IN_PROGRESS.value,
    BatchJobStatus.EXTRACTING.value,
    BatchJobStatus.ANALYZING.value,
)
_WEB_RISK_LOOKUP_TTL = timedelta(hours=24)


class AnalyzeSubmissionError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.headers = headers or {}


class _SleepFn(Protocol):
    async def __call__(self, delay: float) -> None: ...


class _DispatchFn(Protocol):
    async def __call__(
        self,
        job_id: UUID,
        source_url: str,
        normalized_url: str,
        attempt_id: UUID,
    ) -> str | None: ...


class _WebRiskFn(Protocol):
    def __call__(self, url: str) -> Any: ...


@dataclass(slots=True)
class _LockedSubmitResult:
    response: AnalyzeResponse
    dispatch_job_id: UUID | None = None
    dispatch_attempt_id: UUID | None = None


async def submit_url_scan(
    session: AsyncSession,
    request: Request,
    payload: AnalyzeRequest,
    *,
    dispatch: _DispatchFn = dispatch_url_scan_workflow,
    web_risk: _WebRiskFn = run_pre_enqueue_web_risk,
    sleep: _SleepFn = asyncio.sleep,
) -> AnalyzeResponse:
    safe_url, normalized_url, host = _canonicalize_submission_url(payload.url)

    locked_result: _LockedSubmitResult | None = None
    got_lock = False
    for attempt in range(2):
        async with session.begin():
            got_lock = await _try_advisory_lock(session, normalized_url)
            if got_lock:
                locked_result = await _handle_locked_submit(
                    session,
                    request=request,
                    source_url=safe_url,
                    normalized_url=normalized_url,
                    host=host,
                    web_risk=web_risk,
                )
        if got_lock:
            break
        if attempt == 0:
            await sleep(_LOCK_RETRY_DELAY_SECONDS)

    if not got_lock or locked_result is None:
        raise AnalyzeSubmissionError(
            503,
            ErrorCode.RATE_LIMITED,
            "advisory lock contended; retry shortly",
            headers={"Retry-After": "2"},
        )

    if locked_result.dispatch_job_id is not None and locked_result.dispatch_attempt_id is not None:
        try:
            workflow_id = await dispatch(
                locked_result.dispatch_job_id,
                safe_url,
                normalized_url,
                locked_result.dispatch_attempt_id,
            )
            if workflow_id is None:
                raise RuntimeError("dispatch returned no workflow id")
        except Exception as exc:
            await _mark_dispatch_failure(session, locked_result.dispatch_job_id, str(exc))
            raise AnalyzeSubmissionError(
                500,
                ErrorCode.INTERNAL,
                "failed to dispatch url scan workflow",
            ) from exc

    return locked_result.response


def _canonicalize_submission_url(raw_url: str) -> tuple[str, str, str]:
    try:
        safe_url = validate_public_http_url(raw_url)
        normalized_url = canonical_cache_key(safe_url)
    except InvalidURL as exc:
        raise AnalyzeSubmissionError(
            400,
            ErrorCode.INVALID_URL,
            f"url rejected: {exc.reason}",
        ) from exc
    return safe_url, normalized_url, _host_of(normalized_url)


def _host_of(normalized_url: str) -> str:
    return urlparse(normalized_url).hostname or ""


async def _try_advisory_lock(session: AsyncSession, normalized_url: str) -> bool:
    result = await session.execute(_LOCK_SQL, {"normalized_url": normalized_url})
    return bool(result.scalar_one())


async def _handle_locked_submit(
    session: AsyncSession,
    *,
    request: Request,
    source_url: str,
    normalized_url: str,
    host: str,
    web_risk: _WebRiskFn,
) -> _LockedSubmitResult:
    unsafe_finding = await _run_web_risk_lookup(web_risk, source_url, session)
    if unsafe_finding is not None and unsafe_finding.threat_types:
        existing_job_id = await _find_existing_unsafe_job(session, normalized_url)
        if existing_job_id is not None:
            return _LockedSubmitResult(
                response=AnalyzeResponse(
                    job_id=existing_job_id,
                    status=JobStatus.FAILED,
                    cached=False,
                )
            )
        job_id = await _insert_unsafe_job(
            session,
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            finding=unsafe_finding,
            api_key_id=_request_api_key_id(request),
        )
        return _LockedSubmitResult(
            response=AnalyzeResponse(job_id=job_id, status=JobStatus.FAILED, cached=False)
        )

    cached = await session.get(UrlScanSidebarCache, normalized_url)
    if cached is not None and cached.expires_at > datetime.now(UTC):
        job_id = await _insert_cached_job(
            session,
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            cache_row=cached,
            api_key_id=_request_api_key_id(request),
        )
        return _LockedSubmitResult(
            response=AnalyzeResponse(job_id=job_id, status=JobStatus.DONE, cached=True)
        )

    inflight = await _find_inflight_job(session, normalized_url)
    if inflight is not None:
        return _LockedSubmitResult(
            response=AnalyzeResponse(
                job_id=inflight[0],
                status=_job_status_from_batch_status(inflight[1]),
                cached=False,
            )
        )

    job_id, attempt_id = await _insert_pending_job(
        session,
        source_url=source_url,
        normalized_url=normalized_url,
        host=host,
        api_key_id=_request_api_key_id(request),
    )
    return _LockedSubmitResult(
        response=AnalyzeResponse(job_id=job_id, status=JobStatus.PENDING, cached=False),
        dispatch_job_id=job_id,
        dispatch_attempt_id=attempt_id,
    )


async def _run_web_risk_lookup(
    web_risk: _WebRiskFn,
    source_url: str,
    session: AsyncSession,
) -> WebRiskFinding | None:
    normalized_url = canonical_cache_key(source_url)
    now = datetime.now(UTC)
    cached = await session.get(UrlScanWebRiskLookup, normalized_url)
    if cached is not None and cached.expires_at > now:
        cached_finding = WebRiskFinding.model_validate(cached.findings)
        return cached_finding if cached_finding.threat_types else None

    maybe_result = web_risk(source_url)
    if isawaitable(maybe_result):
        return await maybe_result
    return maybe_result


def _request_api_key_id(request: Request) -> str | None:
    state = getattr(request, "state", None)
    api_key = getattr(state, "url_scan_api_key", None)
    api_key_id = getattr(api_key, "id", None)
    return str(api_key_id) if api_key_id is not None else None


async def _find_existing_unsafe_job(session: AsyncSession, normalized_url: str) -> UUID | None:
    result = await session.execute(
        select(BatchJob.id)
        .join(UrlScanState, UrlScanState.job_id == BatchJob.id)
        .where(
            UrlScanState.normalized_url == normalized_url,
            UrlScanState.error_code == ErrorCode.UNSAFE_URL.value,
            BatchJob.status == BatchJobStatus.FAILED.value,
        )
        .order_by(BatchJob.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return row[0]


async def _find_inflight_job(session: AsyncSession, normalized_url: str) -> tuple[UUID, str] | None:
    result = await session.execute(
        select(BatchJob.id, BatchJob.status)
        .join(UrlScanState, UrlScanState.job_id == BatchJob.id)
        .where(
            UrlScanState.normalized_url == normalized_url,
            UrlScanState.finished_at.is_(None),
            BatchJob.status.in_(_NONTERMINAL_BATCH_STATUSES),
        )
        .order_by(BatchJob.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def _insert_unsafe_job(
    session: AsyncSession,
    *,
    source_url: str,
    normalized_url: str,
    host: str,
    finding: WebRiskFinding,
    api_key_id: str | None,
) -> UUID:
    now = datetime.now(UTC)
    await session.merge(
        UrlScanWebRiskLookup(
            normalized_url=normalized_url,
            findings=finding.model_dump(mode="json"),
            expires_at=now + _WEB_RISK_LOOKUP_TTL,
        )
    )
    sidebar_payload = _build_unsafe_sidebar_payload(source_url, finding, now)
    job = BatchJob(
        job_type=_URL_SCAN_JOB_TYPE,
        status=BatchJobStatus.FAILED.value,
        total_tasks=1,
        completed_tasks=0,
        failed_tasks=1,
        metadata_=_job_metadata(
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            api_key_id=api_key_id,
            cached=False,
        ),
        error_summary={
            "error_code": ErrorCode.UNSAFE_URL.value,
            "message": _unsafe_error_message(finding),
        },
    )
    session.add(job)
    await session.flush()
    session.add(
        UrlScanState(
            job_id=job.id,
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            attempt_id=uuid4(),
            error_code=ErrorCode.UNSAFE_URL.value,
            error_message=_unsafe_error_message(finding),
            error_host=host,
            sidebar_payload=sidebar_payload,
            page_kind=PageKind.OTHER.value,
            utterance_count=0,
            finished_at=now,
        )
    )
    return job.id


async def _insert_cached_job(
    session: AsyncSession,
    *,
    source_url: str,
    normalized_url: str,
    host: str,
    cache_row: UrlScanSidebarCache,
    api_key_id: str | None,
) -> UUID:
    now = datetime.now(UTC)
    payload, page_title, page_kind, utterance_count = _hydrate_cached_sidebar_payload(
        source_url, cache_row, now
    )
    job = BatchJob(
        job_type=_URL_SCAN_JOB_TYPE,
        status=BatchJobStatus.COMPLETED.value,
        total_tasks=1,
        completed_tasks=1,
        failed_tasks=0,
        metadata_=_job_metadata(
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            api_key_id=api_key_id,
            cached=True,
        ),
    )
    session.add(job)
    await session.flush()
    session.add(
        UrlScanState(
            job_id=job.id,
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            attempt_id=uuid4(),
            sidebar_payload=payload,
            page_title=page_title,
            page_kind=page_kind,
            utterance_count=utterance_count,
            finished_at=now,
        )
    )
    return job.id


async def _insert_pending_job(
    session: AsyncSession,
    *,
    source_url: str,
    normalized_url: str,
    host: str,
    api_key_id: str | None,
) -> tuple[UUID, UUID]:
    attempt_id = uuid4()
    job = BatchJob(
        job_type=_URL_SCAN_JOB_TYPE,
        status=BatchJobStatus.PENDING.value,
        total_tasks=len(SectionSlug),
        completed_tasks=0,
        failed_tasks=0,
        metadata_=_job_metadata(
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            api_key_id=api_key_id,
            cached=False,
        ),
    )
    session.add(job)
    await session.flush()
    session.add(
        UrlScanState(
            job_id=job.id,
            source_url=source_url,
            normalized_url=normalized_url,
            host=host,
            attempt_id=attempt_id,
            utterance_count=0,
        )
    )
    for slug in SectionSlug:
        session.add(
            UrlScanSectionSlot(
                job_id=job.id,
                slug=slug.value,
                state="PENDING",
                attempt_id=attempt_id,
            )
        )
    return job.id, attempt_id


async def _mark_dispatch_failure(
    session: AsyncSession,
    job_id: UUID,
    detail: str,
) -> None:
    async with session.begin():
        job = await session.get(BatchJob, job_id)
        state = await session.get(UrlScanState, job_id)
        if job is not None:
            job.status = BatchJobStatus.FAILED.value
            job.failed_tasks = max(job.failed_tasks, 1)
            job.error_summary = {
                "error_code": ErrorCode.INTERNAL.value,
                "message": "dispatch failed",
                "detail": detail,
            }
        if state is not None:
            state.error_code = ErrorCode.INTERNAL.value
            state.error_message = "dispatch failed"
            state.finished_at = datetime.now(UTC)


def _job_metadata(
    *,
    source_url: str,
    normalized_url: str,
    host: str,
    api_key_id: str | None,
    cached: bool,
) -> dict[str, str | int | bool | float | list[str] | None]:
    return {
        "source_url": source_url,
        "normalized_url": normalized_url,
        "host": host,
        "api_key_id": api_key_id,
        "cached": cached,
    }


def _job_status_from_batch_status(status: str) -> JobStatus:
    mapping = {
        BatchJobStatus.PENDING.value: JobStatus.PENDING,
        BatchJobStatus.EXTRACTING.value: JobStatus.EXTRACTING,
        BatchJobStatus.ANALYZING.value: JobStatus.ANALYZING,
        BatchJobStatus.COMPLETED.value: JobStatus.DONE,
        BatchJobStatus.PARTIAL.value: JobStatus.PARTIAL,
        BatchJobStatus.FAILED.value: JobStatus.FAILED,
    }
    try:
        return mapping[status]
    except KeyError as exc:
        raise ValueError(f"unsupported batch job status: {status}") from exc


def _hydrate_cached_sidebar_payload(
    source_url: str,
    cache_row: UrlScanSidebarCache,
    now: datetime,
) -> tuple[dict[str, Any], str | None, str | None, int]:
    try:
        payload = SidebarPayload.model_validate(cache_row.sidebar_payload).model_copy(
            update={
                "source_url": source_url,
                "cached": True,
                "cached_at": cache_row.created_at,
            }
        )
        return (
            payload.model_dump(mode="json"),
            payload.page_title,
            payload.page_kind.value,
            len(payload.utterances),
        )
    except Exception:
        raw_payload = dict(cache_row.sidebar_payload)
        raw_payload["source_url"] = source_url
        raw_payload["cached"] = True
        raw_payload["cached_at"] = cache_row.created_at.isoformat()
        return (
            raw_payload,
            raw_payload.get("page_title"),
            raw_payload.get("page_kind"),
            len(raw_payload.get("utterances") or []),
        )


def _build_unsafe_sidebar_payload(
    source_url: str,
    finding: WebRiskFinding,
    now: datetime,
) -> dict[str, Any]:
    sidebar = SidebarPayload(
        source_url=source_url,
        scraped_at=now,
        safety=SafetySection(),
        tone_dynamics=ToneDynamicsSection.model_validate(
            {
                "scd": {
                    "summary": "",
                    "insufficient_conversation": True,
                },
                "flashpoint_matches": [],
            }
        ),
        facts_claims=FactsClaimsSection.model_validate(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                },
                "known_misinformation": [],
            }
        ),
        opinions_sentiments=OpinionsSection.model_validate(
            {
                "opinions_report": {
                    "sentiment_stats": {
                        "per_utterance": [],
                        "positive_pct": 0.0,
                        "negative_pct": 0.0,
                        "neutral_pct": 0.0,
                        "mean_valence": 0.0,
                    },
                    "subjective_claims": [],
                }
            }
        ),
        web_risk=WebRiskSection(findings=[finding]),
    )
    return sidebar.model_dump(mode="json")


def _unsafe_error_message(finding: WebRiskFinding) -> str:
    return f"page URL flagged by Web Risk: {', '.join(finding.threat_types)}"
