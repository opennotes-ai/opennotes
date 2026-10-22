"""Tests for url_content_scan premises extraction.

Covers TASK-1657.04 TDD requirements:
- infer_premises_batch capped by PREMISES_MAX_CLAIMS_PER_BATCH
- build_premises_by_claim attaches premise IDs to eligible claims
- Only PREDICTIONS, SUBJECTIVE, SELF_CLAIMS categories get premises
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.url_content_scan.claims_schemas import (
    ClaimCategory,
    DedupedClaim,
)


def _make_settings(
    *,
    premises_max_claims_per_batch: int = 30,
    default_full_model: str = "google-vertex:gemini-2.0-flash",
) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        PREMISES_MAX_CLAIMS_PER_BATCH=premises_max_claims_per_batch,
        DEFAULT_FULL_MODEL=default_full_model,
    )


def _make_deduped_claim(
    canonical_text: str,
    category: ClaimCategory = ClaimCategory.POTENTIALLY_FACTUAL,
    occurrence_count: int = 1,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=canonical_text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=1,
        utterance_ids=["utt-1"],
        representative_authors=["alice"],
    )


class TestBuildPremisesByClaim:
    @pytest.mark.asyncio
    async def test_returns_empty_for_no_claims(self) -> None:
        from src.url_content_scan.analyses.claims.premises import build_premises_by_claim

        registry, by_claim = await build_premises_by_claim([], _make_settings())
        assert registry.premises == {}
        assert by_claim == {}

    @pytest.mark.asyncio
    async def test_skips_non_eligible_categories(self) -> None:
        from src.url_content_scan.analyses.claims.premises import build_premises_by_claim

        claims = [
            _make_deduped_claim("The sky is blue.", ClaimCategory.POTENTIALLY_FACTUAL),
            _make_deduped_claim("No comment.", ClaimCategory.OTHER),
        ]
        called = []

        async def fake_extractor(texts: list[str], settings: Any) -> dict[str, list[str]]:
            called.extend(texts)
            return {}

        registry, by_claim = await build_premises_by_claim(
            claims, _make_settings(), premise_extractor=fake_extractor
        )
        assert called == []
        assert by_claim == {}
        assert registry.premises == {}

    @pytest.mark.asyncio
    async def test_extracts_premises_for_eligible_categories(self) -> None:
        from src.url_content_scan.analyses.claims.premises import build_premises_by_claim

        claims = [
            _make_deduped_claim("Climate policy will fail.", ClaimCategory.PREDICTIONS),
            _make_deduped_claim("I feel safe here.", ClaimCategory.SELF_CLAIMS),
            _make_deduped_claim("This is unfair.", ClaimCategory.SUBJECTIVE),
            _make_deduped_claim("CO2 is rising.", ClaimCategory.POTENTIALLY_FACTUAL),
        ]

        async def fake_extractor(texts: list[str], settings: Any) -> dict[str, list[str]]:
            assert "Climate policy will fail." in texts
            assert "I feel safe here." in texts
            assert "This is unfair." in texts
            assert "CO2 is rising." not in texts
            return {
                "Climate policy will fail.": ["Policy always fails", "Governments are ineffective"],
                "I feel safe here.": ["Safety is subjective"],
                "This is unfair.": [],
            }

        registry, by_claim = await build_premises_by_claim(
            claims, _make_settings(), premise_extractor=fake_extractor
        )

        assert "Climate policy will fail." in by_claim
        assert len(by_claim["Climate policy will fail."]) == 2
        assert "I feel safe here." in by_claim
        assert len(by_claim["I feel safe here."]) == 1
        assert "This is unfair." not in by_claim
        assert "CO2 is rising." not in by_claim
        assert len(registry.premises) == 3

    @pytest.mark.asyncio
    async def test_premises_are_capped_at_batch_size(self) -> None:
        from src.url_content_scan.analyses.claims.premises import build_premises_by_claim

        batch_size = 2
        settings = _make_settings(premises_max_claims_per_batch=batch_size)
        claims = [
            _make_deduped_claim(f"Subjective claim {i}.", ClaimCategory.SUBJECTIVE)
            for i in range(5)
        ]

        call_log: list[list[str]] = []

        async def fake_extractor(texts: list[str], settings: Any) -> dict[str, list[str]]:
            call_log.append(list(texts))
            return {text: ["premise A"] for text in texts}

        _registry, _by_claim = await build_premises_by_claim(
            claims, settings, premise_extractor=fake_extractor
        )

        assert len(call_log) == 3
        assert len(call_log[0]) == 2
        assert len(call_log[1]) == 2
        assert len(call_log[2]) == 1

    @pytest.mark.asyncio
    async def test_registry_deduplicates_identical_premises_across_claims(self) -> None:
        from src.url_content_scan.analyses.claims.premises import build_premises_by_claim

        claims = [
            _make_deduped_claim("Claim A.", ClaimCategory.PREDICTIONS),
            _make_deduped_claim("Claim B.", ClaimCategory.PREDICTIONS),
        ]
        shared_premise = "Shared underlying assumption."

        async def fake_extractor(texts: list[str], settings: Any) -> dict[str, list[str]]:
            return {text: [shared_premise] for text in texts}

        registry, by_claim = await build_premises_by_claim(
            claims, _make_settings(), premise_extractor=fake_extractor
        )

        premise_ids_a = by_claim.get("Claim A.", [])
        premise_ids_b = by_claim.get("Claim B.", [])
        assert len(premise_ids_a) == 1
        assert len(premise_ids_b) == 1
        assert premise_ids_a[0] == premise_ids_b[0]
        assert len(registry.premises) == 1

    @pytest.mark.asyncio
    async def test_batch_failure_skips_chunk_gracefully(self) -> None:
        from src.url_content_scan.analyses.claims.premises import build_premises_by_claim

        settings = _make_settings(premises_max_claims_per_batch=2)
        claims = [
            _make_deduped_claim("Prediction A.", ClaimCategory.PREDICTIONS),
            _make_deduped_claim("Prediction B.", ClaimCategory.PREDICTIONS),
            _make_deduped_claim("Prediction C.", ClaimCategory.PREDICTIONS),
        ]
        fail_on = {"Prediction A.", "Prediction B."}

        async def fake_extractor(texts: list[str], settings: Any) -> dict[str, list[str]]:
            if any(t in fail_on for t in texts):
                raise RuntimeError("mock batch failure")
            return {text: ["premise"] for text in texts}

        _registry, by_claim = await build_premises_by_claim(
            claims, settings, premise_extractor=fake_extractor
        )

        assert "Prediction A." not in by_claim
        assert "Prediction B." not in by_claim
        assert "Prediction C." in by_claim


class TestInferPremisesBatch:
    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_empty_input(self) -> None:
        from src.url_content_scan.analyses.claims.premises import infer_premises_batch

        result = await infer_premises_batch([], _make_settings())
        assert result == {}

    @pytest.mark.asyncio
    async def test_calls_agent_and_maps_response(self) -> None:
        from src.url_content_scan.analyses.claims.premises import (
            _PremiseExtractionItem,
            _PremiseExtractionResponse,
            infer_premises_batch,
        )

        fake_response = _PremiseExtractionResponse(
            results=[
                _PremiseExtractionItem(
                    canonical_text="Climate change is a hoax.",
                    premises=["Scientific consensus can be wrong", "Data can be manipulated"],
                )
            ]
        )

        mock_result = AsyncMock()
        mock_result.output = fake_response

        with (
            patch("src.llm_config.model_factory.build_url_scan_vertex_model"),
            patch(
                "src.url_content_scan.analyses.claims.premises._PREMISES_AGENT.run",
                new=AsyncMock(return_value=mock_result),
            ),
        ):
            result = await infer_premises_batch(["Climate change is a hoax."], _make_settings())

        assert "Climate change is a hoax." in result
        assert result["Climate change is a hoax."] == [
            "Scientific consensus can be wrong",
            "Data can be manipulated",
        ]

    @pytest.mark.asyncio
    async def test_ignores_results_not_in_input(self) -> None:
        from src.url_content_scan.analyses.claims.premises import (
            _PremiseExtractionItem,
            _PremiseExtractionResponse,
            infer_premises_batch,
        )

        fake_response = _PremiseExtractionResponse(
            results=[
                _PremiseExtractionItem(
                    canonical_text="HALLUCINATED CLAIM NOT IN INPUT",
                    premises=["fake premise"],
                )
            ]
        )

        mock_result = AsyncMock()
        mock_result.output = fake_response

        with (
            patch("src.llm_config.model_factory.build_url_scan_vertex_model"),
            patch(
                "src.url_content_scan.analyses.claims.premises._PREMISES_AGENT.run",
                new=AsyncMock(return_value=mock_result),
            ),
        ):
            result = await infer_premises_batch(["Real claim."], _make_settings())

        assert result == {"Real claim.": []}
