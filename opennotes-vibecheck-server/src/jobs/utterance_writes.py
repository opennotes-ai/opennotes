"""Persist an extractor's UtterancesPayload to vibecheck_job_utterances.

The retry endpoint (routes/analyze.py) gates on
`EXISTS (SELECT 1 FROM vibecheck_job_utterances WHERE job_id = j.job_id)` so
every fresh-job retry rejects with `can_only_retry_after_extraction_succeeds`
unless we've written these rows. Prior to TASK-1473.57 the extractor returned
an in-memory payload that was never durable.

Contract:
    * The row's job.attempt_id is row-locked (FOR UPDATE) so a concurrent
      retry cannot rotate the envelope between the CAS check and the writes.
    * On attempt drift the function raises `HandlerSuperseded` (same semantics
      the rest of the pipeline uses for stale-attempt handling) so `run_job`'s
      supersede handler returns 200 and leaves the newer worker alone.
    * The DELETE+INSERT sequence is in a single transaction so readers never
      observe a partial snapshot — retry-from-zero can produce a shorter
      utterance list than before, and DELETE-before-INSERT is the right
      idempotency shape (upsert-only would leave stale rows behind).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from src.monitoring import get_logger
from src.utterances.schema import UtterancesPayload

logger = get_logger(__name__)


_SELECT_ATTEMPT_FOR_UPDATE_SQL = """
SELECT attempt_id
FROM vibecheck_jobs
WHERE job_id = $1
FOR UPDATE
"""

_DELETE_UTTERANCES_SQL = """
DELETE FROM vibecheck_job_utterances WHERE job_id = $1
"""

_UPDATE_JOB_METADATA_SQL = """
UPDATE vibecheck_jobs
SET page_title = $2,
    page_kind = $3,
    utterance_stream_type = $4,
    updated_at = now()
WHERE job_id = $1
"""

_INSERT_UTTERANCE_SQL = """
INSERT INTO vibecheck_job_utterances
  (job_id, utterance_id, kind, text, author,
   timestamp_at, parent_id, position)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""


class UtterancePersistenceSuperseded(Exception):  # noqa: N818 — matches HandlerSuperseded spec terminology; not raised as an "Error"
    """Raised when the job's attempt_id drifted while persisting utterances.

    The caller (orchestrator) catches this and raises HandlerSuperseded so
    run_job's supersede branch returns 200 without touching the cache.
    """


async def persist_utterances(
    pool: Any,
    job_id: UUID,
    expected_attempt: UUID,
    payload: UtterancesPayload,
) -> None:
    """Persist the extractor payload as a fresh snapshot of utterance rows.

    Raises:
        UtterancePersistenceSuperseded: job.attempt_id drifted from expected.
    """
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(_SELECT_ATTEMPT_FOR_UPDATE_SQL, job_id)
        if row is None:
            raise UtterancePersistenceSuperseded(
                f"persist_utterances: job {job_id} not found"
            )
        if row["attempt_id"] != expected_attempt:
            raise UtterancePersistenceSuperseded(
                f"persist_utterances: attempt drift for job {job_id} "
                f"(expected={expected_attempt}, actual={row['attempt_id']})"
            )
        await conn.execute(
            _UPDATE_JOB_METADATA_SQL,
            job_id,
            payload.page_title,
            payload.page_kind.value,
            payload.utterance_stream_type.value,
        )
        await conn.execute(_DELETE_UTTERANCES_SQL, job_id)
        for idx, utt in enumerate(payload.utterances):
            await conn.execute(
                _INSERT_UTTERANCE_SQL,
                job_id,
                utt.utterance_id,
                utt.kind,
                utt.text,
                utt.author,
                utt.timestamp,
                utt.parent_id,
                idx,
            )
