"""Behavior contracts for the safety analysis schemas (TASK-1474.02)."""
from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError

from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    VideoSegmentFinding,
    WebRiskFinding,
)
from src.analyses.safety._vision_likelihood import likelihood_to_score
from src.analyses.schemas import SafetySection


class TestWebRiskFinding:
    def test_valid_threat_type_accepted(self) -> None:
        finding = WebRiskFinding(url="https://evil.example.com", threat_types=["MALWARE"])
        assert finding.url == "https://evil.example.com"
        assert finding.threat_types == ["MALWARE"]

    def test_web_risk_finding_rejects_unknown_threat_type(self) -> None:
        with pytest.raises(ValidationError):
            WebRiskFinding(
                url="https://evil.example.com",
                threat_types=cast(Any, ["UNKNOWN_THREAT"]),
            )

    def test_all_valid_threat_types_accepted(self) -> None:
        finding = WebRiskFinding(
            url="https://evil.example.com",
            threat_types=[
                "MALWARE",
                "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
        )
        assert len(finding.threat_types) == 4


class TestHarmfulContentMatch:
    def test_harmful_content_match_backfills_missing_source_to_openai(self) -> None:
        # Pre PR #411 payloads did not carry `source`. Reading them back
        # via `SidebarPayload.model_validate` on the poll endpoint must
        # not raise — default to "openai" so the job stays viewable.
        match = HarmfulContentMatch.model_validate(
            {
                "utterance_id": "utt_1",
                "utterance_text": "some text",
                "max_score": 0.5,
                "categories": {"hate": False},
                "scores": {"hate": 0.5},
                "flagged_categories": [],
            }
        )
        assert match.source == "openai"

    def test_harmful_content_match_backfills_missing_utterance_text(self) -> None:
        # Pre PR #411 payloads also predated the `utterance_text` column.
        match = HarmfulContentMatch.model_validate(
            {
                "utterance_id": "utt_1",
                "max_score": 0.5,
                "categories": {"hate": False},
                "scores": {"hate": 0.5},
            }
        )
        assert match.utterance_text == ""
        assert match.source == "openai"

    def test_harmful_content_match_rejects_invalid_source(self) -> None:
        with pytest.raises(ValidationError):
            HarmfulContentMatch(
                utterance_id="utt_1",
                utterance_text="some text",
                max_score=0.5,
                categories={"hate": False},
                scores={"hate": 0.5},
                flagged_categories=[],
                source=cast(Any, "azure"),
            )

    def test_harmful_content_match_accepts_openai_source(self) -> None:
        match = HarmfulContentMatch(
            utterance_id="utt_1",
            utterance_text="some text",
            max_score=0.5,
            categories={"hate": False},
            scores={"hate": 0.5},
            flagged_categories=[],
            source="openai",
        )
        assert match.source == "openai"

    def test_harmful_content_match_accepts_gcp_source(self) -> None:
        match = HarmfulContentMatch(
            utterance_id="utt_1",
            utterance_text="some text",
            max_score=0.5,
            categories={"hate": False},
            scores={"hate": 0.5},
            flagged_categories=[],
            source="gcp",
        )
        assert match.source == "gcp"


class TestSafetyRecommendation:
    def test_safety_level_order_includes_mild_between_safe_and_caution(self) -> None:
        assert list(SafetyLevel) == [
            SafetyLevel.SAFE,
            SafetyLevel.MILD,
            SafetyLevel.CAUTION,
            SafetyLevel.UNSAFE,
        ]

    def test_safety_recommendation_accepts_level_rationale_and_signal_lists(self) -> None:
        recommendation = SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Some safety signals were inconclusive.",
            top_signals=["web risk unavailable"],
            unavailable_inputs=["web_risk"],
        )

        assert recommendation.level == SafetyLevel.CAUTION
        assert recommendation.top_signals == ["web risk unavailable"]
        assert recommendation.unavailable_inputs == ["web_risk"]

    def test_safety_recommendation_rejects_unknown_level(self) -> None:
        with pytest.raises(ValidationError):
            SafetyRecommendation(
                level=cast(Any, "critical"),
                rationale="unsupported level",
            )

    def test_safety_recommendation_defaults_lists_to_empty(self) -> None:
        recommendation = SafetyRecommendation(
            level=SafetyLevel.SAFE,
            rationale="No safety issues detected.",
        )

        assert recommendation.top_signals == []
        assert recommendation.unavailable_inputs == []

    def test_safety_recommendation_round_trips_mild_level(self) -> None:
        recommendation = SafetyRecommendation(
            level=SafetyLevel.MILD,
            rationale="One minor verified safety signal.",
        )

        serialized = recommendation.model_dump_json()
        restored = SafetyRecommendation.model_validate_json(serialized)

        assert recommendation.model_dump()["level"] == SafetyLevel.MILD
        assert restored.level == SafetyLevel.MILD
        assert restored.rationale == "One minor verified safety signal."

    def test_safety_section_recommendation_defaults_to_none(self) -> None:
        section = SafetySection.model_validate({"harmful_content_matches": []})

        assert section.recommendation is None

    def test_safety_section_accepts_embedded_recommendation(self) -> None:
        section = SafetySection.model_validate(
            {
                "harmful_content_matches": [],
                "recommendation": {
                    "level": "safe",
                    "rationale": "No safety issues detected.",
                    "top_signals": [],
                    "unavailable_inputs": [],
                },
            }
        )

        assert section.recommendation is not None
        assert section.recommendation.level == SafetyLevel.SAFE


class TestImageModerationMatch:
    def test_image_moderation_match_round_trip(self) -> None:
        match = ImageModerationMatch(
            utterance_id="utt_img_1",
            image_url="https://example.com/image.jpg",
            adult=0.1,
            violence=0.0,
            racy=0.2,
            medical=0.0,
            spoof=0.0,
            flagged=False,
            max_likelihood=0.2,
        )
        assert match.utterance_id == "utt_img_1"
        assert match.image_url == "https://example.com/image.jpg"
        assert match.adult == 0.1
        assert match.racy == 0.2
        assert match.flagged is False
        assert match.max_likelihood == 0.2


class TestVideoModerationMatch:
    def test_video_moderation_match_round_trip_with_segment_findings(self) -> None:
        frame = VideoSegmentFinding(
            start_offset_ms=1000,
            end_offset_ms=1000,
            adult=0.75,
            violence=0.1,
            racy=0.5,
            medical=0.0,
            spoof=0.0,
            flagged=True,
            max_likelihood=0.75,
        )
        match = VideoModerationMatch(
            utterance_id="utt_vid_1",
            video_url="https://example.com/video.mp4",
            segment_findings=[frame],
            flagged=True,
            max_likelihood=0.75,
        )
        assert match.utterance_id == "utt_vid_1"
        assert match.video_url == "https://example.com/video.mp4"
        assert len(match.segment_findings) == 1
        assert match.segment_findings[0].start_offset_ms == 1000
        assert match.segment_findings[0].end_offset_ms == 1000
        assert match.segment_findings[0].adult == 0.75
        assert match.flagged is True
        assert match.max_likelihood == 0.75

    def test_video_moderation_match_empty_segment_findings(self) -> None:
        match = VideoModerationMatch(
            utterance_id="utt_vid_2",
            video_url="https://example.com/video2.mp4",
            segment_findings=[],
            flagged=False,
            max_likelihood=0.0,
        )
        assert match.segment_findings == []

    def test_video_moderation_match_accepts_legacy_frame_findings(self) -> None:
        match = VideoModerationMatch.model_validate(
            {
                "utterance_id": "utt_vid_legacy",
                "video_url": "https://example.com/legacy.mp4",
                "frame_findings": [
                    {
                        "start_offset_ms": 1250,
                        "end_offset_ms": 1250,
                        "adult": 0.0,
                        "violence": 1.0,
                        "racy": 0.0,
                        "medical": 0.0,
                        "spoof": 0.0,
                        "flagged": True,
                        "max_likelihood": 1.0,
                    }
                ],
                "flagged": True,
                "max_likelihood": 1.0,
            }
        )

        assert len(match.segment_findings) == 1
        assert match.segment_findings[0].start_offset_ms == 1250
        dumped = match.model_dump(mode="json")
        assert "segment_findings" in dumped
        assert "frame_findings" not in dumped


class TestVisionLikelihood:
    def test_vision_likelihood_maps_very_likely_to_one(self) -> None:
        assert likelihood_to_score("VERY_LIKELY") == 1.0

    def test_vision_likelihood_defaults_unknown_to_inconclusive(self) -> None:
        assert likelihood_to_score("UNKNOWN") == 0.5

    def test_very_unlikely_maps_to_zero(self) -> None:
        assert likelihood_to_score("VERY_UNLIKELY") == 0.0

    def test_unlikely_maps_to_quarter(self) -> None:
        assert likelihood_to_score("UNLIKELY") == 0.25

    def test_possible_maps_to_half(self) -> None:
        assert likelihood_to_score("POSSIBLE") == 0.5

    def test_likely_maps_to_three_quarters(self) -> None:
        assert likelihood_to_score("LIKELY") == 0.75

    def test_case_insensitive(self) -> None:
        assert likelihood_to_score("very_likely") == 1.0

    def test_unrecognized_value_defaults_to_zero(self) -> None:
        assert likelihood_to_score("NONEXISTENT") == 0.0
