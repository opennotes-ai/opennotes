from __future__ import annotations

import pytest

from src.url_content_scan.analyses.safety.vision import FLAG_THRESHOLD

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_inputs(
    *,
    image_moderation_matches=None,
    web_risk_findings=None,
    video_moderation_matches=None,
):
    from src.url_content_scan.analyses.safety.recommendation import SafetyRecommendationInputs

    return SafetyRecommendationInputs(
        harmful_content_matches=[],
        web_risk_findings=web_risk_findings or [],
        image_moderation_matches=image_moderation_matches or [],
        video_moderation_matches=video_moderation_matches or [],
        unavailable_inputs=[],
    )


def _image_match(image_url: str, *, flagged: bool = True, max_likelihood: float = 0.9):
    from src.url_content_scan.safety_schemas import ImageModerationMatch

    return ImageModerationMatch(
        utterance_id="u-1",
        image_url=image_url,
        adult=0.0,
        violence=max_likelihood if flagged else 0.0,
        racy=0.0,
        medical=0.0,
        spoof=0.0,
        flagged=flagged,
        max_likelihood=max_likelihood,
    )


def _video_match(*, flagged: bool = True, max_likelihood: float = 0.9, has_segment_findings=True):
    from src.url_content_scan.safety_schemas import FrameFinding, VideoModerationMatch

    segment_findings = (
        [
            FrameFinding(
                frame_offset_ms=0,
                adult=0.0,
                violence=max_likelihood,
                racy=0.0,
                medical=0.0,
                spoof=0.0,
                flagged=flagged,
                max_likelihood=max_likelihood,
            )
        ]
        if has_segment_findings
        else []
    )
    return VideoModerationMatch(
        utterance_id="u-v1",
        video_url="https://example.com/clip.mp4",
        frame_findings=segment_findings,
        flagged=flagged,
        max_likelihood=max_likelihood,
    )


def _web_risk_finding():
    from src.url_content_scan.safety_schemas import WebRiskFinding

    return WebRiskFinding(url="https://example.com/bad", threat_types=["MALWARE"])


def test_select_images_returns_flagged_urls_when_image_is_sole_signal():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[
            _image_match("https://cdn.example.com/a.png"),
            _image_match("https://cdn.example.com/b.png"),
        ]
    )
    result = select_images_for_vision_review(inputs, cap=5)
    assert result == [
        "https://cdn.example.com/a.png",
        "https://cdn.example.com/b.png",
    ]


def test_select_images_respects_cap():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[
            _image_match(f"https://cdn.example.com/{i}.png") for i in range(5)
        ]
    )
    result = select_images_for_vision_review(inputs, cap=2)
    assert len(result) == 2


def test_select_images_returns_empty_when_cap_is_zero():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(image_moderation_matches=[_image_match("https://cdn.example.com/a.png")])
    result = select_images_for_vision_review(inputs, cap=0)
    assert result == []


def test_select_images_excludes_non_flagged_images():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[
            _image_match("https://cdn.example.com/safe.png", flagged=False, max_likelihood=0.1),
        ]
    )
    result = select_images_for_vision_review(inputs, cap=5)
    assert result == []


def test_select_images_includes_image_at_exact_threshold():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[
            _image_match(
                "https://cdn.example.com/threshold.png",
                flagged=False,
                max_likelihood=FLAG_THRESHOLD,
            ),
        ]
    )
    result = select_images_for_vision_review(inputs, cap=5)
    assert result == ["https://cdn.example.com/threshold.png"]


def test_select_images_skips_vision_when_web_risk_is_present():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[_image_match("https://cdn.example.com/a.png")],
        web_risk_findings=[_web_risk_finding()],
    )
    result = select_images_for_vision_review(inputs, cap=5)
    assert result == []


def test_select_images_skips_vision_when_verified_video_signal_present():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[_image_match("https://cdn.example.com/a.png")],
        video_moderation_matches=[_video_match(flagged=True, has_segment_findings=True)],
    )
    result = select_images_for_vision_review(inputs, cap=5)
    assert result == []


def test_select_images_runs_when_video_is_inconclusive_no_segment_findings():
    from src.url_content_scan.analyses.safety.vision_review_selection import (
        select_images_for_vision_review,
    )

    inputs = _make_inputs(
        image_moderation_matches=[_image_match("https://cdn.example.com/a.png")],
        video_moderation_matches=[_video_match(flagged=True, has_segment_findings=False)],
    )
    result = select_images_for_vision_review(inputs, cap=5)
    assert result == ["https://cdn.example.com/a.png"]
