"""Tests for claim premises enrichment (`premises.py` and `premises_slot.py`)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.analyses.claims import premises
from src.analyses.claims._claims_schemas import (
    ClaimCategory,
    ClaimsReport,
    DedupedClaim,
    Premise,
    PremisesRegistry,
)
from src.analyses.claims.premises_slot import run_claims_premises
from src.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _claims_report(*texts: str) -> ClaimsReport:
    return ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text=text,
                category=ClaimCategory.PREDICTIONS
                if "will" in text
                else ClaimCategory.SUBJECTIVE,
                occurrence_count=1,
                author_count=1,
                utterance_ids=["u-1"],
                representative_authors=["alice"],
            )
            for text in texts
        ],
        total_claims=len(texts),
        total_unique=len(texts),
    )


class _Acquire:
    def __init__(self, row: object) -> None:
        self._row = row

    async def __aenter__(self) -> _Conn:
        return _Conn(self._row)

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, row: object) -> None:
        self._row = row

    async def fetchval(self, *_args: object) -> object:
        return self._row


class _Pool:
    def __init__(self, row: object) -> None:
        self._row = row

    def acquire(self) -> _Acquire:
        return _Acquire(self._row)


async def test_build_premises_by_claim_uses_batch_seam_and_dedupes_shared_premises(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_infer_premises_batch(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[str]]:
        assert len(claim_texts) == 2
        return {
            "Claim A will happen.": ["First premise", "Second premise"],
            "Claim B is likely true.": ["Second premise", "Third premise"],
        }

    monkeypatch.setattr(premises, "infer_premises_batch", fake_infer_premises_batch)

    claims = _claims_report("Claim A will happen.", "Claim B is likely true.", "Other claim.")
    claims.deduped_claims[2].category = ClaimCategory.OTHER
    # "Other claim." receives no premises from the seam and should stay unassigned.
    registry, premise_ids_by_claim = await premises.build_premises_by_claim(
        claims.deduped_claims,
        settings,
    )

    assert "Other claim." not in premise_ids_by_claim
    assert len(registry.premises) == 3
    values = list(premise_ids_by_claim.values())
    shared_second_ids = set(values[0]).intersection(values[1])
    assert len(shared_second_ids) == 1
    shared_id = next(iter(shared_second_ids))
    assert registry.premises[shared_id].statement == "Second premise"


async def test_build_premises_by_claim_dedupes_minor_text_variants(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_infer_premises_batch(
        _claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[str]]:
        return {
            "Claim A will happen.": ["The market responds quickly."],
            "Claim B is likely true.": ["market responds quickly"],
        }

    monkeypatch.setattr(premises, "infer_premises_batch", fake_infer_premises_batch)

    registry, premise_ids_by_claim = await premises.build_premises_by_claim(
        _claims_report("Claim A will happen.", "Claim B is likely true.").deduped_claims,
        settings,
    )

    assert len(registry.premises) == 1
    values = list(premise_ids_by_claim.values())
    assert values[0] == values[1]


async def test_build_premises_by_claim_filters_noneligible_categories(settings: Settings) -> None:
    claims = _claims_report("Claim A will happen.", "Claim C is opinion.")
    claims.deduped_claims[0].category = ClaimCategory.OTHER
    claims.deduped_claims[1].category = ClaimCategory.POTENTIALLY_FACTUAL

    registry, premise_ids_by_claim = await premises.build_premises_by_claim(
        claims.deduped_claims, settings
    )

    assert premise_ids_by_claim == {}
    assert registry.premises == {}


async def test_run_claims_premises_adds_premise_ids_and_registry_from_payload(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    async def fake_build_premises_by_claim(
        *_args: object,
    ) -> tuple[PremisesRegistry, dict[str, list[str]]]:
        return (
            PremisesRegistry(
                premises={
                    "premise_abc": Premise(
                        premise_id="premise_abc",
                        statement="Shared premise",
                    )
                }
            ),
            {
                "Prediction claim?": ["premise_abc"],
            },
        )

    monkeypatch.setattr(
        "src.analyses.claims.premises_slot.build_premises_by_claim",
        fake_build_premises_by_claim,
    )

    result = await run_claims_premises(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=SimpleNamespace(claims_report=_claims_report("Prediction claim?")),
        settings=settings,
    )

    claims = result["claims_report"]["deduped_claims"][0]
    assert claims["premise_ids"] == ["premise_abc"]
    assert (
        result["claims_report"]["premises"]["premises"]["premise_abc"]["statement"]
        == "Shared premise"
    )


async def test_run_claims_premises_falls_back_to_dedup_slot_when_payload_missing(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    fake_row = {
        "state": "done",
        "data": {
            "claims_report": _claims_report("Fallback claim.").model_dump(mode="json")
        },
    }

    async def fake_build_premises_by_claim(
        *_args: object,
    ) -> tuple[PremisesRegistry, dict[str, list[str]]]:
        return PremisesRegistry(), {}

    monkeypatch.setattr(
        "src.analyses.claims.premises_slot.build_premises_by_claim",
        fake_build_premises_by_claim,
    )

    result = await run_claims_premises(
        pool=_Pool(fake_row),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=object(),
        settings=settings,
    )

    assert result["claims_report"]["deduped_claims"][0]["canonical_text"] == "Fallback claim."
