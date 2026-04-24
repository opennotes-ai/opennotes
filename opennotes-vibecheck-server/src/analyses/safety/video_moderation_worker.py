from __future__ import annotations

import base64
import logging
from typing import Any
from uuid import UUID

import httpx
import logfire

from src.analyses.safety._schemas import FrameFinding, VideoModerationMatch
from src.analyses.safety._vision_likelihood import likelihood_to_score
from src.analyses.safety.video_sampler import FrameBytes, VideoSamplingError, sample_video
from src.analyses.safety.vision_client import ANNOTATE_URL, VisionTransientError
from src.config import Settings
from src.monitoring import external_api_span
from src.monitoring_metrics import SECTION_MEDIA_DROPPED
from src.services.gcp_adc import CLOUD_PLATFORM_SCOPE, get_access_token

logger = logging.getLogger(__name__)


async def run_video_moderation(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    for utt in getattr(payload, "utterances", []) or []:
        for vid in getattr(utt, "mentioned_videos", []) or []:
            pairs.append((utt.utterance_id or "", vid))
    capped = pairs[: settings.MAX_VIDEOS_MODERATED]
    dropped = len(pairs) - len(capped)
    if dropped > 0:
        logger.info("video moderation cap: processing=%d dropped=%d", len(capped), dropped)
        SECTION_MEDIA_DROPPED.labels(media_type="video").inc(dropped)
    with logfire.span(
        "vibecheck.section.video_moderation",
        video_count=len(capped),
        dropped_video_count=dropped,
    ) as span:
        if not capped:
            return {"matches": []}

        token = get_access_token(CLOUD_PLATFORM_SCOPE)
        if not token:
            raise VisionTransientError("ADC token unavailable")

        matches: list[VideoModerationMatch] = []
        async with httpx.AsyncClient() as hx:
            for uid, vurl in capped:
                try:
                    frames = await sample_video(vurl)
                except VideoSamplingError as exc:
                    # Sampling failures are indeterminate, not "clean". We flag
                    # conservatively so the sidebar surfaces an inconclusive video
                    # rather than silently presenting it as safe (codex P1.3).
                    logger.warning("video sampling failed for %s: %s", vurl, exc)
                    matches.append(VideoModerationMatch(
                        utterance_id=uid, video_url=vurl,
                        frame_findings=[], flagged=True, max_likelihood=1.0,
                    ))
                    continue
                frame_findings = await _annotate_frames(frames, hx, token)
                max_likelihood = max(
                    (ff.max_likelihood for ff in frame_findings),
                    default=0.0,
                )
                flagged = any(ff.flagged for ff in frame_findings)
                matches.append(VideoModerationMatch(
                    utterance_id=uid, video_url=vurl,
                    frame_findings=frame_findings,
                    flagged=flagged,
                    max_likelihood=max_likelihood,
                ))
        span.set_attribute("flagged_count", sum(1 for match in matches if match.flagged))
        return {"matches": [m.model_dump() for m in matches]}


async def _annotate_frames(frames: list[FrameBytes], hx: httpx.AsyncClient, token: str) -> list[FrameFinding]:
    if not frames:
        return []
    requests_body = {"requests": [
        {
            "image": {"content": base64.b64encode(fb.png_bytes).decode("ascii")},
            "features": [{"type": "SAFE_SEARCH_DETECTION"}],
        }
        for fb in frames
    ]}
    with external_api_span("vision", "images.annotate_video_frames", request_count=len(frames)) as obs:
        try:
            r = await hx.post(
                ANNOTATE_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=requests_body,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            obs.set_error_category("network")
            raise VisionTransientError("vision-frames network") from exc
        obs.set_response_status(r.status_code)
        if r.status_code == 429:
            obs.set_error_category("rate_limited")
            raise VisionTransientError(f"vision-frames {r.status_code}")
        if r.status_code >= 500:
            obs.set_error_category("upstream")
            raise VisionTransientError(f"vision-frames {r.status_code}")
        r.raise_for_status()
        responses = r.json().get("responses") or []
        out: list[FrameFinding] = []
        flagged_count = 0
        for fb, resp in zip(frames, responses, strict=False):
            annotation = resp.get("safeSearchAnnotation") or {}
            scores = {
                k: likelihood_to_score(str(annotation.get(k, "UNKNOWN")))
                for k in ("adult", "violence", "racy", "medical", "spoof")
            }
            max_likelihood = max(scores.values())
            flagged = max_likelihood >= 0.75
            flagged_count += 1 if flagged else 0
            out.append(FrameFinding(
                frame_offset_ms=fb.frame_offset_ms,
                **scores,
                flagged=flagged,
                max_likelihood=max_likelihood,
            ))
        obs.add_flagged(flagged_count)
        return out
