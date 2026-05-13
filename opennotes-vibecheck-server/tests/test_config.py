"""Behavior contracts for src/config.py field validators (TASK-1485.06 P2.2).

The recent-analyses cache TTL must stay strictly less than the 15-minute
signed-URL validity window, otherwise a cached signed URL could be served
after its underlying signature expired. The pydantic-settings field
validator is what enforces this invariant — these tests prove it bites.
"""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestRecentAnalysesCacheTTL:
    def test_default_value_under_900s(self) -> None:
        s = Settings()
        assert s.VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS < 900

    def test_accepts_zero(self) -> None:
        # Zero is a documented test-mode hint (cache disabled in route).
        s = Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=0)
        assert s.VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS == 0

    def test_accepts_899(self) -> None:
        # 899 = 15 * 60 - 1, the maximum legal value (strict-less-than 900).
        s = Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=899)
        assert s.VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS == 899

    def test_rejects_900(self) -> None:
        # The signed URL is exactly 15 minutes; a cached entry valid for
        # 15 minutes could be served at the moment its URL expires.
        with pytest.raises(ValidationError, match="900"):
            Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=900)

    def test_rejects_901(self) -> None:
        with pytest.raises(ValidationError, match="900"):
            Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=901)

    def test_rejects_one_hour(self) -> None:
        with pytest.raises(ValidationError, match="900"):
            Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=3600)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match=">= 0"):
            Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=-1)

    def test_accepts_one(self) -> None:
        s = Settings(VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS=1)
        assert s.VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS == 1


class TestVideoModerationProvider:
    def test_defaults_preserve_frame_sample_provider(self) -> None:
        s = Settings()
        assert s.VIDEO_MODERATION_PROVIDER == "frame_sample"
        assert s.VIDEO_MODERATION_MAX_WAIT_SEC == 1800
        assert s.GCS_VIDEO_STAGING_BUCKET is None
        assert "height<=480" in s.YT_DLP_VIDEO_QUALITY

    def test_video_intelligence_requires_staging_bucket(self) -> None:
        with pytest.raises(ValidationError, match="GCS_VIDEO_STAGING_BUCKET"):
            Settings(VIDEO_MODERATION_PROVIDER="video_intelligence")

    def test_video_intelligence_accepts_staging_bucket(self) -> None:
        s = Settings(
            VIDEO_MODERATION_PROVIDER="video_intelligence",
            GCS_VIDEO_STAGING_BUCKET="vibecheck-video-staging-prod",
        )
        assert s.VIDEO_MODERATION_PROVIDER == "video_intelligence"
        assert s.GCS_VIDEO_STAGING_BUCKET == "vibecheck-video-staging-prod"


class TestVertexSaturationRetrySettings:
    def test_defaults_define_bounded_retry_policy(self) -> None:
        s = Settings()

        assert s.VERTEX_SATURATION_RETRY_ATTEMPTS == 2
        assert s.VERTEX_SATURATION_RETRY_BASE_MS == 500
        assert s.VERTEX_SATURATION_RETRY_MAX_MS == 4000
        assert s.VERTEX_SATURATION_RETRY_JITTER_MS == 250

    def test_accepts_environment_overrides(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VERTEX_SATURATION_RETRY_ATTEMPTS", "3")
        monkeypatch.setenv("VERTEX_SATURATION_RETRY_BASE_MS", "100")
        monkeypatch.setenv("VERTEX_SATURATION_RETRY_MAX_MS", "1200")
        monkeypatch.setenv("VERTEX_SATURATION_RETRY_JITTER_MS", "50")

        s = Settings()

        assert s.VERTEX_SATURATION_RETRY_ATTEMPTS == 3
        assert s.VERTEX_SATURATION_RETRY_BASE_MS == 100
        assert s.VERTEX_SATURATION_RETRY_MAX_MS == 1200
        assert s.VERTEX_SATURATION_RETRY_JITTER_MS == 50

    def test_zero_attempts_disables_retries(self) -> None:
        s = Settings(VERTEX_SATURATION_RETRY_ATTEMPTS=0)

        assert s.VERTEX_SATURATION_RETRY_ATTEMPTS == 0

    @pytest.mark.parametrize(
        "field",
        [
            "VERTEX_SATURATION_RETRY_ATTEMPTS",
            "VERTEX_SATURATION_RETRY_JITTER_MS",
        ],
    )
    def test_rejects_negative_retry_counts(self, field: str) -> None:
        invalid_settings: dict[str, Any] = {field: -1}

        with pytest.raises(ValidationError, match="must be >= 0"):
            Settings(**invalid_settings)

    @pytest.mark.parametrize(
        "field",
        [
            "VERTEX_SATURATION_RETRY_BASE_MS",
            "VERTEX_SATURATION_RETRY_MAX_MS",
        ],
    )
    def test_rejects_non_positive_retry_intervals(self, field: str) -> None:
        invalid_settings: dict[str, Any] = {field: 0}

        with pytest.raises(ValidationError, match="must be > 0"):
            Settings(**invalid_settings)

    def test_rejects_max_below_base(self) -> None:
        with pytest.raises(ValidationError, match="MAX_MS must be >= BASE_MS"):
            Settings(
                VERTEX_SATURATION_RETRY_BASE_MS=1000,
                VERTEX_SATURATION_RETRY_MAX_MS=999,
            )
