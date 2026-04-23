from __future__ import annotations

from typing import Any
from uuid import UUID

from src.utterances.schema import Utterance

_LOAD_UTTERANCES_SQL = """
SELECT utterance_id, kind, text, author, timestamp_at, parent_id
FROM vibecheck_job_utterances
WHERE job_id = $1
ORDER BY position, created_at, utterance_pk
"""


async def load_job_utterances(pool: Any, job_id: UUID) -> list[Utterance]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LOAD_UTTERANCES_SQL, job_id)
    return [
        Utterance(
            utterance_id=row["utterance_id"],
            kind=row["kind"],
            text=row["text"],
            author=row["author"],
            timestamp=row["timestamp_at"],
            parent_id=row["parent_id"],
        )
        for row in rows
    ]


__all__ = ["load_job_utterances"]
