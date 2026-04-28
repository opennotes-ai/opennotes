from __future__ import annotations

from typing import Any
from uuid import UUID

from src.utils.url_security import InvalidURL, validate_public_http_url
from src.utterances.schema import Utterance

_SELECT_JOB_UTTERANCES_SQL = """
SELECT
    j.url AS job_url,
    u.utterance_id,
    u.kind,
    u.text,
    u.author,
    u.timestamp_at,
    u.parent_id
FROM vibecheck_jobs j
LEFT JOIN vibecheck_job_utterances u
    ON u.job_id = j.job_id
WHERE j.job_id = $1
ORDER BY u.position
"""


def _normalize_for_match(url: str) -> str | None:
    try:
        return validate_public_http_url(url)
    except InvalidURL:
        return None


async def get_utterances_for_archive(
    pool: Any,
    job_id: UUID,
    requested_url: str,
) -> list[Utterance]:
    requested_normalized = _normalize_for_match(requested_url)
    if requested_normalized is None:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_JOB_UTTERANCES_SQL, job_id)

    if not rows:
        return []

    job_url = rows[0]["job_url"]
    if not isinstance(job_url, str):
        return []
    if _normalize_for_match(job_url) != requested_normalized:
        return []

    utterances: list[Utterance] = []
    for row in rows:
        if row["text"] is None or row["kind"] is None:
            continue
        utterances.append(
            Utterance(
                utterance_id=row["utterance_id"],
                kind=row["kind"],
                text=row["text"],
                author=row["author"],
                timestamp=row["timestamp_at"],
                parent_id=row["parent_id"],
            )
        )
    return utterances
