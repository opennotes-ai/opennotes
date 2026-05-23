"""Tests for the Video Intelligence LRO client and ineligible-URL filtering.

TDD: these tests are written before the implementation. They cover:
  - LRO submit request constructs the correct payload + headers
  - parse_explicit_content maps pornographyLikelihood correctly
  - get_operation handles done=True and done=False
  - Transient vs. permanent error classification
  - is_potential_video_url filter (ineligible URL skipping from PR581)
  - Legacy finding shape: VideoModerationMatch accepts both frame_findings and
    segment_findings (PR532 alias backport)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_response(status: int, body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=body)


class TestVideoIntelligenceClient:
    async def test_submit_constructs_correct_request(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import (
            submit_explicit_content_annotation,
        )

        captured: dict[str, Any] = {}

        async def _fake_post(
            url: str, *, headers: dict, json: dict, timeout: float
        ) -> httpx.Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _make_response(200, {"name": "operations/test-op-123"})

        mock_http = AsyncMock()
        mock_http.post = _fake_post

        op_name = await submit_explicit_content_annotation(
            "gs://my-bucket/video.mp4",
            http=mock_http,
            token="test-token-abc",
        )

        assert op_name == "operations/test-op-123"
        assert captured["json"]["inputUri"] == "gs://my-bucket/video.mp4"
        assert "EXPLICIT_CONTENT_DETECTION" in captured["json"]["features"]
        assert captured["headers"]["Authorization"] == "Bearer test-token-abc"

    async def test_submit_raises_transient_on_5xx(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import (
            VITransientError,
            submit_explicit_content_annotation,
        )

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_make_response(503, {"error": "overload"}))

        with pytest.raises(VITransientError):
            await submit_explicit_content_annotation(
                "gs://bucket/v.mp4", http=mock_http, token="tok"
            )

    async def test_submit_raises_permanent_on_400(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import (
            VIPermanentError,
            submit_explicit_content_annotation,
        )

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_make_response(400, {"error": "bad request"}))

        with pytest.raises(VIPermanentError):
            await submit_explicit_content_annotation(
                "gs://bucket/v.mp4", http=mock_http, token="tok"
            )

    async def test_submit_raises_transient_on_429(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import (
            VITransientError,
            submit_explicit_content_annotation,
        )

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_make_response(429, {}))

        with pytest.raises(VITransientError):
            await submit_explicit_content_annotation(
                "gs://bucket/v.mp4", http=mock_http, token="tok"
            )

    async def test_submit_raises_transient_on_network_error(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import (
            VITransientError,
            submit_explicit_content_annotation,
        )

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("timeout"))

        with pytest.raises(VITransientError):
            await submit_explicit_content_annotation(
                "gs://bucket/v.mp4", http=mock_http, token="tok"
            )

    async def test_get_operation_pending(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import get_operation

        body = {"name": "operations/op-1", "done": False}
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_response(200, body))

        status = await get_operation("operations/op-1", http=mock_http, token="tok")

        assert status.name == "operations/op-1"
        assert status.done is False
        assert status.error is None
        assert status.response is None

    async def test_get_operation_done(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import get_operation

        response_body = {"annotationResults": []}
        body = {
            "name": "operations/op-1",
            "done": True,
            "response": response_body,
        }
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_response(200, body))

        status = await get_operation("operations/op-1", http=mock_http, token="tok")

        assert status.done is True
        assert status.error is None
        assert status.response == response_body

    async def test_get_operation_done_with_error(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import get_operation

        body = {
            "name": "operations/op-1",
            "done": True,
            "error": {"code": 500, "message": "internal"},
        }
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_response(200, body))

        status = await get_operation("operations/op-1", http=mock_http, token="tok")

        assert status.done is True
        assert status.error is not None
        assert status.response is None


class TestParseExplicitContent:
    def test_maps_very_likely_to_1(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import parse_explicit_content

        response = {
            "annotationResults": [
                {
                    "explicitAnnotation": {
                        "frames": [{"timeOffset": "1.5s", "pornographyLikelihood": "VERY_LIKELY"}]
                    }
                }
            ]
        }
        findings = parse_explicit_content(response)
        assert len(findings) == 1
        assert findings[0].adult == 1.0
        assert findings[0].max_likelihood == 1.0
        assert findings[0].flagged is True
        assert findings[0].frame_offset_ms == 1500

    def test_maps_unlikely_to_low_score(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import parse_explicit_content

        response = {
            "annotationResults": [
                {
                    "explicitAnnotation": {
                        "frames": [{"timeOffset": "0s", "pornographyLikelihood": "UNLIKELY"}]
                    }
                }
            ]
        }
        findings = parse_explicit_content(response)
        assert len(findings) == 1
        assert findings[0].max_likelihood < 0.5
        assert findings[0].flagged is False

    def test_empty_response_returns_empty_list(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import parse_explicit_content

        findings = parse_explicit_content({})
        assert findings == []

    def test_handles_dict_time_offset(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import parse_explicit_content

        response = {
            "annotationResults": [
                {
                    "explicitAnnotation": {
                        "frames": [
                            {
                                "timeOffset": {"seconds": 2, "nanos": 500_000_000},
                                "pornographyLikelihood": "LIKELY",
                            }
                        ]
                    }
                }
            ]
        }
        findings = parse_explicit_content(response)
        assert len(findings) == 1
        assert findings[0].frame_offset_ms == 2500

    def test_results_sorted_by_offset(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import parse_explicit_content

        response = {
            "annotationResults": [
                {
                    "explicitAnnotation": {
                        "frames": [
                            {"timeOffset": "3s", "pornographyLikelihood": "POSSIBLE"},
                            {"timeOffset": "1s", "pornographyLikelihood": "VERY_UNLIKELY"},
                        ]
                    }
                }
            ]
        }
        findings = parse_explicit_content(response)
        assert findings[0].frame_offset_ms == 1000
        assert findings[1].frame_offset_ms == 3000


class TestIsEligibleVideoUrl:
    def test_mp4_url_is_eligible(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import is_eligible_video_url

        assert is_eligible_video_url("https://example.com/video.mp4") is True

    def test_youtube_url_is_eligible(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import is_eligible_video_url

        assert is_eligible_video_url("https://www.youtube.com/watch?v=abc") is True

    def test_html_page_is_not_eligible(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import is_eligible_video_url

        assert is_eligible_video_url("https://example.com/article.html") is False

    def test_empty_string_is_not_eligible(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import is_eligible_video_url

        assert is_eligible_video_url("") is False

    def test_private_ip_is_not_eligible(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import is_eligible_video_url

        assert is_eligible_video_url("https://192.168.1.1/video.mp4") is False

    def test_webm_extension_is_eligible(self) -> None:
        from src.url_content_scan.analyses.safety.video_intelligence import is_eligible_video_url

        assert is_eligible_video_url("https://cdn.example.com/clip.webm") is True


class TestLegacyFindingShape:
    def test_video_moderation_match_accepts_frame_findings_alias(self) -> None:
        from src.url_content_scan.safety_schemas import VideoModerationMatch

        data = {
            "utterance_id": "u1",
            "video_url": "https://example.com/v.mp4",
            "frame_findings": [
                {
                    "frame_offset_ms": 1000,
                    "adult": 0.9,
                    "violence": 0.0,
                    "racy": 0.9,
                    "medical": 0.0,
                    "spoof": 0.0,
                    "flagged": True,
                    "max_likelihood": 0.9,
                }
            ],
            "flagged": True,
            "max_likelihood": 0.9,
        }
        match = VideoModerationMatch.model_validate(data)
        assert len(match.frame_findings) == 1

    def test_video_moderation_match_accepts_segment_findings_alias(self) -> None:
        from src.url_content_scan.safety_schemas import VideoModerationMatch

        data = {
            "utterance_id": "u1",
            "video_url": "https://example.com/v.mp4",
            "segment_findings": [
                {
                    "frame_offset_ms": 1000,
                    "adult": 0.9,
                    "violence": 0.0,
                    "racy": 0.9,
                    "medical": 0.0,
                    "spoof": 0.0,
                    "flagged": True,
                    "max_likelihood": 0.9,
                }
            ],
            "flagged": True,
            "max_likelihood": 0.9,
        }
        match = VideoModerationMatch.model_validate(data)
        assert len(match.frame_findings) == 1


class TestFailOpenRecommendation:
    async def test_inconclusive_video_only_fails_open_to_safe(self) -> None:
        from src.url_content_scan.analyses.safety.recommendation import (
            SafetyRecommendationInputs,
            _fallback_recommendation,
        )
        from src.url_content_scan.safety_schemas import (
            SafetyLevel,
            VideoModerationMatch,
        )

        inconclusive_match = VideoModerationMatch(
            utterance_id="u1",
            video_url="https://example.com/v.mp4",
            frame_findings=[],
            flagged=True,
            max_likelihood=1.0,
        )
        inputs = SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[inconclusive_match],
            unavailable_inputs=[],
        )

        result = _fallback_recommendation(inputs)

        assert result.level == SafetyLevel.SAFE, (
            "Inconclusive video sampling only should fail open (safe) not block"
        )
        assert "inconclusive" in result.rationale.lower()

    async def test_verified_flagged_video_escalates(self) -> None:
        from src.url_content_scan.analyses.safety.recommendation import (
            SafetyRecommendationInputs,
            _fallback_recommendation,
        )
        from src.url_content_scan.safety_schemas import (
            FrameFinding,
            SafetyLevel,
            VideoModerationMatch,
        )

        frame = FrameFinding(
            frame_offset_ms=1000,
            adult=0.95,
            violence=0.0,
            racy=0.9,
            medical=0.0,
            spoof=0.0,
            flagged=True,
            max_likelihood=0.95,
        )
        verified_match = VideoModerationMatch(
            utterance_id="u1",
            video_url="https://example.com/v.mp4",
            frame_findings=[frame],
            flagged=True,
            max_likelihood=0.95,
        )
        inputs = SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[verified_match],
            unavailable_inputs=[],
        )

        result = _fallback_recommendation(inputs)

        assert result.level == SafetyLevel.UNSAFE
