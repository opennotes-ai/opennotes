from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions.highlights_slot import run_highlights
from src.analyses.schemas import SectionSlug
from src.config import Settings


class _Acquire:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn

    async def __aenter__(self) -> "_Conn":
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, utterance_rows: list[dict[str, Any]]) -> None:
        self._utterance_rows = utterance_rows

    async def fetch(self, *_args: object) -> list[dict[str, Any]]:
        return self._utterance_rows


class _Pool:
    def __init__(self, utterance_rows: list[dict[str, Any]]) -> None:
        self._conn = _Conn(utterance_rows)

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


def _cluster(
    text: str,
    *,
    category: ClaimCategory = ClaimCategory.SUBJECTIVE,
    occurrence_count: int,
    author_count: int,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=author_count,
        utterance_ids=[f"u-{text}-{i}" for i in range(occurrence_count)],
        representative_authors=[f"author-{i}" for i in range(author_count)],
    )


def _facts_payload(*clusters: DedupedClaim) -> dict[str, Any]:
    report = ClaimsReport(
        deduped_claims=list(clusters),
        total_claims=len(clusters),
        total_unique=len(clusters),
    )
    return {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: {
                "state": "done",
                "attempt_id": str(uuid4()),
                "data": {"claims_report": report.model_dump(mode="json")},
            }
        }
    }


def _utterance_rows(
    *,
    total_authors: int,
    total_utterances: int,
) -> list[dict[str, Any]]:
    return [
        {
            "utterance_id": f"u-{idx}",
            "kind": "comment",
            "text": f"utterance {idx}",
            "author": f"author-{idx % total_authors}",
            "timestamp_at": None,
            "parent_id": None,
        }
        for idx in range(total_utterances)
    ]


@pytest.mark.asyncio
async def test_large_thread_highlights_slot_curates_instead_of_flat_subjective_dump() -> None:
    settings = Settings()
    flat_dump_candidates = [
        _cluster(
            f"lower influence subjective cluster {idx}",
            occurrence_count=3 + (idx % 4),
            author_count=2 + (idx % 4),
        )
        for idx in range(20)
    ]
    scaled_survivors = [
        _cluster(
            f"high influence subjective cluster {idx}",
            occurrence_count=18 + idx,
            author_count=9 + idx,
        )
        for idx in range(6)
    ]
    ignored_factual = [
        _cluster(
            "factual cluster that old subjective dump would not show",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=200,
            author_count=120,
        )
    ]

    result = await run_highlights(
        pool=_Pool(_utterance_rows(total_authors=200, total_utterances=1_000)),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_facts_payload(
            *flat_dump_candidates,
            *scaled_survivors,
            *ignored_factual,
        ),
        settings=settings,
    )
    report = result["highlights_report"]

    prior_flat_dump_count = len(flat_dump_candidates) + len(scaled_survivors)
    assert prior_flat_dump_count >= 20
    assert report["total_input_count"] == prior_flat_dump_count
    assert report["floor_eligible_count"] == prior_flat_dump_count
    assert report["fallback_engaged"] is False
    assert len(report["highlights"]) == len(scaled_survivors)
    assert len(report["highlights"]) <= 8
    assert len(report["highlights"]) < prior_flat_dump_count / 3
    assert {h["cluster"]["canonical_text"] for h in report["highlights"]} == {
        c.canonical_text for c in scaled_survivors
    }
    assert all(h["crossed_scaled_threshold"] for h in report["highlights"])


@pytest.mark.asyncio
async def test_small_thread_highlights_slot_falls_back_to_floor_eligible_cluster() -> None:
    settings = Settings()
    floor_only = _cluster(
        "small thread floor eligible but below scaled threshold",
        occurrence_count=4,
        author_count=2,
    )
    below_floor = _cluster(
        "small thread one-off opinion",
        occurrence_count=2,
        author_count=1,
    )

    result = await run_highlights(
        pool=_Pool(_utterance_rows(total_authors=6, total_utterances=20)),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_facts_payload(floor_only, below_floor),
        settings=settings,
    )
    report = result["highlights_report"]

    assert report["threshold"]["total_authors"] == 6
    assert report["threshold"]["total_utterances"] == 20
    assert report["threshold"]["min_authors_required"] == 2
    assert report["threshold"]["min_occurrences_required"] > floor_only.occurrence_count
    assert report["total_input_count"] == 2
    assert report["floor_eligible_count"] == 1
    assert report["fallback_engaged"] is True
    assert len(report["highlights"]) == 1
    assert report["highlights"][0]["cluster"] == floor_only.model_dump(mode="json")
    assert report["highlights"][0]["crossed_scaled_threshold"] is False
