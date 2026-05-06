"""Tests for claim evidence enrichment (`evidence.py` and `evidence_slot.py`)."""
from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

import pytest

from src.analyses.claims import evidence
from src.analyses.claims._claims_schemas import (
    ClaimCategory,
    ClaimsReport,
    DedupedClaim,
    SourceKind,
)
from src.analyses.claims.evidence_slot import run_claims_evidence
from src.config import Settings
from src.utterances.schema import Utterance


class _Acquire:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def __aenter__(self) -> _Conn:
        return _Conn(self._row)

    async def __aexit__(self, *args: object) -> None:
        return None


class _Conn:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def fetchval(self, *_args: object) -> Any:
        return self._row


class _Pool:
    def __init__(self, row: Any) -> None:
        self._row = row

    def acquire(self) -> _Acquire:
        return _Acquire(self._row)


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _claims_report(*texts: str) -> ClaimsReport:
    return ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text=text,
                category=ClaimCategory.POTENTIALLY_FACTUAL,
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


class _Payload:
    def __init__(self, claims_report: ClaimsReport) -> None:
        self.claims_report = claims_report


@pytest.mark.asyncio
async def test_build_supporting_facts_only_includes_potentially_factual_claims(
    settings: Settings,
) -> None:
    claims = [
        DedupedClaim(
            canonical_text="The moon is round.",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["u-1"],
            representative_authors=["alice"],
        ),
        DedupedClaim(
            canonical_text="I think it will rain.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["u-2"],
            representative_authors=["alice"],
        ),
    ]

    facts = await evidence.build_supporting_facts_by_claim(
        claims,
        {"u-1": "First sentence", "u-2": "Second"},
        settings,
    )

    assert [fact.model_dump(mode="json") for fact in facts["The moon is round."]] == [
        {
            "statement": "The moon is round.",
            "source_kind": SourceKind.UTTERANCE.value,
            "source_ref": "u-1",
        }
    ]
    assert "I think it will rain." not in facts


@pytest.mark.asyncio
async def test_build_supporting_facts_budgets_external_batch(
    settings: Settings,
) -> None:
    calls: list[list[str]] = []

    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        calls.append(list(claim_texts))
        return {text: [] for text in claim_texts}

    claims = [
        DedupedClaim(
            canonical_text=f"claim {index}",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=1,
            author_count=1,
            utterance_ids=[],
            representative_authors=["alice"],
        )
        for index in range(6)
    ]

    await evidence.build_supporting_facts_by_claim(
        claims,
        {},
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert calls == [[f"claim {i}" for i in range(5)]]


@pytest.mark.asyncio
async def test_build_supporting_facts_adds_external_facts_even_with_inline_facts(
    settings: Settings,
) -> None:
    async def fake_external_fetcher(
        claim_texts: list[str], _settings: Settings
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            claim_texts[0]: [
                {
                    "statement": "NASA describes the moon as round.",
                    "source_kind": SourceKind.EXTERNAL.value,
                    "source_ref": "https://science.example/moon",
                }
            ]
        }

    facts = await evidence.build_supporting_facts_by_claim(
        _claims_report("The moon is round.").deduped_claims,
        {"u-1": "The moon is round and glows."},
        settings,
        external_fetcher=fake_external_fetcher,
    )

    assert [fact.source_kind for fact in facts["The moon is round."]] == [
        SourceKind.UTTERANCE,
        SourceKind.EXTERNAL,
    ]


def test_grounded_urls_from_result_normalizes_search_result_urls() -> None:
    class _Returned:
        content: ClassVar[list[dict[str, str]]] = [
            {"uri": "HTTPS://Example.Test/source/"},
            {"uri": "https://example.test/source?ref=search"},
        ]

    class _Response:
        builtin_tool_calls: ClassVar[list[tuple[object, _Returned]]] = [
            (object(), _Returned())
        ]

    class _Result:
        response = _Response()

    assert evidence._grounded_urls_from_result(_Result()) == {
        "https://example.test/source",
        "https://example.test/source?ref=search",
    }


@pytest.mark.asyncio
async def test_run_claims_evidence_merges_from_payload(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    async def fake_load_utterances(_pool: object, job_id: object) -> list[Utterance]:
        del job_id
        return [
            Utterance(
                kind="comment",
                text="The moon is round and glows.",
                utterance_id="u-1",
                author="alice",
            )
        ]

    monkeypatch.setattr(
        "src.analyses.claims.evidence_slot.load_job_utterances",
        fake_load_utterances,
    )

    result = await run_claims_evidence(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=_Payload(_claims_report("The moon is round.")),
        settings=settings,
    )

    claim = result["claims_report"]["deduped_claims"][0]
    assert claim["canonical_text"] == "The moon is round."
    assert claim["supporting_facts"] == [
        {
            "statement": "The moon is round.",
            "source_kind": "utterance",
            "source_ref": "u-1",
        }
    ]


@pytest.mark.asyncio
async def test_run_claims_evidence_falls_back_to_dedup_slot_when_payload_missing(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    fake_row = {
        "state": "done",
        "data": {
            "claims_report": _claims_report("The ocean is blue.").model_dump(mode="json")
        },
    }

    async def fake_load_utterances(_pool: object, job_id: object) -> list[Utterance]:
        del job_id
        return [
            Utterance(
                kind="post",
                text="Scientists observe the ocean.",
                utterance_id="u-1",
                author="alice",
            )
        ]

    monkeypatch.setattr(
        "src.analyses.claims.evidence_slot.load_job_utterances",
        fake_load_utterances,
    )

    result = await run_claims_evidence(
        pool=_Pool(fake_row),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=object(),
        settings=settings,
    )

    claim = result["claims_report"]["deduped_claims"][0]
    assert claim["canonical_text"] == "The ocean is blue."
    assert claim["supporting_facts"] == [
        {
            "statement": "The ocean is blue.",
            "source_kind": "utterance",
            "source_ref": "u-1",
        }
    ]
