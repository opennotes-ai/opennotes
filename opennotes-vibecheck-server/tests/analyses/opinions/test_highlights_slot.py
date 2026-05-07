"""Tests for the `run_highlights` slot wrapper."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions import highlights_slot
from src.analyses.opinions._highlights_schemas import (
    HighlightsThresholdInfo,
    OpinionsHighlightsReport,
)
from src.analyses.opinions.trends_oppositions_slot import FIRST_RUN_DEPENDENCY_PAYLOAD
from src.analyses.schemas import SectionSlug
from src.config import Settings
from src.utterances.schema import Utterance


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, sections_row: dict[str, Any], utterance_rows: list[dict[str, Any]]) -> None:
        self._sections_row = sections_row
        self._utterance_rows = utterance_rows

    async def fetchval(self, *_args: object) -> dict[str, Any]:
        return self._sections_row

    async def fetch(self, *_args: object) -> list[dict[str, Any]]:
        return self._utterance_rows


class _Pool:
    def __init__(self, sections_row: dict[str, Any], utterance_rows: list[dict[str, Any]]) -> None:
        self._conn = _Conn(sections_row, utterance_rows)

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


def _settings() -> Settings:
    return Settings()


def _slot_payload(*, state: str = "done") -> dict[str, Any]:
    return {"state": state, "attempt_id": str(uuid4()), "data": {}}


def _cluster(text: str, category: ClaimCategory) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=text,
        category=category,
        occurrence_count=3,
        author_count=2,
        utterance_ids=["u-1", "u-2", "u-3"],
        representative_authors=["alice", "bob"],
    )


def _claims_report(*clusters: DedupedClaim) -> dict[str, Any]:
    report = ClaimsReport(
        deduped_claims=list(clusters),
        total_claims=len(clusters),
        total_unique=len(clusters),
    )
    return report.model_dump(mode="json")


def _empty_report() -> dict[str, Any]:
    return {
        "highlights_report": {
            "highlights": [],
            "threshold": {
                "total_authors": 0,
                "total_utterances": 0,
                "min_authors_required": 2,
                "min_occurrences_required": 3,
            },
            "fallback_engaged": False,
            "floor_eligible_count": 0,
            "total_input_count": 0,
        }
    }


@pytest.mark.asyncio
async def test_highlights_absent_facts_slot_returns_empty_without_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_compute = AsyncMock()
    monkeypatch.setattr(highlights_slot, "compute_highlights", fake_compute)

    result = await highlights_slot.run_highlights(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload={"sections": {}},
        settings=_settings(),
    )

    assert result == _empty_report()
    fake_compute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts_payload",
    [
        {"state": "failed", "attempt_id": str(uuid4()), "data": {"claims_report": _claims_report()}},
        {"state": "pending", "attempt_id": str(uuid4()), "data": {"claims_report": _claims_report()}},
        {"state": "running", "attempt_id": str(uuid4()), "data": {"claims_report": _claims_report()}},
        {"state": "done", "attempt_id": str(uuid4()), "data": {"claims_report": "oops"}},
        {"state": "done", "attempt_id": str(uuid4()), "data": {"claims_report": {"deduped_claims": "bad"}}},
        {"state": "done", "attempt_id": str(uuid4()), "data": {}},
    ],
)
async def test_highlights_invalid_or_not_done_facts_slot_returns_empty_without_compute(
    monkeypatch: pytest.MonkeyPatch,
    facts_payload: dict[str, Any],
) -> None:
    fake_compute = AsyncMock()
    monkeypatch.setattr(highlights_slot, "compute_highlights", fake_compute)

    result = await highlights_slot.run_highlights(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload={"sections": {SectionSlug.FACTS_CLAIMS_DEDUP.value: facts_payload}},
        settings=_settings(),
    )

    assert result == _empty_report()
    fake_compute.assert_not_called()


@pytest.mark.asyncio
async def test_highlights_only_factual_clusters_returns_empty_without_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_compute = AsyncMock()
    monkeypatch.setattr(highlights_slot, "compute_highlights", fake_compute)

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                **_slot_payload(),
                "data": {
                    "claims_report": _claims_report(
                        _cluster("Fact 1", ClaimCategory.POTENTIALLY_FACTUAL),
                        _cluster("Fact 2", ClaimCategory.POTENTIALLY_FACTUAL),
                    )
                },
            }
        }
    }

    result = await highlights_slot.run_highlights(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    assert result == _empty_report()
    fake_compute.assert_not_called()


@pytest.mark.asyncio
async def test_highlights_subjective_clusters_compute_with_utterance_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    expected_report = OpinionsHighlightsReport(
        highlights=[],
        threshold=HighlightsThresholdInfo(
            total_authors=2,
            total_utterances=4,
            min_authors_required=2,
            min_occurrences_required=3,
        ),
        fallback_engaged=False,
        floor_eligible_count=0,
        total_input_count=2,
    )

    def fake_compute(
        clusters: list[DedupedClaim],
        *,
        total_authors: int,
        total_utterances: int,
        settings: Settings,
    ) -> OpinionsHighlightsReport:
        captured["clusters"] = clusters
        captured["total_authors"] = total_authors
        captured["total_utterances"] = total_utterances
        captured["settings"] = settings
        return expected_report

    async def fake_load_job_utterances(*_args: Any, **_kwargs: Any) -> list[Utterance]:
        return [
            Utterance(utterance_id="u-1", kind="comment", text="a", author="alice"),
            Utterance(utterance_id="u-2", kind="comment", text="b", author="bob"),
            Utterance(utterance_id="u-3", kind="comment", text="c", author=""),
            Utterance(utterance_id="u-4", kind="comment", text="d", author=None),
        ]

    monkeypatch.setattr(highlights_slot, "compute_highlights", fake_compute)
    monkeypatch.setattr(highlights_slot, "load_job_utterances", fake_load_job_utterances)

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                **_slot_payload(),
                "data": {
                    "claims_report": _claims_report(
                        _cluster("Subjective 1", ClaimCategory.SUBJECTIVE),
                        _cluster("Self claim 1", ClaimCategory.SELF_CLAIMS),
                        _cluster("Factual 1", ClaimCategory.POTENTIALLY_FACTUAL),
                    )
                },
            }
        }
    }

    result = await highlights_slot.run_highlights(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    assert result == {"highlights_report": expected_report.model_dump(mode="json")}
    assert len(captured["clusters"]) == 2
    assert {c.category for c in captured["clusters"]} == {
        ClaimCategory.SUBJECTIVE,
        ClaimCategory.SELF_CLAIMS,
    }
    assert captured["total_authors"] == 2
    assert captured["total_utterances"] == 4
    assert isinstance(captured["settings"], Settings)


@pytest.mark.asyncio
async def test_highlights_first_run_sentinel_reads_done_facts_slot_from_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    expected_report = OpinionsHighlightsReport(
        highlights=[],
        threshold=HighlightsThresholdInfo(
            total_authors=2,
            total_utterances=3,
            min_authors_required=2,
            min_occurrences_required=3,
        ),
        fallback_engaged=False,
        floor_eligible_count=0,
        total_input_count=1,
    )

    def fake_compute(
        clusters: list[DedupedClaim],
        *,
        total_authors: int,
        total_utterances: int,
        settings: Settings,
    ) -> OpinionsHighlightsReport:
        captured["clusters"] = clusters
        captured["total_authors"] = total_authors
        captured["total_utterances"] = total_utterances
        captured["settings"] = settings
        return expected_report

    monkeypatch.setattr(highlights_slot, "compute_highlights", fake_compute)
    pool = _Pool(
        sections_row={
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                **_slot_payload(),
                "data": {
                    "claims_report": _claims_report(
                        _cluster("Subjective from persisted facts", ClaimCategory.SUBJECTIVE),
                    )
                },
            }
        },
        utterance_rows=[
            {
                "utterance_id": "u-1",
                "kind": "comment",
                "text": "a",
                "author": "alice",
                "timestamp_at": None,
                "parent_id": None,
            },
            {
                "utterance_id": "u-2",
                "kind": "comment",
                "text": "b",
                "author": "alice",
                "timestamp_at": None,
                "parent_id": None,
            },
            {
                "utterance_id": "u-3",
                "kind": "comment",
                "text": "c",
                "author": "bob",
                "timestamp_at": None,
                "parent_id": None,
            },
        ],
    )

    result = await highlights_slot.run_highlights(
        pool=pool,
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=FIRST_RUN_DEPENDENCY_PAYLOAD,
        settings=_settings(),
    )

    assert result == {"highlights_report": expected_report.model_dump(mode="json")}
    assert len(captured["clusters"]) == 1
    assert captured["clusters"][0].category == ClaimCategory.SUBJECTIVE
    assert captured["total_authors"] == 2
    assert captured["total_utterances"] == 3
    assert isinstance(captured["settings"], Settings)
