"""Tests for the DBOS url_scan_workflow premises/evidence slot fan-out.

Covers TASK-1657.04 TDD requirement:
- DBOS workflow fan-out includes the two new slots (facts_claims__premises, facts_claims__evidence)
"""

from __future__ import annotations

import pytest


class TestPremisesEvidenceSectionRunners:
    def test_section_runner_map_covers_premises_and_evidence(self) -> None:
        from src.url_content_scan.schemas import SectionSlug

        assert SectionSlug.FACTS_CLAIMS_PREMISES in SectionSlug
        assert SectionSlug.FACTS_CLAIMS_EVIDENCE in SectionSlug
        assert SectionSlug.FACTS_CLAIMS_PREMISES.value == "facts_claims__premises"
        assert SectionSlug.FACTS_CLAIMS_EVIDENCE.value == "facts_claims__evidence"

    def test_section_runners_dict_covers_all_slugs(self) -> None:
        from src.dbos_workflows.url_scan_workflow import _SECTION_RUNNERS
        from src.url_content_scan.schemas import SectionSlug

        missing = set(SectionSlug) - set(_SECTION_RUNNERS)
        assert not missing, f"_SECTION_RUNNERS is missing slugs: {missing}"

    def test_premises_runner_is_registered(self) -> None:
        from src.dbos_workflows.url_scan_workflow import _SECTION_RUNNERS
        from src.url_content_scan.schemas import SectionSlug

        assert SectionSlug.FACTS_CLAIMS_PREMISES in _SECTION_RUNNERS

    def test_evidence_runner_is_registered(self) -> None:
        from src.dbos_workflows.url_scan_workflow import _SECTION_RUNNERS
        from src.url_content_scan.schemas import SectionSlug

        assert SectionSlug.FACTS_CLAIMS_EVIDENCE in _SECTION_RUNNERS

    @pytest.mark.asyncio
    async def test_premises_runner_returns_claims_report(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        from src.dbos_workflows.url_scan_workflow import (
            _SECTION_RUNNERS,
            UrlScanWorkflowInputs,
        )
        from src.url_content_scan.claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
        from src.url_content_scan.schemas import SectionSlug

        claim = DedupedClaim(
            canonical_text="We should act on climate.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["utt-1"],
            representative_authors=["alice"],
        )
        claims_report = ClaimsReport(
            deduped_claims=[claim],
            total_claims=1,
            total_unique=1,
        )
        inputs = UrlScanWorkflowInputs(claims_report=claims_report)

        async def fake_extractor(texts: list[str], settings: object) -> dict[str, list[str]]:
            return {text: ["premise A"] for text in texts}

        fake_settings = SimpleNamespace(
            PREMISES_MAX_CLAIMS_PER_BATCH=30,
            DEFAULT_FULL_MODEL="google-vertex:gemini-pro",
        )

        with patch("src.config.get_settings", return_value=fake_settings):
            runner = _SECTION_RUNNERS[SectionSlug.FACTS_CLAIMS_PREMISES]
            result = await runner(inputs)

        assert "claims_report" in result
        assert len(result["claims_report"]["deduped_claims"]) == 1

    @pytest.mark.asyncio
    async def test_evidence_runner_returns_claims_report(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        from src.dbos_workflows.url_scan_workflow import (
            _SECTION_RUNNERS,
            UrlScanWorkflowInputs,
        )
        from src.url_content_scan.claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
        from src.url_content_scan.schemas import SectionSlug

        claim = DedupedClaim(
            canonical_text="Fossil fuels drive climate change.",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["utt-1"],
            representative_authors=["alice"],
        )
        claims_report = ClaimsReport(
            deduped_claims=[claim],
            total_claims=1,
            total_unique=1,
        )
        inputs = UrlScanWorkflowInputs(claims_report=claims_report)

        async def fake_fetcher(texts: list[str], settings: object) -> dict[str, list[dict]]:
            return {}

        fake_settings = SimpleNamespace(
            EVIDENCE_MAX_EXTERNAL_CLAIMS=10,
            EVIDENCE_SYNTHESIS_CANDIDATE_CAP=60,
            EVIDENCE_GROUNDED_FETCH_GROUPS_PER_CALL=1,
            DEFAULT_MINI_MODEL="google-vertex:gemini-flash",
            DEFAULT_FULL_MODEL="google-vertex:gemini-pro",
        )

        with patch("src.config.get_settings", return_value=fake_settings):
            runner = _SECTION_RUNNERS[SectionSlug.FACTS_CLAIMS_EVIDENCE]
            result = await runner(inputs)

        assert "claims_report" in result
        assert len(result["claims_report"]["deduped_claims"]) == 1

    def test_hydrate_section_inputs_loads_dedup_for_premises(self) -> None:
        from unittest.mock import patch

        from src.dbos_workflows.url_scan_workflow import (
            UrlScanWorkflowInputs,
            _hydrate_section_inputs,
        )
        from src.url_content_scan.claims_schemas import ClaimsReport
        from src.url_content_scan.schemas import SectionSlug

        claims_report = ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)
        dedup_payload = claims_report.model_dump(mode="json")

        inputs_without_report = UrlScanWorkflowInputs()

        with patch(
            "src.dbos_workflows.url_scan_workflow.load_url_scan_section_payload_step",
            return_value=dedup_payload,
        ):
            hydrated = _hydrate_section_inputs(
                "test-job-id",
                SectionSlug.FACTS_CLAIMS_PREMISES,
                inputs_without_report,
            )

        assert hydrated.claims_report is not None

    def test_hydrate_section_inputs_loads_dedup_for_evidence(self) -> None:
        from unittest.mock import patch

        from src.dbos_workflows.url_scan_workflow import (
            UrlScanWorkflowInputs,
            _hydrate_section_inputs,
        )
        from src.url_content_scan.claims_schemas import ClaimsReport
        from src.url_content_scan.schemas import SectionSlug

        claims_report = ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)
        dedup_payload = claims_report.model_dump(mode="json")

        inputs_without_report = UrlScanWorkflowInputs()

        with patch(
            "src.dbos_workflows.url_scan_workflow.load_url_scan_section_payload_step",
            return_value=dedup_payload,
        ):
            hydrated = _hydrate_section_inputs(
                "test-job-id",
                SectionSlug.FACTS_CLAIMS_EVIDENCE,
                inputs_without_report,
            )

        assert hydrated.claims_report is not None
