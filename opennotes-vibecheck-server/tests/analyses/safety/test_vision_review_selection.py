from __future__ import annotations

from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    VideoModerationMatch,
    VideoSegmentFinding,
    WebRiskFinding,
)
from src.analyses.safety.recommendation_agent import SafetyRecommendationInputs
from src.analyses.safety.vision_client import FLAG_THRESHOLD
from src.analyses.safety.vision_review_selection import (
    select_images_for_vision_review,
)


def _image(
    url: str,
    *,
    flagged: bool = False,
    max_likelihood: float = 0.0,
    utterance_id: str = "u1",
) -> ImageModerationMatch:
    return ImageModerationMatch(
        utterance_id=utterance_id,
        image_url=url,
        adult=0.0,
        violence=0.0,
        racy=0.0,
        medical=0.0,
        spoof=0.0,
        flagged=flagged,
        max_likelihood=max_likelihood,
    )


def _inputs(
    *,
    images: list[ImageModerationMatch] | None = None,
    text: list[HarmfulContentMatch] | None = None,
    web_risk: list[WebRiskFinding] | None = None,
    videos: list[VideoModerationMatch] | None = None,
    unavailable: list[str] | None = None,
) -> SafetyRecommendationInputs:
    return SafetyRecommendationInputs(
        harmful_content_matches=text or [],
        web_risk_findings=web_risk or [],
        image_moderation_matches=images or [],
        video_moderation_matches=videos or [],
        unavailable_inputs=unavailable or [],
    )


def _text_match(uid: str = "u1") -> HarmfulContentMatch:
    return HarmfulContentMatch(
        utterance_id=uid,
        utterance_text=f"comment {uid}",
        max_score=0.62,
        categories={"harassment": True},
        scores={"harassment": 0.62},
        flagged_categories=["harassment"],
        source="gcp",
    )


def _web_risk(url: str = "https://bad.example") -> WebRiskFinding:
    return WebRiskFinding(url=url, threat_types=["MALWARE"])


def _video_verified(uid: str = "u1") -> VideoModerationMatch:
    return VideoModerationMatch(
        utterance_id=uid,
        video_url="https://cdn.example/video.mp4",
        segment_findings=[
            VideoSegmentFinding(
                start_offset_ms=0,
                end_offset_ms=1000,
                adult=0.0,
                violence=0.0,
                racy=0.0,
                medical=0.0,
                spoof=0.0,
                flagged=True,
                max_likelihood=FLAG_THRESHOLD,
            )
        ],
        flagged=True,
        max_likelihood=FLAG_THRESHOLD,
    )


def test_empty_inputs_returns_empty() -> None:
    assert select_images_for_vision_review(_inputs(), cap=5) == []


def test_single_flagged_image_no_other_signals_returned() -> None:
    url = "https://cdn.example/a.jpg"
    inputs = _inputs(images=[_image(url, flagged=True)])

    assert select_images_for_vision_review(inputs, cap=5) == [url]


def test_unflagged_but_above_threshold_returned() -> None:
    url = "https://cdn.example/b.jpg"
    inputs = _inputs(
        images=[_image(url, flagged=False, max_likelihood=FLAG_THRESHOLD)]
    )

    assert select_images_for_vision_review(inputs, cap=5) == [url]


def test_unflagged_below_threshold_excluded() -> None:
    inputs = _inputs(
        images=[
            _image(
                "https://cdn.example/c.jpg",
                flagged=False,
                max_likelihood=FLAG_THRESHOLD - 0.01,
            )
        ]
    )

    assert select_images_for_vision_review(inputs, cap=5) == []


def test_multiple_flagged_returns_input_order() -> None:
    urls = [
        "https://cdn.example/1.jpg",
        "https://cdn.example/2.jpg",
        "https://cdn.example/3.jpg",
    ]
    inputs = _inputs(images=[_image(u, flagged=True) for u in urls])

    assert select_images_for_vision_review(inputs, cap=10) == urls


def test_flagged_image_with_web_risk_still_returned() -> None:
    url = "https://cdn.example/d.jpg"
    inputs = _inputs(
        images=[_image(url, flagged=True)],
        web_risk=[_web_risk()],
    )

    assert select_images_for_vision_review(inputs, cap=5) == [url]


def test_flagged_image_with_text_match_still_returned() -> None:
    url = "https://cdn.example/e.jpg"
    inputs = _inputs(
        images=[_image(url, flagged=True)],
        text=[_text_match()],
    )

    assert select_images_for_vision_review(inputs, cap=5) == [url]


def test_flagged_image_with_verified_video_still_returned() -> None:
    url = "https://cdn.example/f.jpg"
    inputs = _inputs(
        images=[_image(url, flagged=True)],
        videos=[_video_verified()],
    )

    assert select_images_for_vision_review(inputs, cap=5) == [url]


def test_cap_truncates_preserving_input_order() -> None:
    urls = [f"https://cdn.example/{i}.jpg" for i in range(5)]
    inputs = _inputs(images=[_image(u, flagged=True) for u in urls])

    assert select_images_for_vision_review(inputs, cap=2) == urls[:2]


def test_cap_zero_returns_empty() -> None:
    inputs = _inputs(
        images=[_image("https://cdn.example/x.jpg", flagged=True)]
    )

    assert select_images_for_vision_review(inputs, cap=0) == []


def test_mixed_flagged_and_unflagged_returns_only_flagged_in_order() -> None:
    flagged_url = "https://cdn.example/flagged.jpg"
    inputs = _inputs(
        images=[
            _image("https://cdn.example/clean.jpg", flagged=False, max_likelihood=0.1),
            _image(flagged_url, flagged=True),
            _image(
                "https://cdn.example/below.jpg",
                flagged=False,
                max_likelihood=FLAG_THRESHOLD - 0.001,
            ),
        ]
    )

    assert select_images_for_vision_review(inputs, cap=5) == [flagged_url]
