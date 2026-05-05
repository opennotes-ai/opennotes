from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.bulk_content_scan.openai_moderation_service import ModerationResult
from src.url_content_scan.models import UrlScanWebRiskLookup
from src.url_content_scan.safety_schemas import SafetyLevel, SafetyRecommendation
from src.url_content_scan.utterances.schema import Utterance

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@dataclass(frozen=True)
class _SafeSearchResult:
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float


class _FakeSession:
    def __init__(self, rows: dict[str, UrlScanWebRiskLookup] | None = None) -> None:
        self.rows = rows or {}
        self.commits = 0
        self.rollbacks = 0

    async def get(self, model: type[UrlScanWebRiskLookup], key: str) -> UrlScanWebRiskLookup | None:
        assert model is UrlScanWebRiskLookup
        return self.rows.get(key)

    async def merge(self, row: UrlScanWebRiskLookup) -> UrlScanWebRiskLookup:
        self.rows[row.normalized_url] = row
        return row

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _mock_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.utils.url_security._resolve",
        lambda hostname: ["93.184.216.34"],
    )


def _utterance(
    utterance_id: str,
    text: str,
    *,
    mentioned_urls: list[str] | None = None,
    mentioned_images: list[str] | None = None,
    mentioned_videos: list[str] | None = None,
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind="comment",
        text=text,
        mentioned_urls=mentioned_urls or [],
        mentioned_images=mentioned_images or [],
        mentioned_videos=mentioned_videos or [],
    )


async def test_run_safety_moderation_returns_empty_section_for_empty_input() -> None:
    from src.url_content_scan.analyses.safety import run_safety_moderation

    section = await run_safety_moderation([], moderation_service=AsyncMock())

    assert section.harmful_content_matches == []
    assert section.recommendation is None


async def test_run_safety_moderation_maps_flagged_openai_results() -> None:
    from src.url_content_scan.analyses.safety import run_safety_moderation

    moderation_service = AsyncMock()
    moderation_service.moderate_texts.return_value = [
        ModerationResult(
            flagged=True,
            categories={"violence": True},
            scores={"violence": 0.92},
            max_score=0.92,
            flagged_categories=["violence"],
        ),
        ModerationResult(
            flagged=False,
            categories={"violence": False},
            scores={"violence": 0.03},
            max_score=0.03,
            flagged_categories=[],
        ),
    ]

    section = await run_safety_moderation(
        [_utterance("u-1", "violent text"), _utterance("u-2", "harmless text")],
        moderation_service=moderation_service,
    )

    moderation_service.moderate_texts.assert_awaited_once_with(["violent text", "harmless text"])
    assert [match.utterance_id for match in section.harmful_content_matches] == ["u-1"]
    assert section.harmful_content_matches[0].utterance_text == "violent text"
    assert section.harmful_content_matches[0].source == "openai"


async def test_run_pre_enqueue_web_risk_caches_clean_lookup() -> None:
    from src.url_content_scan.analyses.safety import run_pre_enqueue_web_risk

    session = _FakeSession()
    client = AsyncMock()
    client.check_url.return_value = None
    lookup_cache: dict[str, object | None] = {}

    finding = await run_pre_enqueue_web_risk(
        "https://example.com/path?utm_source=test",
        session=session,
        web_risk_client=client,
        lookup_cache=lookup_cache,
    )

    assert finding is None
    assert client.check_url.await_count == 1
    assert session.commits == 1
    assert list(session.rows) == ["https://example.com/path"]
    assert session.rows["https://example.com/path"].findings == {
        "url": "https://example.com/path",
        "threat_types": [],
    }
    assert lookup_cache["https://example.com/path"] is None


async def test_run_web_risk_dedupes_urls_and_reuses_preenqueue_cache() -> None:
    from src.url_content_scan.analyses.safety import run_pre_enqueue_web_risk, run_web_risk
    from src.url_content_scan.safety_schemas import WebRiskFinding

    session = _FakeSession()
    lookup_cache: dict[str, object | None] = {}
    client = AsyncMock()
    client.check_url.side_effect = [
        WebRiskFinding(url="https://example.com/page", threat_types=["SOCIAL_ENGINEERING"]),
        WebRiskFinding(url="https://example.com/bad", threat_types=["MALWARE"]),
    ]

    pre_enqueue = await run_pre_enqueue_web_risk(
        "https://example.com/page",
        session=session,
        web_risk_client=client,
        lookup_cache=lookup_cache,
    )
    section = await run_web_risk(
        page_url="https://example.com/page",
        mentioned_urls=[
            "https://example.com/page",
            "https://example.com/bad",
            "https://example.com/bad?utm_campaign=x",
        ],
        media_urls=["https://example.com/page"],
        session=session,
        web_risk_client=client,
        lookup_cache=lookup_cache,
    )

    assert pre_enqueue is not None
    assert client.check_url.await_count == 2
    assert [finding.url for finding in section.findings] == [
        "https://example.com/page",
        "https://example.com/bad",
    ]


async def test_run_image_moderation_dedupes_safe_search_by_content_hash() -> None:
    from src.url_content_scan.analyses.safety import MentionedImage, run_image_moderation

    fetch_bytes = AsyncMock(side_effect=[b"same-image", b"same-image"])
    safe_search = AsyncMock(
        return_value=_SafeSearchResult(
            adult=0.0,
            violence=0.81,
            racy=0.0,
            medical=0.0,
            spoof=0.0,
            flagged=True,
            max_likelihood=0.81,
        )
    )

    section = await run_image_moderation(
        [
            MentionedImage("u-1", "https://cdn.example.com/a.png"),
            MentionedImage("u-2", "https://cdn.example.com/b.png"),
        ],
        fetch_bytes=fetch_bytes,
        safe_search=safe_search,
    )

    assert fetch_bytes.await_count == 2
    assert safe_search.await_count == 1
    assert [match.utterance_id for match in section.matches] == ["u-1", "u-2"]
    assert all(match.flagged for match in section.matches)


async def test_run_video_moderation_marks_sampling_failures_as_flagged() -> None:
    from src.url_content_scan.analyses.safety import (
        MentionedVideo,
        VideoSamplingError,
        run_video_moderation,
    )

    sample_video = AsyncMock(side_effect=VideoSamplingError("ffmpeg missing"))
    safe_search = AsyncMock()

    section = await run_video_moderation(
        [MentionedVideo("u-1", "https://videos.example.com/clip.mp4")],
        sample_video=sample_video,
        safe_search=safe_search,
    )

    assert safe_search.await_count == 0
    assert section.matches[0].utterance_id == "u-1"
    assert section.matches[0].flagged is True
    assert section.matches[0].max_likelihood == 1.0
    assert section.matches[0].frame_findings == []


async def test_run_video_moderation_samples_frames_and_aggregates_flags() -> None:
    from src.url_content_scan.analyses.safety import (
        FrameBytes,
        MentionedVideo,
        run_video_moderation,
    )

    sample_video = AsyncMock(
        return_value=[
            FrameBytes(frame_offset_ms=0, png_bytes=b"frame-a"),
            FrameBytes(frame_offset_ms=1250, png_bytes=b"frame-b"),
        ]
    )
    safe_search = AsyncMock(
        side_effect=[
            _SafeSearchResult(
                adult=0.0,
                violence=0.1,
                racy=0.0,
                medical=0.0,
                spoof=0.0,
                flagged=False,
                max_likelihood=0.1,
            ),
            _SafeSearchResult(
                adult=0.0,
                violence=0.0,
                racy=0.77,
                medical=0.0,
                spoof=0.0,
                flagged=True,
                max_likelihood=0.77,
            ),
        ]
    )

    section = await run_video_moderation(
        [MentionedVideo("u-1", "https://videos.example.com/clip.mp4")],
        sample_video=sample_video,
        safe_search=safe_search,
    )

    assert safe_search.await_count == 2
    assert section.matches[0].flagged is True
    assert section.matches[0].max_likelihood == 0.77
    assert [frame.frame_offset_ms for frame in section.matches[0].frame_findings] == [0, 1250]


async def test_run_safety_recommendation_uses_injected_agent_runner() -> None:
    from src.url_content_scan.analyses.safety import (
        SafetyRecommendationInputs,
        run_safety_recommendation,
    )

    captured: dict[str, object] = {}

    async def agent_runner(inputs: SafetyRecommendationInputs) -> SafetyRecommendation:
        captured["inputs"] = inputs
        return SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="One isolated web-risk hit.",
            top_signals=["SOCIAL_ENGINEERING on https://example.com/page"],
            unavailable_inputs=["video_moderation"],
        )

    result = await run_safety_recommendation(
        SafetyRecommendationInputs(
            harmful_content_matches=[],
            web_risk_findings=[],
            image_moderation_matches=[],
            video_moderation_matches=[],
            unavailable_inputs=["video_moderation"],
        ),
        agent_runner=agent_runner,
    )

    assert captured["inputs"] is not None
    assert result.level is SafetyLevel.CAUTION
    assert result.unavailable_inputs == ["video_moderation"]
