"""Tests for the /api/analyze orchestrator."""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.analyses.claims._claims_schemas import Claim, ClaimsReport, DedupedClaim
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import (
    SentimentScore,
    SentimentStatsReport,
    SubjectiveClaim,
)
from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.schemas import SidebarPayload
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone._scd_schemas import SCDReport
from src.cache.supabase_cache import normalize_url
from src.config import get_settings
from src.main import app
from src.routes import analyze as analyze_route
from src.utterances.schema import Utterance, UtterancesPayload

FIXTURE_DIR = Path(__file__).parent / "fixtures"
QUIZLET_URL = "https://quizlet.com/blog/groups-are-now-classes/"
QUIZLET_NORMALIZED = normalize_url(QUIZLET_URL)


def _build_utterances_payload() -> UtterancesPayload:
    return UtterancesPayload(
        source_url=QUIZLET_URL,
        scraped_at=datetime(2024, 9, 1, 12, 0, 0, tzinfo=UTC),
        page_title="Groups are now Classes",
        page_kind="blog_post",
        utterances=[
            Utterance(
                utterance_id="post-0",
                kind="post",
                text="We've renamed Groups to Classes.",
                author="Quizlet Team",
            ),
            Utterance(
                utterance_id="comment-0",
                kind="comment",
                text="Love the rename!",
                author="alice_teacher",
                parent_id="post-0",
            ),
            Utterance(
                utterance_id="comment-1",
                kind="comment",
                text="This breaks our integration.",
                author="bob_dev",
                parent_id="post-0",
            ),
            Utterance(
                utterance_id="reply-0",
                kind="reply",
                text="Existing Groups auto-migrate.",
                author="Quizlet Team",
                parent_id="comment-1",
            ),
        ],
    )


class StubCache:
    """In-memory cache stand-in implementing the SupabaseCache protocol."""

    def __init__(self, preload: dict[str, dict[str, Any]] | None = None) -> None:
        self.store: dict[str, dict[str, Any]] = dict(preload or {})
        self.get_calls: list[str] = []
        self.put_calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, url: str) -> dict[str, Any] | None:
        self.get_calls.append(url)
        return self.store.get(url)

    async def put(self, url: str, payload: dict[str, Any]) -> None:
        self.put_calls.append((url, payload))
        self.store[url] = payload


@pytest.fixture(autouse=True)
def _reset_rate_limit_state() -> Iterator[None]:
    """Clear slowapi's in-memory storage and the settings cache between tests."""
    analyze_route.limiter.reset()
    get_settings.cache_clear()
    yield
    analyze_route.limiter.reset()
    get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient bound to the real app.

    Lifespan is invoked as a context-manager so `app.state.cache` is set to
    the (supabase-missing -> None) default. Individual tests replace
    `app.state.cache` with a StubCache when needed.
    """
    with TestClient(app) as c:
        app.state.cache = None
        app.state.firecrawl_client = None
        app.state.moderation_service = None
        app.state.flashpoint_service = None
        app.state.httpx_client = None
        yield c
        app.state.cache = None


def _stub_all_analyses(
    monkeypatch: pytest.MonkeyPatch,
    *,
    utterances: UtterancesPayload | None = None,
    moderation_matches: list[HarmfulContentMatch] | None = None,
    flashpoint_matches: list[FlashpointMatch] | None = None,
    extracted_claims_per_utt: list[list[Claim]] | None = None,
    claims_report: ClaimsReport | None = None,
    subjective_per_utt: list[list[SubjectiveClaim]] | None = None,
    sentiment_stats: SentimentStatsReport | None = None,
    scd_report: SCDReport | None = None,
    known_misinformation: list[FactCheckMatch] | None = None,
) -> dict[str, MagicMock]:
    """Patch every analysis entry point with an AsyncMock and return them.

    All defaults produce a valid (empty) SidebarPayload, so each test only
    overrides the fields it exercises.
    """
    utterances = utterances or _build_utterances_payload()
    moderation_matches = moderation_matches or []
    flashpoint_matches = flashpoint_matches or []
    extracted_claims_per_utt = extracted_claims_per_utt or [
        [] for _ in utterances.utterances
    ]
    claims_report = claims_report or ClaimsReport(
        deduped_claims=[], total_claims=0, total_unique=0
    )
    subjective_per_utt = subjective_per_utt or [[] for _ in utterances.utterances]
    sentiment_stats = sentiment_stats or SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=0.0,
        mean_valence=0.0,
    )
    scd_report = scd_report or SCDReport(
        summary="ok",
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=False,
    )
    known_misinformation = known_misinformation or []

    extract_mock = AsyncMock(return_value=utterances)
    monkeypatch.setattr(analyze_route, "extract_utterances", extract_mock)

    # Bulk variants replaced per-utterance loops in the orchestrator; mock those.
    n = len(utterances.utterances)
    moderation_bulk_return = moderation_matches + [None] * (n - len(moderation_matches))
    moderation_mock = AsyncMock(return_value=moderation_bulk_return[:n])
    monkeypatch.setattr(analyze_route, "check_content_moderation_bulk", moderation_mock)

    flashpoint_bulk_return = flashpoint_matches + [None] * (n - len(flashpoint_matches))
    flashpoint_mock = AsyncMock(return_value=flashpoint_bulk_return[:n])
    monkeypatch.setattr(analyze_route, "detect_flashpoints_bulk", flashpoint_mock)

    extract_claims_mock = AsyncMock(
        return_value=extracted_claims_per_utt + [[] for _ in range(max(0, n - len(extracted_claims_per_utt)))]
    )
    monkeypatch.setattr(analyze_route, "extract_claims_bulk", extract_claims_mock)

    dedupe_mock = AsyncMock(return_value=claims_report)
    monkeypatch.setattr(analyze_route, "dedupe_claims", dedupe_mock)

    subjective_mock = AsyncMock(
        return_value=subjective_per_utt + [[] for _ in range(max(0, n - len(subjective_per_utt)))]
    )
    monkeypatch.setattr(analyze_route, "extract_subjective_claims_bulk", subjective_mock)

    sentiment_mock = AsyncMock(return_value=sentiment_stats)
    monkeypatch.setattr(analyze_route, "compute_sentiment_stats", sentiment_mock)

    scd_mock = AsyncMock(return_value=scd_report)
    monkeypatch.setattr(analyze_route, "analyze_scd", scd_mock)

    misinfo_mock = AsyncMock(return_value=known_misinformation)
    monkeypatch.setattr(analyze_route, "check_known_misinformation", misinfo_mock)

    monkeypatch.setattr(
        analyze_route, "_get_firecrawl_client", lambda request, settings: MagicMock()
    )
    monkeypatch.setattr(
        analyze_route,
        "_get_moderation_service",
        lambda request, settings: MagicMock(),
    )
    monkeypatch.setattr(
        analyze_route,
        "_get_flashpoint_service",
        lambda request, settings: MagicMock(),
    )

    return {
        "extract_utterances": extract_mock,
        "moderation_bulk": moderation_mock,
        "flashpoint_bulk": flashpoint_mock,
        "extract_claims_bulk": extract_claims_mock,
        "dedupe": dedupe_mock,
        "subjective_bulk": subjective_mock,
        "sentiment": sentiment_mock,
        "scd": scd_mock,
        "known_misinformation": misinfo_mock,
    }


class TestCacheHitShortCircuits:
    def test_cache_hit_returns_cached_true(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_raw = json.loads((FIXTURE_DIR / "quizlet_full.json").read_text())
        cache = StubCache(preload={QUIZLET_NORMALIZED: cached_raw})
        app.state.cache = cache
        mocks = _stub_all_analyses(monkeypatch)

        resp = client.post("/api/analyze", json={"url": QUIZLET_URL})

        assert resp.status_code == 200
        body = resp.json()
        assert body["cached"] is True
        assert body["source_url"] == QUIZLET_URL
        # Confirm no analysis was invoked.
        assert mocks["extract_utterances"].await_count == 0
        assert mocks["moderation_bulk"].await_count == 0
        assert mocks["scd"].await_count == 0


class TestCacheMissRunsPipeline:
    def test_cache_miss_runs_pipeline_and_stores_payload(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = StubCache()
        app.state.cache = cache
        mocks = _stub_all_analyses(monkeypatch)

        resp = client.post("/api/analyze", json={"url": QUIZLET_URL})

        assert resp.status_code == 200
        body = resp.json()
        assert body["cached"] is False
        assert mocks["extract_utterances"].await_count == 1
        # Bulk analyses: ONE call each across all 4 utterances.
        assert mocks["moderation_bulk"].await_count == 1
        assert mocks["extract_claims_bulk"].await_count == 1
        assert mocks["subjective_bulk"].await_count == 1
        assert mocks["flashpoint_bulk"].await_count == 1
        assert mocks["sentiment"].await_count == 1
        assert mocks["scd"].await_count == 1
        assert len(cache.put_calls) == 1
        stored_url, stored_payload = cache.put_calls[0]
        assert stored_url == QUIZLET_NORMALIZED
        assert stored_payload["cached"] is False


class TestRateLimit:
    def test_429_after_threshold(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_HOUR", "10")
        get_settings.cache_clear()
        analyze_route.limiter.reset()

        cache = StubCache()
        app.state.cache = cache
        _stub_all_analyses(monkeypatch)

        for i in range(10):
            resp = client.post("/api/analyze", json={"url": QUIZLET_URL})
            assert resp.status_code == 200, f"req {i}: {resp.status_code} {resp.text}"

        resp_11 = client.post("/api/analyze", json={"url": QUIZLET_URL})
        assert resp_11.status_code == 429


class TestResilienceToAnalysisFailure:
    def test_individual_analysis_exception_does_not_500(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app.state.cache = None
        _stub_all_analyses(monkeypatch)

        # Make SCD raise to verify its section falls back to an empty report.
        async def boom_scd(utterances, settings):  # type: ignore[no-untyped-def]
            raise RuntimeError("scd agent crashed")

        monkeypatch.setattr(analyze_route, "analyze_scd", boom_scd)

        resp = client.post("/api/analyze", json={"url": QUIZLET_URL})

        assert resp.status_code == 200
        body = resp.json()
        assert body["tone_dynamics"]["scd"]["insufficient_conversation"] is True
        assert body["tone_dynamics"]["scd"]["summary"] == ""
        # Other sections are still populated (empty but structurally valid).
        assert "harmful_content_matches" in body["safety"]
        assert "claims_report" in body["facts_claims"]


class TestEndToEndWithFixture:
    def test_all_four_sections_populated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app.state.cache = None

        payload = _build_utterances_payload()
        moderation_matches = [
            HarmfulContentMatch(
                utterance_id="comment-1",
                max_score=0.71,
                categories={"harassment": True},
                scores={"harassment": 0.71},
                flagged_categories=["harassment"],
            )
        ]
        flashpoint_matches = [
            FlashpointMatch(
                utterance_id="comment-1",
                derailment_score=62,
                risk_level=RiskLevel.HEATED,
                reasoning="API-breakage escalates tone",
                context_messages=2,
            )
        ]
        extracted_claims_per_utt: list[list[Claim]] = [
            [],
            [],
            [],
            [Claim(
                claim_text="Existing Groups auto-migrate to Classes.",
                utterance_id="reply-0",
                confidence=0.9,
            )],
        ]
        deduped_report = ClaimsReport(
            deduped_claims=[
                DedupedClaim(
                    canonical_text="Existing Groups auto-migrate to Classes.",
                    occurrence_count=1,
                    author_count=1,
                    utterance_ids=["reply-0"],
                    representative_authors=["Quizlet Team"],
                )
            ],
            total_claims=1,
            total_unique=1,
        )
        subjective_per_utt: list[list[SubjectiveClaim]] = [
            [],
            [SubjectiveClaim(
                claim_text="Love the rename",
                utterance_id="comment-0",
                stance="supports",
            )],
            [],
            [],
        ]
        sentiment_stats = SentimentStatsReport(
            per_utterance=[
                SentimentScore(utterance_id="post-0", label="positive", valence=0.6),
                SentimentScore(utterance_id="comment-0", label="positive", valence=0.5),
                SentimentScore(utterance_id="comment-1", label="negative", valence=-0.4),
                SentimentScore(utterance_id="reply-0", label="neutral", valence=0.1),
            ],
            positive_pct=50.0,
            negative_pct=25.0,
            neutral_pct=25.0,
            mean_valence=0.2,
        )
        scd_report = SCDReport(
            summary="Constructive thread with a guarded turn.",
            tone_labels=["collaborative", "guarded"],
            per_speaker_notes={"bob_dev": "Raises an API-stability concern."},
            insufficient_conversation=False,
        )
        known_misinfo = [
            FactCheckMatch(
                claim_text="Existing Groups auto-migrate to Classes.",
                publisher="Quizlet Help Center",
                review_title="Migration status for renamed Groups",
                review_url="https://help.quizlet.com/fact-check/groups-classes",
                textual_rating="Accurate",
            )
        ]

        _stub_all_analyses(
            monkeypatch,
            utterances=payload,
            moderation_matches=moderation_matches,
            flashpoint_matches=flashpoint_matches,
            extracted_claims_per_utt=extracted_claims_per_utt,
            claims_report=deduped_report,
            subjective_per_utt=subjective_per_utt,
            sentiment_stats=sentiment_stats,
            scd_report=scd_report,
            known_misinformation=known_misinfo,
        )

        resp = client.post("/api/analyze", json={"url": QUIZLET_URL})

        assert resp.status_code == 200
        sidebar = SidebarPayload.model_validate(resp.json())
        assert sidebar.source_url == QUIZLET_URL
        assert sidebar.page_title == "Groups are now Classes"
        assert sidebar.page_kind == "blog_post"
        assert sidebar.cached is False

        assert len(sidebar.safety.harmful_content_matches) == 1
        assert sidebar.safety.harmful_content_matches[0].utterance_id == "comment-1"

        assert sidebar.tone_dynamics.scd.summary.startswith("Constructive")
        assert len(sidebar.tone_dynamics.flashpoint_matches) == 1

        assert sidebar.facts_claims.claims_report.total_unique == 1
        assert len(sidebar.facts_claims.known_misinformation) == 1

        assert sidebar.opinions_sentiments.opinions_report.sentiment_stats.positive_pct == 50.0
        assert len(sidebar.opinions_sentiments.opinions_report.subjective_claims) == 1


class TestValidationAndErrors:
    def test_missing_url_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/analyze", json={})
        assert resp.status_code == 422

    def test_empty_url_returns_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_all_analyses(monkeypatch)
        resp = client.post("/api/analyze", json={"url": ""})
        assert resp.status_code == 400

    def test_extraction_failure_returns_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app.state.cache = None
        _stub_all_analyses(monkeypatch)

        async def boom(url, client):  # type: ignore[no-untyped-def]
            raise RuntimeError("firecrawl offline")

        monkeypatch.setattr(analyze_route, "extract_utterances", boom)

        resp = client.post("/api/analyze", json={"url": QUIZLET_URL})
        assert resp.status_code == 502
