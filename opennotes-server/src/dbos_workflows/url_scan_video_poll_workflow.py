"""DBOS-native Video Intelligence LRO poll workflow.

Ports vibecheck-server PR530 (video_moderation_poller.py) into DBOS patterns.
Instead of Cloud Tasks HTTP callbacks, this workflow polls the LRO with
exponential backoff using DBOS.sleep() and re-enqueues itself until done.

Architecture:
  1. url_scan_section_workflow dispatches the video moderation section
  2. The section runner submits each eligible video to the VI API and returns
     an operations payload with status="polling"
  3. url_scan_video_poll_workflow is enqueued; it polls all pending LROs,
     sleeping between attempts, and completes or fails the section slot.

The workflow is DBOS-checkpointed: if the worker crashes between polls, DBOS
replays from the last completed step (including sleep offsets).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from dbos import DBOS, Queue, SetEnqueueOptions, SetWorkflowID

from src.dbos_workflows.url_scan_workflow import (
    complete_url_scan_section_step,
    fail_url_scan_section_step,
)
from src.url_content_scan.analyses.safety.google_client import get_access_token
from src.url_content_scan.analyses.safety.video_intelligence import (
    OperationStatus,
    get_operation,
    parse_explicit_content,
)
from src.url_content_scan.safety_schemas import FrameFinding, VideoModerationMatch
from src.utils.async_compat import run_sync

_logger = logging.getLogger(__name__)

VIDEO_POLL_QUEUE_NAME = "url_scan_video_poll"
_DEFAULT_MAX_WAIT_SECONDS = 3600
_POLL_SLEEP_SECONDS = 30

url_scan_video_poll_queue = Queue(
    name=VIDEO_POLL_QUEUE_NAME,
    worker_concurrency=4,
    concurrency=8,
)

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def is_lro_timed_out(
    started_at_iso: str, *, max_wait_seconds: int = _DEFAULT_MAX_WAIT_SECONDS
) -> bool:
    """Return True if the LRO has been running longer than max_wait_seconds."""
    try:
        normalized = started_at_iso.replace("Z", "+00:00")
        started = datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        return False
    elapsed = (datetime.now(UTC) - started).total_seconds()
    return elapsed > max_wait_seconds


def poll_operations(
    operations: list[dict[str, Any]],
    *,
    token: str,
) -> list[OperationStatus]:
    """Synchronously poll all operations and return their statuses.

    This is a synchronous wrapper suitable for use inside DBOS steps.
    """

    async def _async_poll() -> list[OperationStatus]:
        statuses: list[OperationStatus] = []
        async with httpx.AsyncClient() as http:
            for op in operations:
                status = await get_operation(
                    str(op["operation_name"]),
                    http=http,
                    token=token,
                )
                statuses.append(status)
        return statuses

    return run_sync(_async_poll())


def build_video_moderation_result(
    operations: list[dict[str, Any]],
    statuses: list[OperationStatus],
) -> dict[str, Any]:
    """Build the VideoModerationSection payload from completed operations."""
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for op, status in zip(operations, statuses, strict=False):
        if status.error:
            errors.append(
                {
                    "operation_name": str(op["operation_name"]),
                    "error": status.error,
                }
            )
            continue
        findings: list[FrameFinding] = parse_explicit_content(status.response or {})
        max_likelihood = max((f.max_likelihood for f in findings), default=0.0)
        match = VideoModerationMatch(
            utterance_id=str(op["utterance_id"]),
            video_url=str(op["video_url"]),
            frame_findings=findings,
            flagged=any(f.flagged for f in findings),
            max_likelihood=max_likelihood,
        )
        matches.append(match.model_dump(mode="json"))

    result: dict[str, Any] = {"matches": matches}
    if errors:
        result["operation_errors"] = errors
    return result


@DBOS.step()
def _get_vi_token_step() -> str | None:
    return run_sync(get_access_token(CLOUD_PLATFORM_SCOPE))


@DBOS.step()
def _poll_operations_step(
    operations: list[dict[str, Any]],
    token: str,
) -> list[dict[str, Any]]:
    statuses = poll_operations(operations, token=token)
    return [
        {
            "name": s.name,
            "done": s.done,
            "error": s.error,
            "response": s.response,
        }
        for s in statuses
    ]


def _statuses_from_dicts(raw: list[dict[str, Any]]) -> list[OperationStatus]:
    return [
        OperationStatus(
            name=str(item["name"]),
            done=bool(item["done"]),
            error=item.get("error"),
            response=item.get("response"),
        )
        for item in raw
    ]


@DBOS.workflow()
def url_scan_video_poll_workflow(
    job_id: str,
    section_slug: str,
    attempt_id: str,
    operations: list[dict[str, Any]],
    started_at: str,
    *,
    max_wait_seconds: int = _DEFAULT_MAX_WAIT_SECONDS,
    poll_sleep_seconds: int = _POLL_SLEEP_SECONDS,
) -> dict[str, Any]:
    if not operations:
        result = {"matches": []}
        complete_url_scan_section_step(job_id, section_slug, attempt_id, result)
        return {"status": "done", "job_id": job_id, "slug": section_slug}

    token = _get_vi_token_step()
    if not token:
        error_msg = "ADC token unavailable for video intelligence poll"
        fail_url_scan_section_step(
            job_id, section_slug, attempt_id, error_msg, error_code="vi_token_unavailable"
        )
        return {"status": "failed", "job_id": job_id, "slug": section_slug, "error": error_msg}

    while True:
        raw_statuses = _poll_operations_step(operations, token)
        statuses = _statuses_from_dicts(raw_statuses)

        pending_ops = [
            (op, status)
            for op, status in zip(operations, statuses, strict=False)
            if not status.done
        ]

        if not pending_ops:
            result = build_video_moderation_result(operations, statuses)
            complete_url_scan_section_step(job_id, section_slug, attempt_id, result)
            return {"status": "done", "job_id": job_id, "slug": section_slug}

        if is_lro_timed_out(started_at, max_wait_seconds=max_wait_seconds):
            pending_names = [str(op["operation_name"]) for op, _ in pending_ops]
            error_msg = (
                f"video-intelligence-timeout: {len(pending_names)} operations still "
                f"pending: {pending_names}"
            )
            fail_url_scan_section_step(
                job_id,
                section_slug,
                attempt_id,
                error_msg,
                error_code="vi_lro_timeout",
            )
            return {
                "status": "failed",
                "job_id": job_id,
                "slug": section_slug,
                "error": error_msg,
            }

        DBOS.sleep(poll_sleep_seconds)


def enqueue_video_poll_workflow(
    job_id: str,
    section_slug: str,
    attempt_id: str,
    operations: list[dict[str, Any]],
    started_at: str,
    *,
    max_wait_seconds: int = _DEFAULT_MAX_WAIT_SECONDS,
) -> Any:
    """Enqueue the video poll workflow with deduplication based on attempt_id."""
    workflow_id = f"url-scan-video-poll-{job_id}-{attempt_id}"
    with SetWorkflowID(workflow_id), SetEnqueueOptions(deduplication_id=workflow_id):
        return url_scan_video_poll_queue.enqueue(
            url_scan_video_poll_workflow,
            job_id,
            section_slug,
            attempt_id,
            operations,
            started_at,
            max_wait_seconds=max_wait_seconds,
        )
