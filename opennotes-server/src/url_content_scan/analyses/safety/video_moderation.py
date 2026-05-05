from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from src.url_content_scan.analyses.safety.video_sampler import (
    FrameBytes,
    VideoSamplingError,
)
from src.url_content_scan.analyses.safety.video_sampler import (
    sample_video as sample_video_default,
)
from src.url_content_scan.analyses.safety.vision import SafeSearchResult, annotate_image_bytes
from src.url_content_scan.safety_schemas import FrameFinding, VideoModerationMatch
from src.url_content_scan.schemas import VideoModerationSection


@dataclass(frozen=True)
class MentionedVideo:
    utterance_id: str
    video_url: str


SampleVideo = Callable[[str], Awaitable[list[FrameBytes]]]
SafeSearch = Callable[[bytes], Awaitable[SafeSearchResult | None]]


async def run_video_moderation(
    mentioned_videos: list[MentionedVideo],
    *,
    sample_video: SampleVideo | None = None,
    safe_search: SafeSearch | None = None,
    frame_cache: dict[str, SafeSearchResult | None] | None = None,
) -> VideoModerationSection:
    if not mentioned_videos:
        return VideoModerationSection()

    sample_video = sample_video or sample_video_default
    if safe_search is None:
        async with httpx.AsyncClient() as http_client:
            return await run_video_moderation(
                mentioned_videos,
                sample_video=sample_video,
                safe_search=lambda image_bytes: annotate_image_bytes(
                    image_bytes, http_client=http_client
                ),
                frame_cache=frame_cache,
            )

    cache = frame_cache if frame_cache is not None else {}
    matches: list[VideoModerationMatch] = []
    for item in mentioned_videos:
        try:
            frames = await sample_video(item.video_url)
        except VideoSamplingError:
            matches.append(
                VideoModerationMatch(
                    utterance_id=item.utterance_id,
                    video_url=item.video_url,
                    frame_findings=[],
                    flagged=True,
                    max_likelihood=1.0,
                )
            )
            continue

        frame_findings: list[FrameFinding] = []
        for frame in frames:
            content_hash = hashlib.sha256(frame.png_bytes).hexdigest()
            if content_hash not in cache:
                cache[content_hash] = await safe_search(frame.png_bytes)
            result = cache[content_hash]
            if result is None:
                continue
            frame_findings.append(
                FrameFinding(
                    frame_offset_ms=frame.frame_offset_ms,
                    adult=result.adult,
                    violence=result.violence,
                    racy=result.racy,
                    medical=result.medical,
                    spoof=result.spoof,
                    flagged=result.flagged,
                    max_likelihood=result.max_likelihood,
                )
            )
        max_likelihood = max((frame.max_likelihood for frame in frame_findings), default=0.0)
        matches.append(
            VideoModerationMatch(
                utterance_id=item.utterance_id,
                video_url=item.video_url,
                frame_findings=frame_findings,
                flagged=any(frame.flagged for frame in frame_findings),
                max_likelihood=max_likelihood,
            )
        )

    return VideoModerationSection(matches=matches)
