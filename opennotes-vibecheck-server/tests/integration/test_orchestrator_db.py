"""Integration tests for orchestrator DB helpers (TASK-1474.23.03.12).

Migrated from `tests/unit/test_orchestrator.py` so the CAS-on-attempt_id
guards are exercised against a real Postgres rather than a hand-rolled
fake conn that has no notion of `attempt_id`. The fakes that lived in
the unit suite (`_StageRecorderConn`, `_ExecuteFailingConn`,
`_IncrementCounterConn`) could not catch a regression that drops the
`AND attempt_id = $N` clause from `_SET_LAST_STAGE_SQL` or
`_INCREMENT_EXTRACT_TRANSIENT_SQL` — this file closes that gap.

Coverage of the two CAS predicates the helpers depend on:

  - `_SET_LAST_STAGE_SQL` (orchestrator.py: `AND attempt_id = $3`)
    -> covered by `test_set_last_stage_no_op_on_rotated_attempt_id`.
  - `_INCREMENT_EXTRACT_TRANSIENT_SQL` (orchestrator.py: `AND attempt_id = $2`)
    -> covered by `test_increment_extract_transient_attempts_no_op_on_rotated_attempt`.

The two `_run_pipeline` migrations (transient/backstop) assert against
DB state and the structured `TerminalError.detail` payload introduced
in TASK-1474.23.03.13, not against substrings of the prose summary.

Reuses `_postgres_container` (module-scoped) + `db_pool` (per-test
fresh schema) + `INTEGRATION_DDL` from `tests/integration/conftest.py`.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from tests.integration.conftest import insert_pending_job, read_job


def _stub_extract_arm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit scrape/build/revalidate so tests focus on the
    extract arm's three-way classification. extract_utterances itself
    is NOT stubbed here — each test sets it per-case to raise the
    specific exception type under test.

    Carried verbatim from `tests/unit/test_orchestrator.py` so the
    migrated `_run_pipeline` tests have the same monkeypatch surface.
    """
    from src.jobs import orchestrator

    monkeypatch.setattr(
        orchestrator, "_build_scrape_cache", lambda s: MagicMock()
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda s: MagicMock()
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
    )

    async def stub_scrape_step(*args: Any, **kwargs: Any) -> Any:
        return MagicMock(metadata=None)

    async def stub_revalidate(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(orchestrator, "_scrape_step", stub_scrape_step)
    monkeypatch.setattr(
        orchestrator, "_revalidate_final_url", stub_revalidate
    )


async def _seed_extract_transient_attempts(
    pool: Any, job_id: UUID, value: int
) -> None:
    """Pre-load the in-row backstop counter for tests that exercise the
    backstop boundary (counter at MAX-1 then increments to MAX)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET extract_transient_attempts = $1 "
            "WHERE job_id = $2",
            value,
            job_id,
        )


async def _rotate_attempt_id(pool: Any, job_id: UUID) -> UUID:
    """Atomically rotate `attempt_id` to a fresh UUID. Returns the new
    attempt_id so the test can assert the row state didn't get
    overwritten by a stale CAS-miss helper call."""
    new_attempt = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET attempt_id = $1 WHERE job_id = $2",
            new_attempt,
            job_id,
        )
    return new_attempt


# ---------------------------------------------------------------------------
# _set_last_stage — CAS-on-attempt_id guard against stale workers.
# ---------------------------------------------------------------------------


async def test_set_last_stage_cas_writes_with_attempt_id(db_pool: Any) -> None:
    """Real DB: `_set_last_stage` writes `last_stage` when the row's
    `attempt_id` matches the caller's `task_attempt`."""
    from src.jobs import orchestrator

    job_id, attempt = await insert_pending_job(db_pool)

    await orchestrator._set_last_stage(
        db_pool, job_id, attempt, "persist_utterances"
    )

    row = await read_job(db_pool, job_id)
    assert row["last_stage"] == "persist_utterances"
    # CAS predicate verified: row's attempt_id is unchanged.
    assert row["attempt_id"] == attempt


async def test_set_last_stage_no_op_on_rotated_attempt_id(
    db_pool: Any,
) -> None:
    """CAS-MISS: rotate the row's `attempt_id` between insert and the
    helper call; `_set_last_stage` is a NO-OP, no exception, no
    `last_stage` write. This is the regression gap that motivated the
    ticket — the in-process `_StageRecorderConn` had no notion of
    `attempt_id` and would have silently logged a write that real
    Postgres rejects."""
    from src.jobs import orchestrator

    job_id, original_attempt = await insert_pending_job(db_pool)
    rotated = await _rotate_attempt_id(db_pool, job_id)
    assert rotated != original_attempt

    # Caller still holds the original (now stale) attempt_id.
    await orchestrator._set_last_stage(
        db_pool, job_id, original_attempt, "persist_utterances"
    )

    row = await read_job(db_pool, job_id)
    # CAS WHERE clause `AND attempt_id = $3` rejects the UPDATE: the
    # last_stage column is still NULL.
    assert row["last_stage"] is None
    # Row's attempt_id is whatever the rotation set, not what the stale
    # caller supplied.
    assert row["attempt_id"] == rotated


async def test_set_last_stage_swallows_db_failure(
    db_pool: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A DB failure inside the breadcrumb write must not tear down the
    pipeline. We force the failure by closing the pool before invoking
    the helper — the helper logs and returns normally so the caller
    can keep running its own cleanup."""
    import logging

    from src.jobs import orchestrator

    job_id, attempt = await insert_pending_job(db_pool)

    caplog.set_level(logging.WARNING, logger="src.jobs.orchestrator")
    await db_pool.close()

    # Helper must not raise even though the underlying pool is closed.
    await orchestrator._set_last_stage(
        db_pool, job_id, attempt, "persist_utterances"
    )

    assert any(
        "set_last_stage" in r.message for r in caplog.records
    ), [r.message for r in caplog.records]


# ---------------------------------------------------------------------------
# _increment_extract_transient_attempts — CAS-on-attempt_id with RETURNING.
# ---------------------------------------------------------------------------


async def test_increment_extract_transient_attempts_returns_new_count(
    db_pool: Any,
) -> None:
    """Real DB: counter increments from 0 -> 1 atomically; CAS hits
    because the supplied `task_attempt` matches the row's
    `attempt_id`. Returned value matches the post-increment column."""
    from src.jobs import orchestrator

    job_id, attempt = await insert_pending_job(db_pool)

    new_count = await orchestrator._increment_extract_transient_attempts(
        db_pool, job_id, task_attempt=attempt
    )

    assert new_count == 1
    row = await read_job(db_pool, job_id)
    assert row["extract_transient_attempts"] == 1


async def test_increment_extract_transient_attempts_no_op_on_rotated_attempt(
    db_pool: Any,
) -> None:
    """CAS-MISS (the gap that motivated the ticket): the row's
    `attempt_id` rotated under the caller; the increment helper
    returns None and the counter is NOT bumped.

    A regression that drops `AND attempt_id = $2` from
    `_INCREMENT_EXTRACT_TRANSIENT_SQL` would silently start
    double-counting across stale + fresh workers — the in-process
    `_IncrementCounterConn` fake could not catch this because it had
    no notion of `attempt_id` at all."""
    from src.jobs import orchestrator

    job_id, original_attempt = await insert_pending_job(db_pool)
    rotated = await _rotate_attempt_id(db_pool, job_id)
    assert rotated != original_attempt

    new_count = await orchestrator._increment_extract_transient_attempts(
        db_pool, job_id, task_attempt=original_attempt
    )

    assert new_count is None
    row = await read_job(db_pool, job_id)
    assert row["extract_transient_attempts"] == 0
    assert row["attempt_id"] == rotated


# ---------------------------------------------------------------------------
# _run_pipeline — extract-arm classification driven by real DB state.
# Migrated from tests/unit/test_orchestrator.py so the in-row backstop
# counter increments are observable as real column writes rather than
# a hand-rolled counter on a fake conn.
# ---------------------------------------------------------------------------


async def test_run_pipeline_translates_transient_extraction_error_to_transient(
    db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First TransientExtractionError increments the in-row counter to
    1 (below EXTRACT_TRANSIENT_MAX_ATTEMPTS=2) and surfaces as
    TransientError so `run_job`'s outer arm resets the row to pending
    and returns 503.

    Migrated from unit (TASK-1474.23.03.13 left TransientError without
    a structured payload — assertions are on raised type + observable
    DB state, not on prose substrings)."""
    from src.jobs import orchestrator
    from src.utterances.errors import TransientExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_transient(*args: Any, **kwargs: Any) -> Any:
        raise TransientExtractionError(
            provider="vertex",
            status_code=504,
            status="DEADLINE_EXCEEDED",
            fallback_message="Vertex 504",
        )

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_transient)

    job_id, attempt = await insert_pending_job(db_pool)

    with pytest.raises(orchestrator.TransientError):
        await orchestrator._run_pipeline(
            db_pool, job_id, attempt, "https://example.com", MagicMock()
        )

    # Single CAS-hit increment is observable on the row.
    row = await read_job(db_pool, job_id)
    assert row["extract_transient_attempts"] == 1
    assert row["attempt_id"] == attempt


async def test_run_pipeline_backstop_escalates_to_terminal_at_max(
    db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the in-row counter is already at MAX-1, the next
    TransientExtractionError pushes it to MAX and escalates to
    TerminalError(UPSTREAM_ERROR). Cloud Tasks would otherwise silently
    exhaust at max_attempts=3 and leave the row stuck pending.

    Asserts on `exc.error_code` + `exc.detail` keys (the structured
    payload introduced in TASK-1474.23.03.13), not substrings of the
    prose summary."""
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator
    from src.utterances.errors import TransientExtractionError

    _stub_extract_arm_only(monkeypatch)

    async def raise_transient(*args: Any, **kwargs: Any) -> Any:
        raise TransientExtractionError(
            provider="vertex",
            status_code=429,
            status="RESOURCE_EXHAUSTED",
            fallback_message="Vertex 429",
        )

    monkeypatch.setattr(orchestrator, "extract_utterances", raise_transient)

    job_id, attempt = await insert_pending_job(db_pool)
    # Pre-load the row's counter to (MAX - 1); the next increment hits MAX.
    await _seed_extract_transient_attempts(
        db_pool, job_id, orchestrator.EXTRACT_TRANSIENT_MAX_ATTEMPTS - 1
    )

    with pytest.raises(orchestrator.TerminalError) as info:
        await orchestrator._run_pipeline(
            db_pool, job_id, attempt, "https://example.com", MagicMock()
        )

    assert info.value.error_code == ErrorCode.UPSTREAM_ERROR
    assert info.value.detail["provider"] == "vertex"
    assert info.value.detail["status_code"] == 429
    assert info.value.detail["status"] == "RESOURCE_EXHAUSTED"
    assert (
        info.value.detail["transient_attempts"]
        == orchestrator.EXTRACT_TRANSIENT_MAX_ATTEMPTS
    )

    # CAS-hit increment landed exactly once on the row.
    row = await read_job(db_pool, job_id)
    assert (
        row["extract_transient_attempts"]
        == orchestrator.EXTRACT_TRANSIENT_MAX_ATTEMPTS
    )


# ---------------------------------------------------------------------------
# _mark_failed — error_host plumbing for UNSUPPORTED_SITE (TASK-1488.13).
# ---------------------------------------------------------------------------


async def test_mark_failed_writes_error_host_when_provided(
    db_pool: Any,
) -> None:
    """`_mark_failed(error_host="linkedin.com")` writes the value to
    `vibecheck_jobs.error_host` so the FE can render host-specific copy
    on UNSUPPORTED_SITE (TASK-1488.13)."""
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator

    job_id, attempt = await insert_pending_job(db_pool)

    await orchestrator._mark_failed(
        db_pool,
        job_id,
        task_attempt=attempt,
        error_code=ErrorCode.UNSUPPORTED_SITE,
        error_message="tier 1: …; tier 2: …",
        error_host="linkedin.com",
    )

    row = await read_job(db_pool, job_id)
    assert row["status"] == "failed"
    assert row["error_code"] == "unsupported_site"
    assert row["error_host"] == "linkedin.com"


async def test_mark_failed_leaves_error_host_unchanged_when_none(
    db_pool: Any,
) -> None:
    """`_mark_failed(error_host=None)` (legacy callers / non-UNSUPPORTED_SITE
    paths) does not clobber an existing `error_host`. The COALESCE(_, error_host)
    in `_MARK_FAILED_SQL` preserves prior writes."""
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator

    job_id, attempt = await insert_pending_job(db_pool)
    # Pre-populate error_host on the row (e.g. from an earlier UNSUPPORTED_SITE
    # write that this terminal call should not erase).
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET error_host = $1 WHERE job_id = $2",
            "preserved.example.com",
            job_id,
        )

    await orchestrator._mark_failed(
        db_pool,
        job_id,
        task_attempt=attempt,
        error_code=ErrorCode.EXTRACTION_FAILED,
        error_message="extraction failed",
    )

    row = await read_job(db_pool, job_id)
    assert row["error_code"] == "extraction_failed"
    assert row["error_host"] == "preserved.example.com"
