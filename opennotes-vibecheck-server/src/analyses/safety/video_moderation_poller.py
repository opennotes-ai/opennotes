from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel

from src.analyses.safety._schemas import VideoModerationMatch
from src.analyses.safety.video_intelligence_client import (
    OperationStatus,
    VITransientError,
    get_operation,
    parse_explicit_content,
)
from src.analyses.schemas import SectionSlug, SectionState, VideoModerationSection
from src.config import Settings
from src.jobs.enqueue import enqueue_video_moderation_poll
from src.jobs.finalize import maybe_finalize_job
from src.jobs.slots import mark_slot_done, mark_slot_failed
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token

logger = logging.getLogger(__name__)


class VideoModerationPollPayload(BaseModel):
    job_id: UUID
    task_attempt: UUID
    slot_attempt: UUID


async def video_moderation_poll(
    payload: VideoModerationPollPayload,
    *,
    pool: Any,
    settings: Settings,
) -> Literal["pending", "done", "failed", "stale"]:
    slot = await _load_slot(pool, payload.job_id)
    if not slot or slot.get("state") != SectionState.RUNNING.value:
        return "stale"
    if str(slot.get("attempt_id")) != str(payload.slot_attempt):
        return "stale"
    data = slot.get("data") or {}
    operations = data.get("operations") or []
    started_at = _parse_started_at(data.get("started_at"))
    elapsed = (datetime.now(UTC) - started_at).total_seconds()

    token = get_access_token(CLOUD_PLATFORM_SCOPE)
    if not token:
        raise VITransientError("ADC token unavailable")

    statuses: list[tuple[dict[str, Any], OperationStatus]] = []
    async with httpx.AsyncClient() as http:
        for operation in operations:
            statuses.append(
                (
                    operation,
                    await get_operation(
                        str(operation["operation_name"]),
                        http=http,
                        token=token,
                    ),
                )
            )

    pending = [operation for operation, status in statuses if not status.done]
    if pending and elapsed < settings.VIDEO_MODERATION_MAX_WAIT_SEC:
        await enqueue_video_moderation_poll(
            payload.job_id,
            payload.task_attempt,
            payload.slot_attempt,
            settings,
            schedule_delay_seconds=30,
        )
        return "pending"
    if pending:
        operation_names = [str(item["operation_name"]) for item in pending]
        await mark_slot_failed(
            pool,
            payload.job_id,
            SectionSlug.SAFETY_VIDEO_MODERATION,
            payload.slot_attempt,
            error=(
                "video-intelligence-timeout: "
                f"{len(operation_names)} operations still pending after {int(elapsed)}s: "
                f"{operation_names}"
            ),
            expected_task_attempt=payload.task_attempt,
        )
        await _cleanup_staged_objects(operations)
        await maybe_finalize_job(
            pool,
            payload.job_id,
            expected_task_attempt=payload.task_attempt,
        )
        return "failed"

    matches: list[VideoModerationMatch] = []
    errors: list[dict[str, str]] = []
    for operation, status in statuses:
        if status.error:
            errors.append(
                {
                    "operation_name": str(operation["operation_name"]),
                    "error": status.error,
                }
            )
            continue
        findings = parse_explicit_content(status.response or {})
        max_likelihood = max((finding.max_likelihood for finding in findings), default=0.0)
        matches.append(
            VideoModerationMatch(
                utterance_id=operation["utterance_id"],
                video_url=operation["video_url"],
                segment_findings=findings,
                flagged=any(finding.flagged for finding in findings),
                max_likelihood=max_likelihood,
            )
        )
    section = VideoModerationSection(matches=matches)
    data_out = section.model_dump(mode="json")
    if errors:
        data_out["operation_errors"] = errors
    await mark_slot_done(
        pool,
        payload.job_id,
        SectionSlug.SAFETY_VIDEO_MODERATION,
        payload.slot_attempt,
        data_out,
        expected_task_attempt=payload.task_attempt,
    )
    await _cleanup_staged_objects(operations)
    await maybe_finalize_job(
        pool,
        payload.job_id,
        expected_task_attempt=payload.task_attempt,
    )
    return "done"


async def _load_slot(pool: Any, job_id: UUID) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT sections -> $2::text AS slot
            FROM vibecheck_jobs
            WHERE job_id = $1
            """,
            job_id,
            SectionSlug.SAFETY_VIDEO_MODERATION.value,
        )
    if row is None:
        return None
    slot = row["slot"]
    if isinstance(slot, str):
        slot = json.loads(slot)
    return dict(slot) if slot is not None else None


def _parse_started_at(value: Any) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(UTC)


async def _cleanup_staged_objects(operations: list[dict[str, Any]]) -> None:
    for operation in operations:
        uri = str(operation.get("staging_uri") or "")
        if not uri.startswith("gs://"):
            continue
        try:
            await _delete_gcs_uri(uri)
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.warning("video staging cleanup failed for %s: %s", uri, exc)


async def _delete_gcs_uri(uri: str) -> None:
    from google.cloud import storage  # noqa: PLC0415

    path = uri.removeprefix("gs://")
    bucket_name, _, key = path.partition("/")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    await asyncio.to_thread(bucket.delete_blob, key)
