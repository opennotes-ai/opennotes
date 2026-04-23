from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.analyses.safety.video_sampler import (
    FrameBytes,
    VideoSamplingError,
    _offsets,
    sample_video,
)


class FakeProcess:
    def __init__(self, *, returncode=0, stdout=b"", stderr=b"", hang=False):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._hang = hang
        self._terminated = False
        self._killed = False

    async def communicate(self, *_, **__):
        if self._hang:
            await asyncio.sleep(100)
        return self._stdout, self._stderr

    async def wait(self):
        return self.returncode

    def terminate(self):
        self._terminated = True

    def kill(self):
        self._killed = True


FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _make_yt_dlp_process(tmp_dir: str, duration: float = 30.0) -> FakeProcess:
    tmp_path = Path(tmp_dir)
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake video bytes")
    info_file = tmp_path / "video.info.json"
    info_file.write_text(json.dumps({"duration": duration, "title": "test"}))
    return FakeProcess(returncode=0, stdout=b"", stderr=b"")


class TestOffsets:
    def test_offsets_single_frame_returns_zero(self):
        assert _offsets(30000, 1) == [0]

    def test_offsets_three_frames_over_30_seconds(self):
        assert _offsets(30000, 3) == [0, 15000, 30000]

    def test_offsets_five_frames_over_10_seconds(self):
        assert _offsets(10000, 5) == [0, 2500, 5000, 7500, 10000]


class TestSuccessfulSample:
    async def test_successful_sample_returns_frames_at_expected_offsets(self):
        call_count = 0
        captured_tmp: list[str] = []

        async def fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                tmp_dir = None
                for arg in args:
                    if "vibecheck-video-" in str(arg):
                        tmp_dir = str(Path(arg).parent)
                        break
                if tmp_dir is None:
                    for arg in args:
                        if "-o" in str(arg):
                            idx = list(args).index(arg)
                            out_template = args[idx + 1]
                            tmp_dir = str(Path(out_template).parent)
                            break
                if tmp_dir:
                    captured_tmp.append(tmp_dir)
                    return _make_yt_dlp_process(tmp_dir, duration=30.0)
                return FakeProcess(returncode=0)
            else:
                return FakeProcess(returncode=0, stdout=FAKE_PNG, stderr=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            frames = await sample_video("https://example.com/video.mp4", frame_count=3)

        assert len(frames) == 3
        assert frames[0].frame_offset_ms == 0
        assert frames[1].frame_offset_ms == 15000
        assert frames[2].frame_offset_ms == 30000
        for frame in frames:
            assert isinstance(frame, FrameBytes)
            assert frame.png_bytes == FAKE_PNG


class TestYtDlpTimeout:
    async def test_yt_dlp_timeout_raises_video_sampling_error_and_kills_process(self):
        hanging_proc = FakeProcess(returncode=0, hang=True)

        with patch("asyncio.create_subprocess_exec", return_value=hanging_proc):
            with pytest.raises(VideoSamplingError, match="timeout"):
                await sample_video(
                    "https://example.com/video.mp4",
                    download_timeout_s=0,
                )

        assert hanging_proc._terminated is True


class TestYtDlpNonzeroExit:
    async def test_yt_dlp_nonzero_exit_raises_video_sampling_error(self):
        proc = FakeProcess(returncode=1, stdout=b"", stderr=b"download failed")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(VideoSamplingError, match="yt-dlp exit 1"):
                await sample_video("https://example.com/video.mp4")


class TestYtDlpNoOutputFile:
    async def test_yt_dlp_no_output_file_raises(self):
        proc = FakeProcess(returncode=0, stdout=b"", stderr=b"")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(VideoSamplingError, match="no video file"):
                await sample_video("https://example.com/video.mp4")


class TestMissingInfoJson:
    async def test_missing_info_json_raises(self):
        call_count = 0

        async def fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                for i, arg in enumerate(args):
                    if arg == "-o":
                        out_template = args[i + 1]
                        tmp_dir = str(Path(out_template).parent)
                        video_file = Path(tmp_dir) / "video.mp4"
                        video_file.write_bytes(b"fake")
                        break
                return FakeProcess(returncode=0)
            return FakeProcess(returncode=0, stdout=FAKE_PNG, stderr=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with pytest.raises(VideoSamplingError, match="info.json missing"):
                await sample_video("https://example.com/video.mp4")


class TestFfmpegTimeout:
    async def test_ffmpeg_timeout_raises(self):
        call_count = 0

        async def fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                for i, arg in enumerate(args):
                    if arg == "-o":
                        out_template = args[i + 1]
                        tmp_dir = str(Path(out_template).parent)
                        return _make_yt_dlp_process(tmp_dir, duration=10.0)
                return FakeProcess(returncode=0)
            return FakeProcess(returncode=0, hang=True)

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with pytest.raises(VideoSamplingError, match="ffmpeg timeout"):
                await sample_video(
                    "https://example.com/video.mp4",
                    frame_count=1,
                    extract_timeout_s=0,
                )


class TestFfmpegNonzeroExit:
    async def test_ffmpeg_nonzero_exit_raises(self):
        call_count = 0

        async def fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                for i, arg in enumerate(args):
                    if arg == "-o":
                        out_template = args[i + 1]
                        tmp_dir = str(Path(out_template).parent)
                        return _make_yt_dlp_process(tmp_dir, duration=10.0)
                return FakeProcess(returncode=0)
            return FakeProcess(returncode=1, stdout=b"", stderr=b"codec error")

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with pytest.raises(VideoSamplingError, match="ffmpeg exit 1"):
                await sample_video(
                    "https://example.com/video.mp4",
                    frame_count=1,
                )


class TestFfmpegEmptyStdout:
    async def test_ffmpeg_empty_stdout_raises(self):
        call_count = 0

        async def fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                for i, arg in enumerate(args):
                    if arg == "-o":
                        out_template = args[i + 1]
                        tmp_dir = str(Path(out_template).parent)
                        return _make_yt_dlp_process(tmp_dir, duration=10.0)
                return FakeProcess(returncode=0)
            return FakeProcess(returncode=0, stdout=b"", stderr=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with pytest.raises(VideoSamplingError, match="empty frame"):
                await sample_video(
                    "https://example.com/video.mp4",
                    frame_count=1,
                )


class TestUrlNotShellConcatenated:
    async def test_url_never_passed_through_shell(self):
        captured_calls: list[tuple] = []

        async def fake_exec(*args, **kwargs):
            captured_calls.append(args)
            if len(captured_calls) == 1:
                for i, arg in enumerate(args):
                    if arg == "-o":
                        out_template = args[i + 1]
                        tmp_dir = str(Path(out_template).parent)
                        return _make_yt_dlp_process(tmp_dir, duration=5.0)
                return FakeProcess(returncode=0)
            return FakeProcess(returncode=0, stdout=FAKE_PNG, stderr=b"")

        test_url = "https://example.com/watch?v=abc123"
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            await sample_video(test_url, frame_count=1)

        assert len(captured_calls) >= 1
        yt_dlp_args = captured_calls[0]
        assert test_url in yt_dlp_args, "URL must be a standalone argv element"
        for arg in yt_dlp_args:
            if isinstance(arg, str) and test_url in arg and arg != test_url:
                pytest.fail(f"URL was concatenated into another argument: {arg!r}")


class TestTempDirCleanup:
    async def test_temp_dir_cleaned_up_on_exception(self):
        created_dirs: list[str] = []
        original_tempdir = tempfile.TemporaryDirectory

        class TrackingTempDir:
            def __init__(self, **kwargs):
                self._delegate = original_tempdir(**kwargs)
                created_dirs.append(self._delegate.name)

            def __enter__(self):
                return self._delegate.__enter__()

            def __exit__(self, *args):
                return self._delegate.__exit__(*args)

        proc = FakeProcess(returncode=1, stdout=b"", stderr=b"download error")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("tempfile.TemporaryDirectory", TrackingTempDir):
                with pytest.raises(VideoSamplingError):
                    await sample_video("https://example.com/video.mp4")

        assert len(created_dirs) >= 1
        for tmp_dir in created_dirs:
            assert not Path(tmp_dir).exists(), f"Temp dir {tmp_dir!r} was not cleaned up"
