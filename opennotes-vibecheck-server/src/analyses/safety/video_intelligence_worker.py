from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import logfire

from src.analyses.safety.gcs_video_staging import (
    VideoStagingPermanentError,
    VideoStagingTransientError,
    stage_video,
)
from src.analyses.safety.video_intelligence_client import (
    VIPermanentError,
    VITransientError,
    submit_explicit_content_annotation,
)
from src.config import Settings
from src.monitoring_metrics import SECTION_MEDIA_DROPPED
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token

logger = logging.getLogger(__name__)


async def run_video_intelligence(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del pool, task_attempt
    pairs: list[tuple[str, str]] = []
    for utterance in getattr(payload, "utterances", []) or []:
        for video_url in getattr(utterance, "mentioned_videos", []) or []:
            pairs.append((utterance.utterance_id or "", video_url))
    capped = pairs[: settings.MAX_VIDEOS_MODERATED]
    dropped = len(pairs) - len(capped)
    if dropped > 0:
        SECTION_MEDIA_DROPPED.labels(media_type="video").inc(dropped)
    if not capped:
        return {"matches": []}

    token = get_access_token(CLOUD_PLATFORM_SCOPE)
    if not token:
        raise VITransientError("ADC token unavailable")

    operations: list[dict[str, Any]] = []
    with logfire.span(
        "vibecheck.section.video_intelligence",
        video_count=len(capped),
        dropped_video_count=dropped,
    ) as span:
        async with httpx.AsyncClient() as http:
            for utterance_id, video_url in capped:
                try:
                    with logfire.span("vibecheck.video_intelligence.staging.upload") as upload_span:
                        staged = await stage_video(
                            video_url,
                            job_id=job_id,
                            utterance_id=utterance_id,
                            settings=settings,
                        )
                        upload_span.set_attribute("bytes_size", staged.bytes_size)
                        upload_span.set_attribute("duration_ms", staged.duration_ms)
                    with logfire.span("vibecheck.video_intelligence.vi.submit") as submit_span:
                        operation_name = await submit_explicit_content_annotation(
                            staged.gs_uri,
                            http=http,
                            token=token,
                        )
                        submit_span.set_attribute("operation_name", operation_name)
                except (VideoStagingTransientError, VITransientError):
                    raise
                except (VideoStagingPermanentError, VIPermanentError) as exc:
                    logger.warning(
                        "video intelligence skipped video_url=%s utterance_id=%s: %s",
                        video_url,
                        utterance_id,
                        exc,
                    )
                    continue
                operations.append(
                    {
                        "operation_name": operation_name,
                        "staging_uri": staged.gs_uri,
                        "video_url": video_url,
                        "utterance_id": utterance_id,
                    }
                )
        span.set_attribute("operation_count", len(operations))

    if not operations:
        return {"status": "empty", "matches": []}
    return {
        "status": "polling",
        "started_at": datetime.now(UTC).isoformat(),
        "operations": operations,
    }
