"""Behavior contracts for derive_preview_description (TASK-1485.02).

Pure-function rule: deterministic, no I/O, no clock, no random. Same
SidebarPayload + DerivationContext always yields the same string.
"""
from __future__ import annotations

from datetime import UTC, datetime

from src.analyses.claims._claims_schemas import ClaimsReport, DedupedClaim
from src.analyses.opinions._schemas import OpinionsReport, SentimentStatsReport
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    SafetyLevel,
    SafetyRecommendation,
)
from src.analyses.schemas import (
    FactsClaimsSection,
    HeadlineSummary,
    OpinionsSection,
    PageKind,
    SafetySection,
    SidebarPayload,
    ToneDynamicsSection,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch, RiskLevel
from src.analyses.tone._scd_schemas import SCDReport
from src.jobs.preview_description import (
    PREVIEW_MAX_LEN,
    DerivationContext,
    derive_preview_description,
)


def _empty_payload() -> SidebarPayload:
    return SidebarPayload(
        source_url="https://example.com/post",
        page_title=None,
        page_kind=PageKind.OTHER,
        scraped_at=datetime.now(UTC),
        cached=False,
        safety=SafetySection(harmful_content_matches=[], recommendation=None),
        tone_dynamics=ToneDynamicsSection(
            scd=SCDReport(summary="", insufficient_conversation=True),
            flashpoint_matches=[],
        ),
        facts_claims=FactsClaimsSection(
            claims_report=ClaimsReport(
                deduped_claims=[],
                total_claims=0,
                total_unique=0,
            ),
            known_misinformation=[],
        ),
        opinions_sentiments=OpinionsSection(
            opinions_report=OpinionsReport(
                sentiment_stats=SentimentStatsReport(
                    per_utterance=[],
                    positive_pct=0.0,
                    negative_pct=0.0,
                    neutral_pct=0.0,
                    mean_valence=0.0,
                ),
                subjective_claims=[],
            )
        ),
    )


def _empty_ctx() -> DerivationContext:
    return DerivationContext(page_title=None, first_utterance_text=None)


class TestHeadlineSummaryBranch:
    """Priority 1: headline synthesis wins over downstream findings."""

    def test_headline_summary_text_is_used_first(self) -> None:
        payload = _empty_payload()
        payload.headline = HeadlineSummary(
            text="Readers are debating whether the proposal solves the actual problem.",
            kind="synthesized",
        )
        payload.safety.recommendation = SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Multiple high-confidence hate-speech utterances",
            top_signals=["hate", "harassment"],
        )

        out = derive_preview_description(payload, _empty_ctx())

        assert out == "Readers are debating whether the proposal solves the actual problem."

    def test_blank_headline_summary_falls_through_to_safety(self) -> None:
        payload = _empty_payload()
        payload.headline = HeadlineSummary(text="   ", kind="synthesized")
        payload.safety.recommendation = SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Multiple high-confidence hate-speech utterances",
            top_signals=["hate", "harassment"],
        )

        out = derive_preview_description(payload, _empty_ctx())

        assert "Caution" in out
        assert "hate-speech" in out


class TestSafetyRecommendationBranch:
    """Priority 2: SafetyRecommendation rationale wins over later branches."""

    def test_caution_recommendation_renders_level_and_rationale(self) -> None:
        payload = _empty_payload()
        payload.safety.recommendation = SafetyRecommendation(
            level=SafetyLevel.CAUTION,
            rationale="Multiple high-confidence hate-speech utterances",
            top_signals=["hate", "harassment"],
        )
        out = derive_preview_description(payload, _empty_ctx())
        assert "Caution" in out or "caution" in out
        assert "hate-speech" in out

    def test_safety_recommendation_outranks_harmful_match(self) -> None:
        """When both signals exist, SafetyRecommendation wins (parent priority)."""
        payload = _empty_payload()
        payload.safety.recommendation = SafetyRecommendation(
            level=SafetyLevel.UNSAFE,
            rationale="Page contains malware-distribution content",
            top_signals=[],
        )
        payload.safety.harmful_content_matches = [
            HarmfulContentMatch(
                utterance_id="u1",
                utterance_text="something else",
                max_score=0.9,
                categories={"hate": True},
                scores={"hate": 0.9},
                flagged_categories=["hate"],
            )
        ]
        out = derive_preview_description(payload, _empty_ctx())
        assert "malware" in out


class TestHarmfulContentBranch:
    """Priority 2: top harmful_content_match by max_score DESC."""

    def test_renders_top_flagged_category_and_score(self) -> None:
        payload = _empty_payload()
        payload.safety.harmful_content_matches = [
            HarmfulContentMatch(
                utterance_id="u1",
                utterance_text="bad",
                max_score=0.55,
                categories={"violence": True},
                scores={"violence": 0.55},
                flagged_categories=["violence"],
            ),
            HarmfulContentMatch(
                utterance_id="u2",
                utterance_text="worse",
                max_score=0.92,
                categories={"hate": True},
                scores={"hate": 0.92},
                flagged_categories=["hate"],
            ),
        ]
        out = derive_preview_description(payload, _empty_ctx())
        assert "hate" in out


class TestFlashpointBranch:
    """Priority 3: top FlashpointMatch by derailment_score DESC."""

    def test_renders_top_flashpoint_risk_level(self) -> None:
        payload = _empty_payload()
        payload.tone_dynamics.flashpoint_matches = [
            FlashpointMatch(
                utterance_id="u1",
                derailment_score=40,
                risk_level=RiskLevel.GUARDED,
                reasoning="mild",
                context_messages=2,
            ),
            FlashpointMatch(
                utterance_id="u2",
                derailment_score=85,
                risk_level=RiskLevel.HOSTILE,
                reasoning="hostile rant",
                context_messages=2,
            ),
        ]
        out = derive_preview_description(payload, _empty_ctx())
        assert "Hostile" in out or "hostile" in out


class TestClaimsBranch:
    """Priority 4: top DedupedClaim by (occurrence_count DESC, author_count DESC)."""

    def test_renders_top_claim_canonical_text(self) -> None:
        payload = _empty_payload()
        payload.facts_claims.claims_report = ClaimsReport(
            deduped_claims=[
                DedupedClaim(
                    canonical_text="Vaccines cause autism",
                    occurrence_count=5,
                    author_count=3,
                    utterance_ids=["u1", "u2"],
                    representative_authors=["a"],
                ),
                DedupedClaim(
                    canonical_text="The earth is flat",
                    occurrence_count=2,
                    author_count=2,
                    utterance_ids=["u3"],
                    representative_authors=["b"],
                ),
            ],
            total_claims=7,
            total_unique=2,
        )
        out = derive_preview_description(payload, _empty_ctx())
        assert "Vaccines cause autism" in out

    def test_ties_broken_by_author_count(self) -> None:
        payload = _empty_payload()
        payload.facts_claims.claims_report = ClaimsReport(
            deduped_claims=[
                DedupedClaim(
                    canonical_text="Same occurrence A",
                    occurrence_count=3,
                    author_count=1,
                    utterance_ids=["u1"],
                    representative_authors=["a"],
                ),
                DedupedClaim(
                    canonical_text="Same occurrence B",
                    occurrence_count=3,
                    author_count=2,
                    utterance_ids=["u2"],
                    representative_authors=["b"],
                ),
            ],
            total_claims=6,
            total_unique=2,
        )
        out = derive_preview_description(payload, _empty_ctx())
        assert "Same occurrence B" in out


class TestSentimentBranch:
    """Priority 5: dominant sentiment (largest pct)."""

    def test_renders_dominant_sentiment_label(self) -> None:
        payload = _empty_payload()
        payload.opinions_sentiments.opinions_report = OpinionsReport(
            sentiment_stats=SentimentStatsReport(
                per_utterance=[],
                positive_pct=70.0,
                negative_pct=20.0,
                neutral_pct=10.0,
                mean_valence=0.4,
            ),
            subjective_claims=[],
        )
        out = derive_preview_description(payload, _empty_ctx())
        assert "positive" in out


class TestFallbackBranches:
    """Priorities 6-7: page_title, first utterance, last-resort."""

    def test_falls_back_to_page_title(self) -> None:
        payload = _empty_payload()
        ctx = DerivationContext(
            page_title="My fascinating blog post",
            first_utterance_text=None,
        )
        out = derive_preview_description(payload, ctx)
        assert "My fascinating blog post" in out

    def test_falls_back_to_first_utterance_when_no_page_title(self) -> None:
        payload = _empty_payload()
        ctx = DerivationContext(
            page_title=None,
            first_utterance_text="The first thing I want to say is hello",
        )
        out = derive_preview_description(payload, ctx)
        assert "The first thing I want to say is hello" in out

    def test_returns_nonempty_when_no_signals(self) -> None:
        payload = _empty_payload()
        out = derive_preview_description(payload, _empty_ctx())
        assert out != ""
        assert len(out) <= PREVIEW_MAX_LEN


class TestTruncation:
    """Hard 140-char cap with ellipsis."""

    def test_long_input_truncated_to_140_with_ellipsis(self) -> None:
        payload = _empty_payload()
        ctx = DerivationContext(page_title="x" * 200, first_utterance_text=None)
        out = derive_preview_description(payload, ctx)
        assert len(out) == PREVIEW_MAX_LEN
        assert out.endswith("…")

    def test_short_input_not_truncated(self) -> None:
        payload = _empty_payload()
        ctx = DerivationContext(page_title="short title", first_utterance_text=None)
        out = derive_preview_description(payload, ctx)
        assert not out.endswith("…")
        assert "short title" in out


class TestDeterminism:
    def test_same_input_yields_same_output(self) -> None:
        payload = _empty_payload()
        payload.opinions_sentiments.opinions_report = OpinionsReport(
            sentiment_stats=SentimentStatsReport(
                per_utterance=[],
                positive_pct=60.0,
                negative_pct=20.0,
                neutral_pct=20.0,
                mean_valence=0.3,
            ),
            subjective_claims=[],
        )
        ctx = DerivationContext(page_title="t", first_utterance_text="u")
        assert derive_preview_description(payload, ctx) == derive_preview_description(
            payload, ctx
        )
