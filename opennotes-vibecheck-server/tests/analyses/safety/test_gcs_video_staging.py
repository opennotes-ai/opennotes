from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from src.analyses.safety import gcs_video_staging
from src.analyses.safety.gcs_video_staging import (
    VideoStagingPermanentError,
    _object_key,
    stage_video,
)
from src.config import Settings


class _FakeProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


@pytest.mark.asyncio
async def test_stage_video_uses_configured_quality_and_uploads_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    uploads: list[tuple[str, str, Path, str, str]] = []

    async def fake_exec(*cmd, **_kwargs):
        commands.append(list(cmd))
        output_template = Path(cmd[cmd.index("-o") + 1])
        video_path = output_template.with_name("video.mp4")
        video_path.write_bytes(b"video")
        output_template.with_name("video.info.json").write_text(
            json.dumps({"duration": 3.5, "filepath": str(video_path)})
        )
        return _FakeProcess()

    def fake_upload(bucket, key, video_path, original_url, utterance_id):
        uploads.append((bucket, key, video_path, original_url, utterance_id))

    monkeypatch.setattr(gcs_video_staging.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(gcs_video_staging, "_upload", fake_upload)

    settings = Settings(
        GCS_VIDEO_STAGING_BUCKET="bucket",
        YT_DLP_VIDEO_QUALITY="best[height<=360]",
    )
    staged = await stage_video(
        "https://example.com/video.mp4",
        job_id=UUID("00000000-0000-0000-0000-000000000001"),
        utterance_id="utt-1",
        settings=settings,
    )

    assert "-f" in commands[0]
    assert commands[0][commands[0].index("-f") + 1] == "best[height<=360]"
    assert staged.gs_uri.startswith("gs://bucket/video-moderation/")
    assert staged.bytes_size == 5
    assert staged.duration_ms == 3500
    assert uploads[0][0] == "bucket"
    assert uploads[0][3] == "https://example.com/video.mp4"
    assert uploads[0][4] == "utt-1"


def test_object_key_is_stable_for_retry_identity() -> None:
    job_id = UUID("00000000-0000-0000-0000-000000000001")

    first = _object_key(job_id, "utt-1", "https://example.com/video.mp4", ".mp4")
    second = _object_key(job_id, "utt-1", "https://example.com/video.mp4", ".mp4")

    assert first == second
    assert first.endswith(".mp4")


@pytest.mark.asyncio
async def test_stage_video_requires_bucket() -> None:
    with pytest.raises(VideoStagingPermanentError, match="GCS_VIDEO_STAGING_BUCKET"):
        await stage_video(
            "https://example.com/video.mp4",
            job_id=UUID("00000000-0000-0000-0000-000000000001"),
            utterance_id="utt-1",
            settings=Settings(),
        )
