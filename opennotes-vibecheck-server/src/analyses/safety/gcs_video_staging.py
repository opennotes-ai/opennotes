from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from src.config import Settings
from src.utils.url_security import InvalidURL, validate_public_http_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StagedVideo:
    gs_uri: str
    original_url: str
    bytes_size: int
    duration_ms: int | None


class VideoStagingTransientError(Exception):
    """Network, upload, or timeout failures that should be retried."""


class VideoStagingPermanentError(Exception):
    """Unsupported URL or stable download failure."""


async def stage_video(
    url: str,
    *,
    job_id: UUID,
    utterance_id: str,
    settings: Settings,
) -> StagedVideo:
    if not settings.GCS_VIDEO_STAGING_BUCKET:
        raise VideoStagingPermanentError("GCS_VIDEO_STAGING_BUCKET is not configured")
    try:
        safe_url = validate_public_http_url(url)
    except InvalidURL as exc:
        raise VideoStagingPermanentError(f"url rejected: {exc.reason}") from exc

    with tempfile.TemporaryDirectory(prefix="vibecheck-video-stage-") as tmp:
        tmp_path = Path(tmp)
        video_path, duration_ms = await _download_video(
            safe_url,
            tmp_path,
            settings.YT_DLP_VIDEO_QUALITY,
        )
        key = _object_key(job_id, utterance_id, url, video_path.suffix)
        await asyncio.to_thread(
            _upload,
            settings.GCS_VIDEO_STAGING_BUCKET,
            key,
            video_path,
            url,
            utterance_id,
        )
        return StagedVideo(
            gs_uri=f"gs://{settings.GCS_VIDEO_STAGING_BUCKET}/{key}",
            original_url=url,
            bytes_size=video_path.stat().st_size,
            duration_ms=duration_ms,
        )


async def _download_video(
    url: str,
    tmp_path: Path,
    quality: str,
) -> tuple[Path, int | None]:
    out_template = str(tmp_path / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--write-info-json",
        "--no-warnings",
        "--quiet",
        "-f",
        quality,
        "-o",
        out_template,
        url,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
    except TimeoutError as exc:
        await _kill(proc)
        raise VideoStagingTransientError("yt-dlp timeout after 90s") from exc
    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")[:500]
        if _is_permanent_ytdlp_error(stderr_text):
            raise VideoStagingPermanentError(
                f"yt-dlp exit {proc.returncode}: {stderr_text}"
            )
        raise VideoStagingTransientError(
            f"yt-dlp exit {proc.returncode}: {stderr_text}"
        )

    videos = [
        path
        for path in tmp_path.iterdir()
        if path.is_file() and path.suffix not in {".json", ".part"}
    ]
    if not videos:
        raise VideoStagingPermanentError("yt-dlp produced no video file")
    video_path = _downloaded_video_path(tmp_path / "video.info.json", videos)
    duration_ms = _duration_ms(tmp_path / "video.info.json")
    return video_path, duration_ms


def _upload(
    bucket_name: str,
    key: str,
    video_path: Path,
    original_url: str,
    utterance_id: str,
) -> None:
    try:
        from google.cloud import storage  # noqa: PLC0415

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)
        blob.metadata = {
            "original_url": original_url,
            "utterance_id": utterance_id,
        }
        blob.upload_from_filename(str(video_path))
    except Exception as exc:  # pragma: no cover - SDK-specific failure shapes
        logger.warning("video staging upload failed for %s: %s", original_url, exc)
        raise VideoStagingTransientError("gcs upload failed") from exc


def _object_key(job_id: UUID, utterance_id: str, url: str, suffix: str) -> str:
    digest = hashlib.sha256(f"{job_id}:{utterance_id}:{url}".encode()).hexdigest()
    ext = suffix if suffix.startswith(".") else ".mp4"
    return f"video-moderation/{job_id}/{digest[:16]}{ext or '.mp4'}"


def _downloaded_video_path(info_path: Path, videos: list[Path]) -> Path:
    if info_path.exists():
        info = json.loads(info_path.read_text())
        requested_downloads = info.get("requested_downloads")
        if isinstance(requested_downloads, list):
            for item in requested_downloads:
                if isinstance(item, dict) and isinstance(item.get("filepath"), str):
                    candidate = Path(str(item["filepath"]))
                    if candidate.exists():
                        return candidate
        for key in ("filepath", "_filename", "filename"):
            value = info.get(key)
            if isinstance(value, str):
                candidate = Path(value)
                if candidate.exists():
                    return candidate
    return videos[0]


def _duration_ms(info_path: Path) -> int | None:
    if not info_path.exists():
        return None
    info = json.loads(info_path.read_text())
    duration = info.get("duration")
    if duration is None:
        return None
    return int(float(duration) * 1000)


def _is_permanent_ytdlp_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(
        marker in lowered
        for marker in (
            "unsupported url",
            "no suitable extractor",
            "404",
            "not found",
            "private video",
            "video unavailable",
        )
    )


async def _kill(proc: Any) -> None:
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass
