"""Tests for url_content_scan evidence enrichment.

Covers TASK-1657.04 TDD requirements:
- gather_evidence (build_supporting_facts_by_claim) capped by EVIDENCE_MAX_EXTERNAL_CLAIMS
- External-only requirement: evidence MUST come from external URLs (no self-referential)
- Source-post-body NOT flooded into supporting_facts
- proportional_shrink helper
"""

from __future__ import annotations

from typing import Any

import pytest

from src.url_content_scan.claims_schemas import (
    ClaimCategory,
    DedupedClaim,
    SourceKind,
)


def _make_settings(
    *,
    evidence_max_external_claims: int = 10,
    evidence_synthesis_candidate_cap: int = 60,
    evidence_grounded_fetch_groups_per_call: int = 1,
    premises_max_claims_per_batch: int = 30,
    default_mini_model: str = "google-vertex:gemini-flash",
    default_full_model: str = "google-vertex:gemini-pro",
) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        EVIDENCE_MAX_EXTERNAL_CLAIMS=evidence_max_external_claims,
        EVIDENCE_SYNTHESIS_CANDIDATE_CAP=evidence_synthesis_candidate_cap,
        EVIDENCE_GROUNDED_FETCH_GROUPS_PER_CALL=evidence_grounded_fetch_groups_per_call,
        PREMISES_MAX_CLAIMS_PER_BATCH=premises_max_claims_per_batch,
        DEFAULT_MINI_MODEL=default_mini_model,
        DEFAULT_FULL_MODEL=default_full_model,
    )


def _make_deduped_claim(
    canonical_text: str,
    category: ClaimCategory = ClaimCategory.POTENTIALLY_FACTUAL,
    utterance_ids: list[str] | None = None,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=canonical_text,
        category=category,
        occurrence_count=1,
        author_count=1,
        utterance_ids=utterance_ids or ["utt-1"],
        representative_authors=["alice"],
    )


def _external_fact(
    statement: str, source_ref: str = "https://example.com/source"
) -> dict[str, Any]:
    return {
        "statement": statement,
        "source_kind": "external",
        "source_ref": source_ref,
    }


class TestBuildSupportingFactsByClaim:
    @pytest.mark.asyncio
    async def test_returns_empty_for_no_claims(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        result = await build_supporting_facts_by_claim([], _make_settings())
        assert result == {}

    @pytest.mark.asyncio
    async def test_skips_non_factual_claims(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claims = [
            _make_deduped_claim("I predict it will rain.", ClaimCategory.PREDICTIONS),
            _make_deduped_claim("I love sunshine.", ClaimCategory.SUBJECTIVE),
            _make_deduped_claim("I run daily.", ClaimCategory.SELF_CLAIMS),
        ]
        called = []

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            called.extend(texts)
            return {}

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=fake_fetcher
        )
        assert called == []
        assert result == {}

    @pytest.mark.asyncio
    async def test_evidence_capped_at_max_external_claims(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        max_claims = 3
        settings = _make_settings(evidence_max_external_claims=max_claims)
        claims = [
            _make_deduped_claim(f"Factual claim {i}.", ClaimCategory.POTENTIALLY_FACTUAL)
            for i in range(6)
        ]

        fetched_texts: list[str] = []

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            fetched_texts.extend(texts)
            return {text: [_external_fact(f"fact for {text}")] for text in texts}

        await build_supporting_facts_by_claim(claims, settings, external_fetcher=fake_fetcher)

        assert len(fetched_texts) == max_claims

    @pytest.mark.asyncio
    async def test_external_only_evidence_accepted(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claims = [_make_deduped_claim("The economy grew 3% last year.")]

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {
                "The economy grew 3% last year.": [
                    _external_fact(
                        "GDP increased by 3.1% according to the Bureau of Economic Analysis."
                    )
                ]
            }

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=fake_fetcher
        )

        assert "The economy grew 3% last year." in result
        facts = result["The economy grew 3% last year."]
        assert len(facts) == 1
        assert facts[0].source_kind == SourceKind.EXTERNAL

    @pytest.mark.asyncio
    async def test_non_external_source_kind_dropped(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claims = [_make_deduped_claim("Vaccines cause autism.")]

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {
                "Vaccines cause autism.": [
                    {
                        "statement": "Some user said so.",
                        "source_kind": "utterance",
                        "source_ref": "utt-1",
                    }
                ]
            }

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=fake_fetcher
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_tautological_statement_dropped(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claim_text = "The stock market rose sharply yesterday."
        claims = [_make_deduped_claim(claim_text)]

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {
                claim_text: [
                    {
                        "statement": claim_text,
                        "source_kind": "external",
                        "source_ref": "https://example.com",
                    }
                ]
            }

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=fake_fetcher
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_source_body_not_self_referential_as_supporting_facts(self) -> None:
        """The claim text itself must not appear verbatim as a supporting fact statement."""
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claim_text = "Climate change is accelerating rapidly."
        claims = [_make_deduped_claim(claim_text)]

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {
                claim_text: [
                    {
                        "statement": claim_text,
                        "source_kind": "external",
                        "source_ref": "https://example.com",
                    }
                ]
            }

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=fake_fetcher
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_fetcher_exception_returns_empty_without_crash(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claims = [_make_deduped_claim("The moon is made of cheese.")]

        async def failing_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            raise RuntimeError("network error")

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=failing_fetcher
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_deduplicates_identical_supporting_facts(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import build_supporting_facts_by_claim

        claims = [_make_deduped_claim("Inflation is rising.")]

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {
                "Inflation is rising.": [
                    _external_fact("CPI rose 4.2% year-over-year.", "https://bls.gov/cpi"),
                    _external_fact("CPI rose 4.2% year-over-year.", "https://bls.gov/cpi"),
                ]
            }

        result = await build_supporting_facts_by_claim(
            claims, _make_settings(), external_fetcher=fake_fetcher
        )

        assert "Inflation is rising." in result
        assert len(result["Inflation is rising."]) == 1


class TestProportionalShrink:
    def test_empty_counts(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import proportional_shrink

        assert proportional_shrink([], 10) == []

    def test_zero_cap_returns_all_zeros(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import proportional_shrink

        assert proportional_shrink([3, 2, 5], 0) == [0, 0, 0]

    def test_total_within_cap_unchanged(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import proportional_shrink

        assert proportional_shrink([2, 3, 1], 10) == [2, 3, 1]

    def test_shrinks_proportionally(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import proportional_shrink

        result = proportional_shrink([6, 6, 6], 9)
        assert sum(result) == 9
        assert all(r <= 6 for r in result)

    def test_preserves_nonzero_entries(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import proportional_shrink

        result = proportional_shrink([1, 1, 1], 3)
        assert result == [1, 1, 1]

    def test_cap_smaller_than_nonzero_count(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import proportional_shrink

        result = proportional_shrink([5, 5, 5], 2)
        assert sum(result) == 2
        assert result.count(1) == 2
        assert result.count(0) == 1


class TestIsTautologyHelpers:
    def test_identical_statement_is_tautology(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import _is_inline_tautology

        claim = "The stock market crashed."
        assert _is_inline_tautology(claim, claim) is True

    def test_statement_with_padding_words_is_tautology(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import _is_inline_tautology

        claim = "The stock market crashed."
        assert _is_inline_tautology(f"The claim that {claim}", claim) is True

    def test_different_statement_is_not_tautology(self) -> None:
        from src.url_content_scan.analyses.claims.evidence import _is_inline_tautology

        assert (
            _is_inline_tautology(
                "GDP fell 2% in Q3 according to official data.", "Economic growth slowed."
            )
            is False
        )


class TestEvidenceSlot:
    @pytest.mark.asyncio
    async def test_run_claims_evidence_empty_report(self) -> None:
        from src.url_content_scan.analyses.claims.evidence_slot import run_claims_evidence

        result = await run_claims_evidence(None, _make_settings())
        assert "claims_report" in result
        assert result["claims_report"]["deduped_claims"] == []

    @pytest.mark.asyncio
    async def test_run_claims_evidence_attaches_facts(self) -> None:
        from src.url_content_scan.analyses.claims.evidence_slot import run_claims_evidence
        from src.url_content_scan.claims_schemas import ClaimsReport

        report = ClaimsReport(
            deduped_claims=[
                _make_deduped_claim("Sea levels are rising.", ClaimCategory.POTENTIALLY_FACTUAL)
            ],
            total_claims=1,
            total_unique=1,
        )

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {
                "Sea levels are rising.": [
                    _external_fact("NOAA data shows sea level rise of 3.6mm/year.")
                ]
            }

        result = await run_claims_evidence(
            {"claims_report": report.model_dump(mode="json")},
            _make_settings(),
            external_fetcher=fake_fetcher,
        )

        claims = result["claims_report"]["deduped_claims"]
        assert len(claims) == 1
        assert len(claims[0]["supporting_facts"]) == 1

    @pytest.mark.asyncio
    async def test_run_claims_evidence_sets_facts_to_verify_when_no_evidence(self) -> None:
        from src.url_content_scan.analyses.claims.evidence_slot import run_claims_evidence
        from src.url_content_scan.claims_schemas import ClaimsReport

        report = ClaimsReport(
            deduped_claims=[
                DedupedClaim(
                    canonical_text="Moon landing was faked.",
                    category=ClaimCategory.POTENTIALLY_FACTUAL,
                    occurrence_count=3,
                    author_count=2,
                    utterance_ids=["utt-1", "utt-2", "utt-3"],
                    representative_authors=["alice", "bob"],
                )
            ],
            total_claims=3,
            total_unique=1,
        )

        async def fake_fetcher(texts: list[str], settings: Any) -> dict[str, list[dict]]:
            return {}

        result = await run_claims_evidence(
            {"claims_report": report.model_dump(mode="json")},
            _make_settings(),
            external_fetcher=fake_fetcher,
        )

        claims = result["claims_report"]["deduped_claims"]
        assert claims[0]["facts_to_verify"] == 3
        assert claims[0]["supporting_facts"] == []


class TestPremisesSlot:
    @pytest.mark.asyncio
    async def test_run_claims_premises_empty_report(self) -> None:
        from src.url_content_scan.analyses.claims.premises_slot import run_claims_premises

        result = await run_claims_premises(None, _make_settings())
        assert "claims_report" in result
        assert result["claims_report"]["deduped_claims"] == []

    @pytest.mark.asyncio
    async def test_run_claims_premises_attaches_premise_ids(self) -> None:
        from src.url_content_scan.analyses.claims.premises_slot import run_claims_premises
        from src.url_content_scan.claims_schemas import ClaimsReport

        report = ClaimsReport(
            deduped_claims=[
                _make_deduped_claim("We should ban single-use plastics.", ClaimCategory.SUBJECTIVE)
            ],
            total_claims=1,
            total_unique=1,
        )

        async def fake_extractor(texts: list[str], settings: Any) -> dict[str, list[str]]:
            return {
                "We should ban single-use plastics.": ["Plastic is harmful", "Alternatives exist"]
            }

        result = await run_claims_premises(
            {"claims_report": report.model_dump(mode="json")},
            _make_settings(),
            premise_extractor=fake_extractor,
        )

        claims = result["claims_report"]["deduped_claims"]
        assert len(claims) == 1
        assert len(claims[0]["premise_ids"]) == 2

        premises = result["claims_report"].get("premises")
        assert premises is not None
        assert len(premises["premises"]) == 2
