from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from src.batch_jobs.models import BatchJob

_POLL_DELAY_BY_STATUS = {
    "pending": 500,
    "in_progress": 500,
    "extracting": 500,
    "analyzing": 1500,
    "completed": 0,
    "done": 0,
    "partial": 0,
    "failed": 0,
    "cancelled": 0,
}

_WIRE_STATUS_BY_BATCH_STATUS = {
    "in_progress": "extracting",
    "completed": "done",
}

_ACTIVITY_LABEL_BY_STATUS = {
    "extracting": "Extracting page content",
    "analyzing": "Running section analyses",
}

_DEFAULT_JOB_TTL_DAYS = 30

JOB_EXPIRED = object()


def _load_schemas() -> Any:
    return import_module("src.url_content_scan.schemas")


def _load_models() -> Any:
    return import_module("src.url_content_scan.models")


def _wire_status(raw_status: str) -> str:
    return _WIRE_STATUS_BY_BATCH_STATUS.get(raw_status, raw_status)


def _coerce_section_state(raw_state: str, schemas: Any) -> Any:
    return schemas.SectionState(raw_state.lower())


def _is_terminal_status(status: str) -> bool:
    return status in {"completed", "done", "partial", "failed", "cancelled"}


def _finished_at(batch_job: BatchJob, scan_state: Any) -> datetime | None:
    if scan_state.finished_at is not None:
        return scan_state.finished_at
    return getattr(batch_job, "completed_at", None)


def build_job_state(
    batch_job: BatchJob,
    scan_state: Any,
    slot_rows: list[Any],
) -> Any:
    schemas = _load_schemas()
    status = schemas.JobStatus(_wire_status(batch_job.status))

    sections: dict[Any, Any] = {}
    for row in slot_rows:
        slug = schemas.SectionSlug(row.slug)
        sections[slug] = schemas.SectionSlot(
            state=_coerce_section_state(row.state, schemas),
            attempt_id=row.attempt_id,
            data=row.data,
            error=getattr(row, "error_message", None),
            started_at=getattr(row, "started_at", None),
            finished_at=getattr(row, "finished_at", None),
        )

    sidebar_payload = None
    if scan_state.sidebar_payload is not None:
        sidebar_payload = schemas.SidebarPayload.model_validate(scan_state.sidebar_payload)

    is_terminal = status in {
        schemas.JobStatus.DONE,
        schemas.JobStatus.PARTIAL,
        schemas.JobStatus.FAILED,
    }
    page_kind = None
    if scan_state.page_kind:
        page_kind = schemas.PageKind(scan_state.page_kind)

    return schemas.JobState(
        job_id=batch_job.id,
        url=scan_state.source_url,
        status=status,
        attempt_id=scan_state.attempt_id,
        error_code=scan_state.error_code,
        error_message=scan_state.error_message,
        error_host=scan_state.error_host,
        created_at=batch_job.created_at,
        updated_at=batch_job.updated_at,
        sections=sections,
        sidebar_payload=sidebar_payload,
        sidebar_payload_complete=bool(sidebar_payload)
        and status in {schemas.JobStatus.DONE, schemas.JobStatus.PARTIAL},
        activity_at=None if is_terminal else scan_state.heartbeat_at,
        activity_label=None if is_terminal else _ACTIVITY_LABEL_BY_STATUS.get(status.value),
        cached=False,
        next_poll_ms=_POLL_DELAY_BY_STATUS[batch_job.status],
        page_title=scan_state.page_title,
        page_kind=page_kind,
        utterance_count=scan_state.utterance_count,
    )


async def _soft_delete_job(session: Any, job_id: UUID) -> None:
    models = _load_models()
    now = datetime.now(UTC)
    await session.execute(
        update(models.UrlScanState)
        .where(
            models.UrlScanState.job_id == job_id,
            models.UrlScanState.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    await session.commit()


async def load_job_state(
    session: Any,
    job_id: UUID,
    *,
    job_ttl_days: int = _DEFAULT_JOB_TTL_DAYS,
) -> Any | None:
    batch_job = await session.get(BatchJob, job_id)
    if batch_job is None:
        return None

    models = _load_models()
    scan_state = await session.get(models.UrlScanState, job_id)
    if scan_state is None:
        return None

    if _is_terminal_status(batch_job.status):
        finished = _finished_at(batch_job, scan_state)
        if finished is not None:
            cutoff = datetime.now(UTC) - timedelta(days=job_ttl_days)
            if finished < cutoff:
                if getattr(scan_state, "deleted_at", None) is None:
                    await _soft_delete_job(session, job_id)
                return JOB_EXPIRED

    result = await session.execute(
        select(models.UrlScanSectionSlot)
        .where(models.UrlScanSectionSlot.job_id == job_id)
        .order_by(models.UrlScanSectionSlot.slug)
    )
    return build_job_state(batch_job, scan_state, list(result.scalars().all()))
