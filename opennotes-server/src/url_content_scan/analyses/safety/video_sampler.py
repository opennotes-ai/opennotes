from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.utils.url_security import InvalidURL, validate_public_http_url


@dataclass(frozen=True)
class FrameBytes:
    frame_offset_ms: int
    png_bytes: bytes


class VideoSamplingError(Exception):
    pass


async def sample_video(
    url: str,
    *,
    frame_count: int = 3,
    max_bytes: int = 50_000_000,
    download_timeout_s: int = 60,
    extract_timeout_s: int = 30,
) -> list[FrameBytes]:
    if frame_count < 1:
        raise ValueError("frame_count must be >= 1")
    try:
        safe_url = validate_public_http_url(url)
    except InvalidURL as exc:
        raise VideoSamplingError(f"url rejected: {exc.reason}") from exc

    with tempfile.TemporaryDirectory(prefix="url-scan-video-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        video_path, duration_ms = await _download(
            safe_url,
            tmp_path,
            max_bytes=max_bytes,
            timeout_s=download_timeout_s,
        )
        return [
            FrameBytes(
                frame_offset_ms=offset,
                png_bytes=await _extract_frame(video_path, offset, timeout_s=extract_timeout_s),
            )
            for offset in _offsets(duration_ms, frame_count)
        ]


def _offsets(duration_ms: int, frame_count: int) -> list[int]:
    if frame_count == 1 or duration_ms <= 0:
        return [0]
    tail_ms = 100 if duration_ms > 100 else 0
    usable_ms = duration_ms - tail_ms
    step = usable_ms / (frame_count - 1)
    return [round(index * step) for index in range(frame_count)]


async def _download(
    url: str,
    tmp_path: Path,
    *,
    max_bytes: int,
    timeout_s: int,
) -> tuple[Path, int]:
    out_template = str(tmp_path / "video.%(ext)s")
    process = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--no-playlist",
        "--max-filesize",
        str(max_bytes),
        "--write-info-json",
        "--no-warnings",
        "--quiet",
        "-o",
        out_template,
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError as exc:
        await _kill(process)
        raise VideoSamplingError(f"yt-dlp timeout after {timeout_s}s") from exc
    if process.returncode != 0:
        raise VideoSamplingError(
            f"yt-dlp exit {process.returncode}: {stderr.decode(errors='replace')[:200]}"
        )

    videos = [
        item
        for item in tmp_path.iterdir()
        if item.is_file()
        and item.name != "video.info.json"
        and item.suffix not in {".json", ".part"}
    ]
    if not videos:
        raise VideoSamplingError("yt-dlp produced no video file")
    info_path = tmp_path / "video.info.json"
    if not info_path.exists():
        raise VideoSamplingError("yt-dlp info.json missing")
    info = json.loads(info_path.read_text())
    video_path = _downloaded_video_path(info, videos)
    if video_path is None:
        raise VideoSamplingError("yt-dlp produced no video file")
    return video_path, int(float(info.get("duration") or 0) * 1000)


def _downloaded_video_path(info: dict[str, object], videos: list[Path]) -> Path | None:
    requested_downloads = info.get("requested_downloads")
    if isinstance(requested_downloads, list):
        for item in requested_downloads:
            if not isinstance(item, dict):
                continue
            filepath = item.get("filepath")
            if isinstance(filepath, str):
                candidate = Path(filepath)
                if candidate.exists():
                    return candidate
    for key in ("filepath", "_filename", "filename"):
        value = info.get(key)
        if isinstance(value, str):
            candidate = Path(value)
            if candidate.exists():
                return candidate
    return videos[0] if videos else None


async def _extract_frame(video_path: Path, offset_ms: int, *, timeout_s: int) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-ss",
        f"{offset_ms / 1000:.3f}",
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-vf",
        "scale=640:-1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError as exc:
        await _kill(process)
        raise VideoSamplingError(f"ffmpeg timeout at offset={offset_ms}ms") from exc
    if process.returncode != 0:
        raise VideoSamplingError(
            f"ffmpeg exit {process.returncode}: {stderr.decode(errors='replace')[:200]}"
        )
    if not stdout:
        raise VideoSamplingError("ffmpeg produced empty frame")
    return stdout


async def _kill(process: asyncio.subprocess.Process) -> None:
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except TimeoutError:
            process.kill()
            await process.wait()
    except ProcessLookupError:
        pass
