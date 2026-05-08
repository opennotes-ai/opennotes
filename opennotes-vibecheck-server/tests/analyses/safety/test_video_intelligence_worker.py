from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.analyses.safety import video_intelligence_worker
from src.analyses.safety.gcs_video_staging import StagedVideo, VideoStagingPermanentError
from src.analyses.safety.video_intelligence_worker import run_video_intelligence
from src.config import Settings


class _Utterance:
    def __init__(self, uid: str, videos: list[str]) -> None:
        self.utterance_id = uid
        self.mentioned_videos = videos


class _Payload:
    def __init__(self, utterances: list[_Utterance]) -> None:
        self.utterances = utterances


def _settings(**overrides: Any) -> Settings:
    data: dict[str, Any] = {
        "GCS_VIDEO_STAGING_BUCKET": "bucket",
        "MAX_VIDEOS_MODERATED": 5,
    }
    data.update(overrides)
    return Settings(**cast(Any, data))


@pytest.mark.asyncio
async def test_returns_polling_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(video_intelligence_worker, "get_access_token", lambda _scope: "token")
    monkeypatch.setattr(
        video_intelligence_worker,
        "stage_video",
        AsyncMock(return_value=StagedVideo("gs://bucket/a.mp4", "url", 10, 1000)),
    )
    monkeypatch.setattr(
        video_intelligence_worker,
        "submit_explicit_content_annotation",
        AsyncMock(return_value="operations/1"),
    )

    result = await run_video_intelligence(
        None,
        uuid4(),
        uuid4(),
        _Payload([_Utterance("utt-1", ["https://example.com/a.mp4"])]),
        _settings(),
    )

    assert result["status"] == "polling"
    assert result["operations"] == [
        {
            "operation_name": "operations/1",
            "staging_uri": "gs://bucket/a.mp4",
            "video_url": "https://example.com/a.mp4",
            "utterance_id": "utt-1",
        }
    ]


@pytest.mark.asyncio
async def test_respects_max_videos(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = AsyncMock(return_value=StagedVideo("gs://bucket/a.mp4", "url", 10, 1000))
    monkeypatch.setattr(video_intelligence_worker, "get_access_token", lambda _scope: "token")
    monkeypatch.setattr(video_intelligence_worker, "stage_video", stage)
    monkeypatch.setattr(
        video_intelligence_worker,
        "submit_explicit_content_annotation",
        AsyncMock(return_value="operations/1"),
    )

    await run_video_intelligence(
        None,
        uuid4(),
        uuid4(),
        _Payload([_Utterance("utt-1", ["https://example.com/a.mp4", "https://example.com/b.mp4"])]),
        _settings(MAX_VIDEOS_MODERATED=1),
    )

    assert stage.await_count == 1


@pytest.mark.asyncio
async def test_permanent_staging_failure_with_zero_successes_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(video_intelligence_worker, "get_access_token", lambda _scope: "token")
    monkeypatch.setattr(
        video_intelligence_worker,
        "stage_video",
        AsyncMock(side_effect=VideoStagingPermanentError("unsupported")),
    )

    result = await run_video_intelligence(
        None,
        uuid4(),
        uuid4(),
        _Payload([_Utterance("utt-1", ["https://example.com/a.mp4"])]),
        _settings(),
    )

    assert result == {"status": "empty", "matches": []}
