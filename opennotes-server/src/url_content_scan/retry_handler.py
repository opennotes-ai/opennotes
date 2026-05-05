from __future__ import annotations

import inspect
from dataclasses import dataclass
from importlib import import_module
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select

from src.batch_jobs.models import BatchJob

_RETRYABLE_JOB_STATUSES = frozenset({"analyzing", "partial", "completed", "failed"})


def _load_schemas() -> Any:
    return import_module("src.url_content_scan.schemas")


def _load_models() -> Any:
    return import_module("src.url_content_scan.models")


def _load_utterance_schema() -> Any:
    return import_module("src.url_content_scan.utterances.schema")


def _load_workflow_inputs() -> Any:
    return import_module("src.dbos_workflows.url_scan_workflow").UrlScanWorkflowInputs


def _conflict(error_code: str, message: str, **extra: object) -> HTTPException:
    detail = {"error_code": error_code, "message": message, **extra}
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@dataclass(slots=True)
class RetryDispatchSurface:
    attempt_id: UUID
    section_inputs: Any


def _coerce_slug_value(slug: Any) -> str:
    return slug.value if hasattr(slug, "value") else str(slug)


def _build_section_inputs(batch_job: BatchJob, scan_state: Any, utterance_rows: list[Any]) -> Any:
    utterance_schema = _load_utterance_schema()
    workflow_inputs_cls = _load_workflow_inputs()
    schemas = _load_schemas()

    utterances = [utterance_schema.Utterance.model_validate(row.payload) for row in utterance_rows]
    mentioned_urls = sorted({url for item in utterances for url in item.mentioned_urls})
    mentioned_images = sorted({url for item in utterances for url in item.mentioned_images})
    mentioned_videos = sorted({url for item in utterances for url in item.mentioned_videos})

    metadata = batch_job.metadata_ if isinstance(batch_job.metadata_, dict) else {}
    page_kind = (
        schemas.PageKind(scan_state.page_kind) if scan_state.page_kind else schemas.PageKind.OTHER
    )

    return workflow_inputs_cls(
        utterances=utterances,
        page_url=scan_state.source_url,
        mentioned_urls=mentioned_urls,
        media_urls=sorted(set(mentioned_images + mentioned_videos)),
        mentioned_images=mentioned_images,
        mentioned_videos=mentioned_videos,
        page_kind=page_kind,
        community_server_id=str(metadata.get("community_server_id") or "") or None,
        community_server_uuid=str(metadata.get("community_server_uuid") or "") or None,
        dataset_tags=list(metadata.get("dataset_tags") or []),
    )


async def _default_dispatch_workflow(
    job_id: UUID,
    slug: Any,
    attempt_id: UUID,
    section_inputs: Any,
) -> None:
    workflow_module = import_module("src.dbos_workflows.url_scan_section_retry_workflow")
    maybe_result = workflow_module.url_scan_section_retry_workflow(
        job_id=str(job_id),
        section_slug=_coerce_slug_value(slug),
        section_inputs=section_inputs,
    )
    if inspect.isawaitable(maybe_result):
        await maybe_result
    _ = attempt_id


async def prepare_section_retry(
    session: Any,
    job_id: UUID,
    slug: Any,
    *,
    dispatch_workflow: Any | None = None,
) -> Any:
    batch_job = await session.get(BatchJob, job_id)
    if batch_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "not_found", "message": "job not found"},
        )

    if batch_job.status not in _RETRYABLE_JOB_STATUSES:
        raise _conflict(
            "job_not_retryable",
            f"job status {batch_job.status!r} is not retryable",
            job_status=batch_job.status,
        )

    models = _load_models()
    scan_state = await session.get(models.UrlScanState, job_id)
    if scan_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "not_found", "message": "url scan state not found"},
        )

    slug_value = _coerce_slug_value(slug)
    slots_result = await session.execute(
        select(models.UrlScanSectionSlot).where(models.UrlScanSectionSlot.job_id == job_id)
    )
    slot_rows = list(slots_result.scalars().all())
    slot_row = next((row for row in slot_rows if row.slug == slug_value), None)
    if slot_row is None or str(slot_row.state).upper() != "FAILED":
        raise _conflict(
            "slot_not_in_retryable_state",
            f"slot {slug_value!r} must be in FAILED state to retry",
            slug=slug_value,
        )

    utterance_rows_result = await session.execute(
        select(models.UrlScanUtterance).where(models.UrlScanUtterance.job_id == job_id)
    )
    utterance_rows = list(utterance_rows_result.scalars().all())
    section_inputs = _build_section_inputs(batch_job, scan_state, utterance_rows)
    attempt_id = uuid4()

    dispatcher = dispatch_workflow or _default_dispatch_workflow
    maybe_result = dispatcher(job_id, slug, attempt_id, section_inputs)
    if inspect.isawaitable(maybe_result):
        await maybe_result

    schemas = _load_schemas()
    return schemas.RetryResponse(job_id=job_id, slug=slug, attempt_id=attempt_id)
