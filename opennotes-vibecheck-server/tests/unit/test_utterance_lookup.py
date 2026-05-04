from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.utterances.lookup import get_utterances_for_archive


class FakeAcquire:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    async def __aenter__(self) -> Any:
        return self.conn

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakePool:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self)

    async def fetch(self, query: str, job_id: object) -> list[dict[str, object]]:
        del query, job_id
        return self.rows


async def test_get_utterances_for_archive_allows_pdf_gcs_key_match() -> None:
    job_id = uuid4()
    gcs_key = "22222222-2222-4222-8222-222222222222"
    rows: list[dict[str, object]] = [
        {
            "job_url": gcs_key,
            "normalized_url": gcs_key,
            "source_type": "pdf",
            "utterance_id": "pdf-1",
            "kind": "post",
            "text": "Alice opens calmly.",
            "author": None,
            "timestamp_at": None,
            "parent_id": None,
        }
    ]

    utterances = await get_utterances_for_archive(FakePool(rows), job_id, gcs_key)

    assert len(utterances) == 1
    assert utterances[0].utterance_id == "pdf-1"
    assert utterances[0].text == "Alice opens calmly."


async def test_get_utterances_for_archive_rejects_mismatched_pdf_key() -> None:
    rows: list[dict[str, object]] = [
        {
            "job_url": "22222222-2222-4222-8222-222222222222",
            "normalized_url": "22222222-2222-4222-8222-222222222222",
            "source_type": "pdf",
            "utterance_id": "pdf-1",
            "kind": "post",
            "text": "Alice opens calmly.",
            "author": None,
            "timestamp_at": None,
            "parent_id": None,
        }
    ]

    utterances = await get_utterances_for_archive(
        FakePool(rows),
        uuid4(),
        "33333333-3333-4333-8333-333333333333",
    )

    assert utterances == []
