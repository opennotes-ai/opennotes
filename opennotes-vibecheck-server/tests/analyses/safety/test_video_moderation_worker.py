from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.analyses.safety._schemas import FrameFinding
from src.analyses.safety.video_moderation_worker import run_video_moderation
from src.analyses.safety.video_sampler import FrameBytes, VideoSamplingError
from src.analyses.safety.vision_client import VisionTransientError
from src.config import Settings


def _make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "MAX_IMAGES_MODERATED": 30,
        "MAX_VIDEOS_MODERATED": 5,
    }
    base.update(overrides)
    return Settings(**base)


class _Utterance:
    def __init__(self, uid: str, videos: list[str]):
        self.utterance_id = uid
        self.mentioned_videos = videos


class _Payload:
    def __init__(self, utterances: list[_Utterance]):
        self.utterances = utterances


FAKE_TOKEN = "fake-token-video"

CLEAN_ANNOTATION = {
    "adult": "VERY_UNLIKELY",
    "violence": "VERY_UNLIKELY",
    "racy": "VERY_UNLIKELY",
    "medical": "VERY_UNLIKELY",
    "spoof": "VERY_UNLIKELY",
}

ADULT_ANNOTATION = {
    "adult": "VERY_LIKELY",
    "violence": "VERY_UNLIKELY",
    "racy": "VERY_UNLIKELY",
    "medical": "VERY_UNLIKELY",
    "spoof": "VERY_UNLIKELY",
}


def _fake_frames(count: int = 2) -> list[FrameBytes]:
    return [FrameBytes(frame_offset_ms=i * 1000, png_bytes=b"PNG" + bytes([i])) for i in range(count)]


def _clean_frame_findings(count: int = 1) -> list[FrameFinding]:
    return [
        FrameFinding(
            frame_offset_ms=i * 1000,
            adult=0.0, violence=0.0, racy=0.0, medical=0.0, spoof=0.0,
            flagged=False, max_likelihood=0.0,
        )
        for i in range(count)
    ]


def _adult_frame_finding() -> FrameFinding:
    return FrameFinding(
        frame_offset_ms=1000,
        adult=1.0, violence=0.0, racy=0.0, medical=0.0, spoof=0.0,
        flagged=True, max_likelihood=1.0,
    )


@pytest.mark.asyncio
async def test_empty_videos_returns_empty_matches_no_http():
    payload = _Payload([])
    settings = _make_settings()
    with patch("src.analyses.safety.video_moderation_worker.get_access_token", return_value=FAKE_TOKEN):  # noqa: SIM117
        with patch("src.analyses.safety.video_moderation_worker.sample_video") as mock_sample:
            with patch("src.analyses.safety.video_moderation_worker._annotate_frames") as mock_annotate:
                result = await run_video_moderation(None, uuid4(), uuid4(), payload, settings)
    assert result == {"matches": []}
    mock_sample.assert_not_called()
    mock_annotate.assert_not_called()


@pytest.mark.asyncio
async def test_flattens_per_utterance_videos_and_caps(caplog):
    videos = [f"https://example.com/vid{i}.mp4" for i in range(7)]
    payload = _Payload([_Utterance("utt-1", videos)])
    settings = _make_settings(MAX_VIDEOS_MODERATED=5)

    processed: list[str] = []

    async def fake_sample(url: str, **kwargs):
        processed.append(url)
        return _fake_frames(1)

    with patch("src.analyses.safety.video_moderation_worker.get_access_token", return_value=FAKE_TOKEN):  # noqa: SIM117
        with patch("src.analyses.safety.video_moderation_worker.sample_video", new=fake_sample):
            with patch(
                "src.analyses.safety.video_moderation_worker._annotate_frames",
                new=AsyncMock(return_value=_clean_frame_findings(1)),
            ):
                with caplog.at_level(logging.INFO, logger="src.analyses.safety.video_moderation_worker"):
                    result = await run_video_moderation(None, uuid4(), uuid4(), payload, settings)

    assert len(processed) == 5
    assert len(result["matches"]) == 5
    assert any("dropped=2" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_sampler_error_emits_empty_frame_findings_match_and_continues():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/bad.mp4", "https://example.com/ok.mp4"]),
    ])
    settings = _make_settings()

    async def fake_sample(url: str, **kwargs):
        if "bad" in url:
            raise VideoSamplingError("yt-dlp exit 1: error")
        return _fake_frames(1)

    with patch("src.analyses.safety.video_moderation_worker.get_access_token", return_value=FAKE_TOKEN):  # noqa: SIM117
        with patch("src.analyses.safety.video_moderation_worker.sample_video", new=fake_sample):
            with patch(
                "src.analyses.safety.video_moderation_worker._annotate_frames",
                new=AsyncMock(return_value=_clean_frame_findings(1)),
            ):
                result = await run_video_moderation(None, uuid4(), uuid4(), payload, settings)

    assert len(result["matches"]) == 2
    bad_match = result["matches"][0]
    assert bad_match["video_url"] == "https://example.com/bad.mp4"
    assert bad_match["frame_findings"] == []
    # Sampling failure is indeterminate; conservatively flagged (codex P1.3).
    assert bad_match["flagged"] is True
    assert bad_match["max_likelihood"] == 1.0

    ok_match = result["matches"][1]
    assert ok_match["video_url"] == "https://example.com/ok.mp4"
    assert len(ok_match["frame_findings"]) == 1


@pytest.mark.asyncio
async def test_vision_transient_error_raises():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/vid.mp4"]),
    ])
    settings = _make_settings()

    with patch("src.analyses.safety.video_moderation_worker.get_access_token", return_value=FAKE_TOKEN):  # noqa: SIM117
        with patch(
            "src.analyses.safety.video_moderation_worker.sample_video",
            new=AsyncMock(return_value=_fake_frames(1)),
        ):
            with patch(
                "src.analyses.safety.video_moderation_worker._annotate_frames",
                new=AsyncMock(side_effect=VisionTransientError("vision-frames 503")),
            ):
                with pytest.raises(VisionTransientError, match="503"):
                    await run_video_moderation(None, uuid4(), uuid4(), payload, settings)


@pytest.mark.asyncio
async def test_aggregate_max_likelihood_and_flagged_across_frames():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/vid.mp4"]),
    ])
    settings = _make_settings()

    mixed_findings = [_clean_frame_findings(1)[0], _adult_frame_finding()]

    with patch("src.analyses.safety.video_moderation_worker.get_access_token", return_value=FAKE_TOKEN):  # noqa: SIM117
        with patch(
            "src.analyses.safety.video_moderation_worker.sample_video",
            new=AsyncMock(return_value=_fake_frames(2)),
        ):
            with patch(
                "src.analyses.safety.video_moderation_worker._annotate_frames",
                new=AsyncMock(return_value=mixed_findings),
            ):
                result = await run_video_moderation(None, uuid4(), uuid4(), payload, settings)

    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["flagged"] is True
    assert match["max_likelihood"] == 1.0
    assert len(match["frame_findings"]) == 2
    assert match["frame_findings"][0]["flagged"] is False
    assert match["frame_findings"][1]["flagged"] is True
    assert match["frame_findings"][1]["adult"] == 1.0


@pytest.mark.asyncio
async def test_missing_adc_token_raises_transient_error():
    payload = _Payload([
        _Utterance("utt-1", ["https://example.com/vid.mp4"]),
    ])
    settings = _make_settings()
    with patch("src.analyses.safety.video_moderation_worker.get_access_token", return_value=None):  # noqa: SIM117
        with pytest.raises(VisionTransientError, match="ADC token unavailable"):
            await run_video_moderation(None, uuid4(), uuid4(), payload, settings)
