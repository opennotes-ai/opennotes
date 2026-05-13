"""Tests for the `run_trends_oppositions` slot wrapper."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions import trends_oppositions_slot
from src.analyses.opinions._trends_schemas import ClaimTrend, TrendsOppositionsReport
from src.analyses.schemas import SectionSlug
from src.config import Settings


class _Acquire:
    def __init__(self, sections_row: Any) -> None:
        self._sections_row = sections_row

    async def __aenter__(self) -> _Conn:
        return _Conn(self._sections_row)

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, sections_row: Any) -> None:
        self._sections_row = sections_row

    async def fetchval(self, *_args: object) -> object:
        return self._sections_row


class _Pool:
    def __init__(self, sections_row: Any) -> None:
        self._sections_row = sections_row

    def acquire(self) -> _Acquire:
        return _Acquire(self._sections_row)


class _FailingConn:
    async def fetchval(self, *_args: object) -> object:
        raise RuntimeError("simulated db failure")


class _FailingPool:
    def acquire(self) -> object:
        class _FailingAcquire:
            async def __aenter__(self) -> _FailingConn:
                return _FailingConn()

            async def __aexit__(self, *args: object) -> None:
                return None

        return _FailingAcquire()


def _settings() -> Settings:
    return Settings()


def _slot_payload(*, state: str = "done") -> dict[str, Any]:
    return {"state": state, "attempt_id": str(uuid4()), "data": {}}  # data overwritten by tests


def _claims_report(*clusters: DedupedClaim) -> dict[str, Any]:
    report = ClaimsReport(
        deduped_claims=list(clusters),
        total_claims=len(clusters),
        total_unique=len(clusters),
    )
    return report.model_dump(mode="json")


def _cluster(text: str, category: ClaimCategory) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=text,
        category=category,
        occurrence_count=1,
        author_count=1,
        utterance_ids=["u-1"],
        representative_authors=["alice"],
    )


def _empty_report() -> dict[str, Any]:
    return {
        "trends_oppositions_report": {
            "trends": [],
            "oppositions": [],
            "input_cluster_count": 0,
            "skipped_for_cap": 0,
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["failed"])
async def test_trends_oppositions_facts_slot_not_done_returns_empty_report(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    fake = AsyncMock(
        return_value=TrendsOppositionsReport(
            trends=[],
            oppositions=[],
            input_cluster_count=0,
            skipped_for_cap=0,
        )
    )
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake)
    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                **_slot_payload(state=state),
                "data": {"claims_report": _claims_report()},
            }
        }
    }

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    assert result == _empty_report()
    fake.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("facts_state", ["pending", "running"])
async def test_trends_oppositions_retry_payload_none_facts_slot_not_done_raises(
    facts_state: str,
) -> None:
    pool = _Pool(
        json.dumps(
            {
                SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                    "state": facts_state,
                    "attempt_id": str(uuid4()),
                    "data": {"claims_report": _claims_report()},
                }
            }
        )
    )

    with pytest.raises(
        trends_oppositions_slot.TrendsDependenciesNotReadyError,
        match="dependencies not ready",
    ):
        await trends_oppositions_slot.run_trends_oppositions(
            pool=pool,
            job_id=uuid4(),
            task_attempt=uuid4(),
            payload=None,
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_trends_oppositions_retry_payload_none_facts_slot_missing_empty() -> None:
    pool = _Pool(json.dumps({}))

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=pool,
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=None,
        settings=_settings(),
    )

    assert result == _empty_report()


@pytest.mark.asyncio
async def test_trends_oppositions_retry_payload_none_facts_slot_failed_empty() -> None:
    pool = _Pool(
        json.dumps(
            {
                SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                    "state": "failed",
                    "attempt_id": str(uuid4()),
                    "data": {
                        "claims_report": {
                            "deduped_claims": [],
                            "total_claims": 0,
                            "total_unique": 0,
                        }
                    },
                }
            }
        )
    )

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=pool,
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=None,
        settings=_settings(),
    )

    assert result == _empty_report()


@pytest.mark.asyncio
async def test_trends_oppositions_retry_payload_none_reads_done_facts_slot_from_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = AsyncMock(
        return_value=TrendsOppositionsReport(
            trends=[
                ClaimTrend(
                    label="Retry-only fact",
                    cluster_texts=["cluster-1"],
                    summary="Two subjective/self clusters found.",
                )
            ],
            oppositions=[],
            input_cluster_count=2,
            skipped_for_cap=0,
        )
    )
    captured: list[DedupedClaim] = []

    async def fake_extract(clusters: list[DedupedClaim], **kwargs: Any) -> TrendsOppositionsReport:
        captured.extend(clusters)
        assert kwargs["settings"] is not None
        return await fake(clusters=clusters, **kwargs)

    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake_extract)

    sections = json.dumps(
        {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "done",
                "attempt_id": str(uuid4()),
                "data": {
                    "claims_report": _claims_report(
                        _cluster("I like this", ClaimCategory.SUBJECTIVE),
                        _cluster("I prefer this", ClaimCategory.SELF_CLAIMS),
                        _cluster("This is true", ClaimCategory.POTENTIALLY_FACTUAL),
                    )
                },
            }
        }
    )
    pool = _Pool(sections)

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=pool,
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=None,
        settings=_settings(),
    )

    assert result["trends_oppositions_report"]["input_cluster_count"] == 2
    assert [cluster.canonical_text for cluster in captured] == [
        "I like this",
        "I prefer this",
    ]
    assert result["trends_oppositions_report"]["trends"][0]["label"] == "Retry-only fact"


@pytest.mark.asyncio
async def test_trends_oppositions_retry_payload_none_db_error_is_not_swallowed() -> None:
    pool = _FailingPool()

    with pytest.raises(RuntimeError, match="simulated db failure"):
        await trends_oppositions_slot.run_trends_oppositions(
            pool=pool,
            job_id=uuid4(),
            task_attempt=uuid4(),
            payload=None,
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_trends_oppositions_facts_slot_malformed_db_payload_returns_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = AsyncMock(
        return_value=TrendsOppositionsReport(
            trends=[],
            oppositions=[],
            input_cluster_count=0,
            skipped_for_cap=0,
        )
    )
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake)

    sections = {
        SectionSlug.FACTS_CLAIMS_DEDUP.value: {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"claims_report": "malformed"},
        }
    }
    pool = _Pool(json.dumps(sections))

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=pool,
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=None,
        settings=_settings(),
    )

    assert result == _empty_report()
    fake.assert_not_called()


@pytest.mark.asyncio
async def test_trends_oppositions_absent_facts_dedup_slot_returns_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = AsyncMock(
        return_value=TrendsOppositionsReport(
            trends=[],
            oppositions=[],
            input_cluster_count=0,
            skipped_for_cap=0,
        )
    )
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake)

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload={},
        settings=_settings(),
    )

    assert result == _empty_report()
    fake.assert_not_called()


@pytest.mark.asyncio
async def test_trends_oppositions_zero_deduped_claims_returns_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = AsyncMock(
        return_value=TrendsOppositionsReport(
            trends=[],
            oppositions=[],
            input_cluster_count=0,
            skipped_for_cap=0,
        )
    )
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake)
    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot_payload(),
        }
    }
    # Populate empty claims report; no analyzer call should happen.
    payload["sections"][SectionSlug.FACTS_CLAIMS_DEDUP.value]["data"] = {
        "claims_report": _claims_report()
    }

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    assert result == _empty_report()
    fake.assert_not_called()


@pytest.mark.asyncio
async def test_trends_oppositions_filters_to_subjective_and_self_claims_and_calls_analyzer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = TrendsOppositionsReport(
        trends=[
            ClaimTrend(
                label="Climate is debated",
                cluster_texts=["Subj", "Self"],
                summary="Subjective and self claims repeat.",
            )
        ],
        oppositions=[],
        input_cluster_count=2,
        skipped_for_cap=0,
    )
    captured_calls: list[list[DedupedClaim]] = []

    async def fake_extract(clusters: list[DedupedClaim], **kwargs: Any) -> TrendsOppositionsReport:
        assert kwargs["settings"] is not None
        captured_calls.append(clusters)
        return report

    fake = AsyncMock(wraps=fake_extract)
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake)

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot_payload(),
        }
    }
    payload["sections"][SectionSlug.FACTS_CLAIMS_DEDUP.value]["data"] = {
        "claims_report": _claims_report(
            _cluster("I like this", ClaimCategory.SUBJECTIVE),
            _cluster("I dislike this", ClaimCategory.SELF_CLAIMS),
            _cluster("The sky is blue", ClaimCategory.POTENTIALLY_FACTUAL),
        )
    }

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    assert fake.call_count == 1
    clustered_calls = [
        cluster.canonical_text for cluster in captured_calls[0]
    ]
    assert clustered_calls == ["I like this", "I dislike this"]
    assert result["trends_oppositions_report"]["trends"] == [
        {
            "label": "Climate is debated",
            "cluster_texts": ["Subj", "Self"],
            "summary": "Subjective and self claims repeat.",
        }
    ]
    assert result["trends_oppositions_report"]["input_cluster_count"] == 2


@pytest.mark.asyncio
async def test_trends_oppositions_malformed_facts_payload_returns_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = AsyncMock(
        return_value=TrendsOppositionsReport(
            trends=[],
            oppositions=[],
            input_cluster_count=0,
            skipped_for_cap=0,
        )
    )
    monkeypatch.setattr(trends_oppositions_slot, "extract_trends_oppositions", fake)

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                **_slot_payload(),
                "data": {"claims_report": "malformed"},
            }
        }
    }

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    assert result == _empty_report()
    fake.assert_not_called()
