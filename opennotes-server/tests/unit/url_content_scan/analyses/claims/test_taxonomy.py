"""Tests for the 5-way ClaimCategory taxonomy and downstream plumbing.

Ports vibecheck-server PR484: ClaimCategory expands from 3-way to 5-way
(potentially_factual / self_claims / predictions / subjective / other).

Validates:
- ClaimCategory has exactly 5 values with correct string keys
- ExtractedClaim carries category (defaults to POTENTIALLY_FACTUAL)
- DedupedClaim carries category propagated from canonical claim
- run_claims_dedup propagates the canonical claim's category to DedupedClaim
"""

from __future__ import annotations

import pytest

from src.url_content_scan.claims_schemas import (
    ClaimCategory,
    DedupedClaim,
    ExtractedClaim,
)
from src.url_content_scan.utterances.schema import Utterance


class TestClaimCategoryEnum:
    def test_has_exactly_five_values(self) -> None:
        values = list(ClaimCategory)
        assert len(values) == 5

    def test_has_potentially_factual(self) -> None:
        assert ClaimCategory.POTENTIALLY_FACTUAL == "potentially_factual"

    def test_has_self_claims(self) -> None:
        assert ClaimCategory.SELF_CLAIMS == "self_claims"

    def test_has_predictions(self) -> None:
        assert ClaimCategory.PREDICTIONS == "predictions"

    def test_has_subjective(self) -> None:
        assert ClaimCategory.SUBJECTIVE == "subjective"

    def test_has_other(self) -> None:
        assert ClaimCategory.OTHER == "other"

    def test_default_category_in_extracted_claim(self) -> None:
        claim = ExtractedClaim(claim_text="The budget increased.", confidence=0.9)
        assert claim.category is ClaimCategory.POTENTIALLY_FACTUAL

    def test_extracted_claim_accepts_subjective(self) -> None:
        claim = ExtractedClaim(
            claim_text="I prefer this approach.",
            category=ClaimCategory.SUBJECTIVE,
            confidence=0.8,
        )
        assert claim.category is ClaimCategory.SUBJECTIVE

    def test_extracted_claim_accepts_predictions(self) -> None:
        claim = ExtractedClaim(
            claim_text="Inflation will fall next quarter.",
            category=ClaimCategory.PREDICTIONS,
            confidence=0.7,
        )
        assert claim.category is ClaimCategory.PREDICTIONS

    def test_extracted_claim_accepts_self_claims(self) -> None:
        claim = ExtractedClaim(
            claim_text="I lost 10 kg last year.",
            category=ClaimCategory.SELF_CLAIMS,
            confidence=0.6,
        )
        assert claim.category is ClaimCategory.SELF_CLAIMS

    def test_extracted_claim_accepts_other(self) -> None:
        claim = ExtractedClaim(
            claim_text="What time is it?",
            category=ClaimCategory.OTHER,
            confidence=0.5,
        )
        assert claim.category is ClaimCategory.OTHER

    def test_deduped_claim_defaults_category(self) -> None:
        claim = DedupedClaim(
            canonical_text="The city approved the tax increase.",
            occurrence_count=2,
            author_count=1,
            utterance_ids=["u-1", "u-2"],
            representative_authors=["alice"],
        )
        assert claim.category is ClaimCategory.POTENTIALLY_FACTUAL

    def test_deduped_claim_accepts_subjective(self) -> None:
        claim = DedupedClaim(
            canonical_text="This policy is a disaster.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=3,
            author_count=2,
            utterance_ids=["u-1", "u-2", "u-3"],
            representative_authors=["alice", "bob"],
        )
        assert claim.category is ClaimCategory.SUBJECTIVE


class TestClaimCategoryPropagation:
    @pytest.mark.asyncio
    async def test_dedup_propagates_canonical_claim_category(self) -> None:
        from src.url_content_scan.analyses.claims.dedup import run_claims_dedup

        utterances = [
            Utterance(
                utterance_id="u-1", kind="comment", text="I think I lost 5 kg.", author="alice"
            ),
            Utterance(utterance_id="u-2", kind="comment", text="I lost about 5 kg.", author="bob"),
        ]

        async def fake_extract(utterance: Utterance) -> list[ExtractedClaim]:
            return [
                ExtractedClaim(
                    claim_text=utterance.text,
                    category=ClaimCategory.SELF_CLAIMS,
                    confidence=0.8,
                )
            ]

        async def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

        report = await run_claims_dedup(
            utterances,
            extract_claims=fake_extract,
            embed_texts=fake_embed,
        )

        assert report.total_unique == 1
        assert report.deduped_claims[0].category is ClaimCategory.SELF_CLAIMS

    @pytest.mark.asyncio
    async def test_dedup_highest_confidence_claim_wins_category(self) -> None:
        from src.url_content_scan.analyses.claims.dedup import run_claims_dedup

        utterances = [
            Utterance(
                utterance_id="u-1", kind="comment", text="inflation will rise", author="alice"
            ),
            Utterance(
                utterance_id="u-2",
                kind="comment",
                text="inflation will rise next year",
                author="bob",
            ),
        ]

        async def fake_extract(utterance: Utterance) -> list[ExtractedClaim]:
            if utterance.utterance_id == "u-1":
                return [
                    ExtractedClaim(
                        claim_text=utterance.text, category=ClaimCategory.SUBJECTIVE, confidence=0.5
                    )
                ]
            return [
                ExtractedClaim(
                    claim_text=utterance.text, category=ClaimCategory.PREDICTIONS, confidence=0.95
                )
            ]

        async def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

        report = await run_claims_dedup(
            utterances,
            extract_claims=fake_extract,
            embed_texts=fake_embed,
        )

        assert report.total_unique == 1
        assert report.deduped_claims[0].category is ClaimCategory.PREDICTIONS

    @pytest.mark.asyncio
    async def test_extract_uses_shared_extracted_claim_type(self) -> None:
        from src.url_content_scan.analyses.claims.extract import (
            ExtractedClaim as ExtractExtractedClaim,
        )
        from src.url_content_scan.claims_schemas import ExtractedClaim as SchemaExtractedClaim

        assert ExtractExtractedClaim is SchemaExtractedClaim
