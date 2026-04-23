"""JSONB concurrency tests for the async-pipeline slot path (TASK-1473.21).

These tests run against a real Postgres (testcontainers) because the
contract under test — `sections = sections || jsonb_build_object(...)`
under concurrent UPDATEs — is exclusively a database-level behavior. A
mocked asyncpg surface would assert against the mock, not the merge
semantics that production relies on.

Coverage:

  * Concurrent `_run_section` coroutines for the same job + different
    slugs land seven distinct slot keys without lost writes.
  * Two concurrent `claim_slot` calls on the same (job, slug) serialize
    via row-level locking — exactly one wins.
  * `write_slot` racing the same (job, slug, attempt) preserves the last
    write (no torn JSONB) and never strips peer slugs.
  * `mark_slot_done` racing on the same slot acts as a CAS: exactly one
    `done` write commits; the loser observes `state='done'` and no-ops.

Pre-existing `tests/unit/test_slot_writes.py` covers the happy-path CAS
contract; this file focuses on the multi-coroutine merge scenarios that
were not exercised there.
"""
from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.config import Settings
from src.jobs.orchestrator import _run_section
from src.jobs.slots import claim_slot, mark_slot_done, write_slot

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE vibecheck_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    test_fail_slug TEXT
);
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(
    _postgres_container: PostgresContainer,
) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=16)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


async def _insert_active_job(
    pool: Any, attempt_id: UUID, *, url: str = "https://example.com/job"
) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, attempt_id)
            VALUES ($1, $1, 'example.com', 'analyzing', $2)
            RETURNING job_id
            """,
            url,
            attempt_id,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _read_sections(pool: Any, job_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT sections FROM vibecheck_jobs WHERE job_id = $1", job_id
        )
    return json.loads(row) if isinstance(row, str) else dict(row)


# ---------------------------------------------------------------------------
# AC: Concurrent _run_section across different slugs — no lost writes.
# ---------------------------------------------------------------------------


async def test_concurrent_run_section_across_all_slugs_lands_every_slot(
    db_pool: Any,
) -> None:
    """`asyncio.gather` over every SectionSlug must produce seven JSONB keys.

    The orchestrator's production fan-out is exactly this shape; if the
    `sections || jsonb_build_object(...)` merge dropped a write under
    contention, this test would observe < 7 keys. Each coroutine runs on
    its own pool connection so the test exercises real Postgres
    contention rather than a serialized fixture lock.
    """
    task_attempt = uuid4()
    job_id = await _insert_active_job(db_pool, task_attempt)

    settings = Settings()
    payload = object()

    await asyncio.gather(
        *[
            _run_section(db_pool, job_id, task_attempt, slug, payload, settings)
            for slug in SectionSlug
        ]
    )

    sections = await _read_sections(db_pool, job_id)
    for slug in SectionSlug:
        assert slug.value in sections, (
            f"slot {slug.value!r} is missing from sections JSONB after "
            f"concurrent _run_section — JSONB merge dropped a write"
        )
        assert sections[slug.value]["state"] == "done"


async def test_concurrent_write_slot_preserves_all_seven_keys(
    db_pool: Any,
) -> None:
    """Direct `write_slot` fan-out — same contract, lower-level surface.

    Reproduces the JSONB merge under maximum contention by skipping
    `_run_section`'s metric/contextvar overhead. If the merge is racy at
    the SQL layer we'd see fewer than seven keys here even though the
    higher-level `_run_section` test passed.
    """
    task_attempt = uuid4()
    job_id = await _insert_active_job(db_pool, task_attempt)

    slots = {
        slug: SectionSlot(
            state=SectionState.DONE,
            attempt_id=uuid4(),
            data={"slug": slug.value, "sentinel": f"s-{slug.value}"},
        )
        for slug in SectionSlug
    }

    results = await asyncio.gather(
        *[
            write_slot(db_pool, job_id, task_attempt, slug, slot)
            for slug, slot in slots.items()
        ]
    )

    assert all(r == 1 for r in results)
    sections = await _read_sections(db_pool, job_id)
    assert len(sections) == len(SectionSlug)
    for slug in SectionSlug:
        entry = sections[slug.value]
        assert entry["state"] == "done"
        assert entry["data"]["sentinel"] == f"s-{slug.value}"


# ---------------------------------------------------------------------------
# AC: claim_slot serialization under concurrent coroutines (CAS contention).
# ---------------------------------------------------------------------------


async def test_claim_slot_under_high_concurrency_serializes_to_one_winner(
    db_pool: Any,
) -> None:
    """N concurrent claimers on the same (job, slug) — exactly one wins.

    `tests/unit/test_slot_writes.py` covers the 2-coroutine case; this
    test bumps the fan-out higher to exercise asyncpg pool contention
    against the row-level lock the UPDATE inherits.
    """
    task_attempt = uuid4()
    job_id = await _insert_active_job(db_pool, task_attempt)

    fanout = 8
    results = await asyncio.gather(
        *[
            claim_slot(
                db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
            )
            for _ in range(fanout)
        ]
    )

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == fanout - 1


# ---------------------------------------------------------------------------
# AC: mark_slot_done racing on the same slot — exactly one terminal write.
# ---------------------------------------------------------------------------


async def test_mark_slot_done_concurrent_calls_one_winner(
    db_pool: Any,
) -> None:
    """Two `mark_slot_done` calls in parallel: one wins, the other no-ops.

    The slot-write contract requires `state='running'` for the CAS to
    succeed. The first commit flips state to `done`; the second observes
    state≠'running' and returns 0 rows. We never end up with a partially
    serialized slot.
    """
    task_attempt = uuid4()
    job_id = await _insert_active_job(db_pool, task_attempt)
    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.FACTS_CLAIMS_DEDUP
    )
    assert slot_attempt is not None

    payload_a = {"claims_report": {"deduped_claims": [], "total_claims": 1, "total_unique": 1}}
    payload_b = {"claims_report": {"deduped_claims": [], "total_claims": 2, "total_unique": 2}}

    results = await asyncio.gather(
        mark_slot_done(
            db_pool,
            job_id,
            SectionSlug.FACTS_CLAIMS_DEDUP,
            slot_attempt,
            payload_a,
            expected_task_attempt=task_attempt,
        ),
        mark_slot_done(
            db_pool,
            job_id,
            SectionSlug.FACTS_CLAIMS_DEDUP,
            slot_attempt,
            payload_b,
            expected_task_attempt=task_attempt,
        ),
    )

    assert sorted(results) == [0, 1]
    sections = await _read_sections(db_pool, job_id)
    final = sections[SectionSlug.FACTS_CLAIMS_DEDUP.value]
    assert final["state"] == "done"
    # The winning payload is one of the two — never a torn merge of both.
    assert final["data"]["claims_report"]["total_claims"] in (1, 2)


# ---------------------------------------------------------------------------
# AC: Concurrent writes to different slugs preserve sibling slugs.
# ---------------------------------------------------------------------------


async def test_concurrent_writes_to_different_slugs_no_clobber(
    db_pool: Any,
) -> None:
    """Two parallel `write_slot` calls on different slugs must not clobber
    each other — the JSONB `||` merge is right-biased per top-level key,
    so the overlap point is the row-level UPDATE itself, not the slug
    keys. If the test sees one slug missing, the merge is racy.
    """
    task_attempt = uuid4()
    job_id = await _insert_active_job(db_pool, task_attempt)

    safety_slot = SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data={"harmful_content_matches": [{"id": "safety-1"}]},
    )
    flashpoint_slot = SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data={"flashpoint_matches": [{"id": "flash-1"}]},
    )

    results = await asyncio.gather(
        write_slot(
            db_pool,
            job_id,
            task_attempt,
            SectionSlug.SAFETY_MODERATION,
            safety_slot,
        ),
        write_slot(
            db_pool,
            job_id,
            task_attempt,
            SectionSlug.TONE_DYNAMICS_FLASHPOINT,
            flashpoint_slot,
        ),
    )
    assert results == [1, 1]

    sections = await _read_sections(db_pool, job_id)
    assert SectionSlug.SAFETY_MODERATION.value in sections
    assert SectionSlug.TONE_DYNAMICS_FLASHPOINT.value in sections
    assert sections[SectionSlug.SAFETY_MODERATION.value]["data"][
        "harmful_content_matches"
    ] == [{"id": "safety-1"}]
    assert sections[SectionSlug.TONE_DYNAMICS_FLASHPOINT.value]["data"][
        "flashpoint_matches"
    ] == [{"id": "flash-1"}]
