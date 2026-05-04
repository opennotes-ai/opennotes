from __future__ import annotations

from typing import Any
from uuid import UUID

from src.utils.url_security import InvalidURL, validate_public_http_url
from src.utterances.schema import Utterance

_SELECT_JOB_UTTERANCES_SQL = """
SELECT
    j.url AS job_url,
    j.normalized_url AS normalized_url,
    COALESCE(j.source_type, 'url') AS source_type,
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
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_JOB_UTTERANCES_SQL, job_id)

    if not rows:
        return []

    job_url = rows[0]["job_url"]
    source_type = rows[0]["source_type"]
    if source_type == "pdf":
        normalized_url = rows[0]["normalized_url"]
        if not isinstance(normalized_url, str) or normalized_url != requested_url:
            return []
    else:
        requested_normalized = _normalize_for_match(requested_url)
        if requested_normalized is None:
            return []
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
