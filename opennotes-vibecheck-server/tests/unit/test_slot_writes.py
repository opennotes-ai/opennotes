"""Integration tests for slot write-contract helpers (TASK-1473.09).

These tests run against a real Postgres instance (via testcontainers) because
the contracts under test — optimistic CAS updates, concurrent claim arbitration,
advisory-lock-guarded finalization — are inherently database-level behaviors
that cannot be faithfully simulated with mocks.
"""
from __future__ import annotations

import asyncio
import json
import socket
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.jobs.finalize import maybe_finalize_job
from src.jobs.slots import (
    claim_slot,
    mark_slot_done,
    mark_slot_failed,
    write_slot,
)

# Capture the real resolver before the suite-wide autouse `_stub_dns` fixture
# in tests/conftest.py patches it at test setup time.
_REAL_GETADDRINFO = socket.getaddrinfo


# --- Container + schema bootstrapping --------------------------------------

# src/cache/schema.sql depends on pg_cron / uuid-ossp which aren't both
# present in vanilla Postgres images. For unit tests we install just the core
# DDL we exercise. If new columns land in schema.sql, mirror them here.
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
    finished_at TIMESTAMPTZ
);
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite-wide autouse `_stub_dns` fixture in tests/conftest.py pins
    # every hostname lookup to 8.8.8.8 for SSRF tests. Testcontainers needs
    # real localhost resolution to reach the Postgres it just booted, so we
    # undo the stub for this module.
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container) -> Any:
    # Build asyncpg DSN from the container's driver-shaped URL.
    raw = _postgres_container.get_connection_url()
    # testcontainers returns e.g. postgresql+psycopg2://... — strip driver suffix.
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None

    async with pool.acquire() as conn:
        # Fresh schema per test keeps behavior checks independent.
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)

    try:
        yield pool
    finally:
        await pool.close()


async def _insert_job(pool: Any, attempt_id: UUID, url: str = "https://example.com/a") -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, attempt_id)
            VALUES ($1, $2, $3, 'analyzing', $4)
            RETURNING job_id
            """,
            url,
            url,
            "example.com",
            attempt_id,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _read_sections(pool: Any, job_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT sections FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    return json.loads(row) if isinstance(row, str) else dict(row)


# --- claim_slot ------------------------------------------------------------


async def test_claim_slot_returns_attempt_id_for_fresh_slot(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )

    assert isinstance(slot_attempt, UUID)
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.SAFETY_MODERATION.value]["state"] == "running"
    assert sections[SectionSlug.SAFETY_MODERATION.value]["attempt_id"] == str(slot_attempt)


async def test_claim_slot_rejects_stale_task_attempt(db_pool) -> None:
    current_attempt = uuid4()
    stale_attempt = uuid4()
    job_id = await _insert_job(db_pool, current_attempt)

    slot_attempt = await claim_slot(
        db_pool, job_id, stale_attempt, SectionSlug.SAFETY_MODERATION
    )

    assert slot_attempt is None
    sections = await _read_sections(db_pool, job_id)
    assert SectionSlug.SAFETY_MODERATION.value not in sections


async def test_claim_slot_returns_none_if_already_running(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    first = await claim_slot(db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD)
    second = await claim_slot(db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD)

    assert first is not None
    assert second is None


async def test_claim_slot_is_atomic_under_concurrency(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    # Two concurrent claimers on the same slot, each using its own connection.
    results = await asyncio.gather(
        claim_slot(db_pool, job_id, task_attempt, SectionSlug.FACTS_CLAIMS_DEDUP),
        claim_slot(db_pool, job_id, task_attempt, SectionSlug.FACTS_CLAIMS_DEDUP),
    )

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1


async def test_claim_slot_permits_reclaim_after_failed(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    first_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE
    )
    assert first_attempt is not None
    rows = await mark_slot_failed(
        db_pool,
        job_id,
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE,
        first_attempt,
        "boom",
        expected_task_attempt=task_attempt,
    )
    assert rows == 1

    second_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE
    )

    assert isinstance(second_attempt, UUID)
    assert second_attempt != first_attempt


# --- mark_slot_done / mark_slot_failed CAS ---------------------------------


async def test_mark_slot_done_fails_on_stale_slot_attempt(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    live_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_FLASHPOINT
    )
    assert live_attempt is not None

    stale_attempt = uuid4()
    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        stale_attempt,
        {"flashpoint_matches": []},
        expected_task_attempt=task_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.TONE_DYNAMICS_FLASHPOINT.value]["state"] == "running"


async def test_mark_slot_done_writes_payload_when_attempt_matches(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )
    assert slot_attempt is not None

    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        slot_attempt,
        {"harmful_content_matches": []},
        expected_task_attempt=task_attempt,
    )

    assert rows == 1
    sections = await _read_sections(db_pool, job_id)
    entry = sections[SectionSlug.SAFETY_MODERATION.value]
    assert entry["state"] == "done"
    assert entry["data"] == {"harmful_content_matches": []}
    assert entry["finished_at"] is not None


# --- Terminal CAS guards (P1.3): task_attempt + status + prior slot state --


async def test_mark_slot_done_fails_when_job_task_attempt_has_rotated(db_pool) -> None:
    """A superseded job attempt must not accept terminal slot writes.

    Scenario: worker A claims the slot; before A finishes, the job was
    retried, rotating `attempt_id`. A's late `mark_slot_done` must no-op
    even though A still holds the matching `slot_attempt_id` — otherwise a
    stale worker can mutate a fresh attempt's cache.
    """
    initial_attempt = uuid4()
    job_id = await _insert_job(db_pool, initial_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, initial_attempt, SectionSlug.TONE_DYNAMICS_FLASHPOINT
    )
    assert live_slot is not None

    # Simulate a retry rotating the job-level attempt_id.
    rotated_attempt = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET attempt_id = $2 WHERE job_id = $1",
            job_id,
            rotated_attempt,
        )

    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        live_slot,
        {"flashpoint_matches": []},
        expected_task_attempt=initial_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    # Slot must still be running — the stale worker did not clobber it.
    assert sections[SectionSlug.TONE_DYNAMICS_FLASHPOINT.value]["state"] == "running"


async def test_mark_slot_done_fails_when_slot_state_is_not_running(db_pool) -> None:
    """Once a slot reaches a terminal state, re-delivered done writes no-op."""
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )
    assert live_slot is not None

    first = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        live_slot,
        {"harmful_content_matches": []},
        expected_task_attempt=task_attempt,
    )
    assert first == 1

    second = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        live_slot,
        {"harmful_content_matches": [{"spurious": "write"}]},
        expected_task_attempt=task_attempt,
    )

    assert second == 0
    sections = await _read_sections(db_pool, job_id)
    # Original done payload wins — the second (stale) write did not clobber.
    assert sections[SectionSlug.SAFETY_MODERATION.value]["data"] == {
        "harmful_content_matches": []
    }


async def test_mark_slot_done_fails_when_job_status_is_terminal(db_pool) -> None:
    """A job that flipped to failed/done must reject further slot terminal writes."""
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD
    )
    assert live_slot is not None

    # Sweeper (or explicit error path) transitions the job to failed.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'failed' WHERE job_id = $1",
            job_id,
        )

    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.TONE_DYNAMICS_SCD,
        live_slot,
        {"scd": {"summary": "late"}},
        expected_task_attempt=task_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.TONE_DYNAMICS_SCD.value]["state"] == "running"


async def test_mark_slot_failed_fails_when_job_task_attempt_has_rotated(db_pool) -> None:
    """mark_slot_failed must enforce the same CAS envelope as mark_slot_done."""
    initial_attempt = uuid4()
    job_id = await _insert_job(db_pool, initial_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, initial_attempt, SectionSlug.FACTS_CLAIMS_DEDUP
    )
    assert live_slot is not None

    rotated_attempt = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET attempt_id = $2 WHERE job_id = $1",
            job_id,
            rotated_attempt,
        )

    rows = await mark_slot_failed(
        db_pool,
        job_id,
        SectionSlug.FACTS_CLAIMS_DEDUP,
        live_slot,
        "boom",
        expected_task_attempt=initial_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.FACTS_CLAIMS_DEDUP.value]["state"] == "running"


# --- write_slot (generic contract) -----------------------------------------


async def test_write_slot_merges_sections_without_clobbering_siblings(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    slot_a = SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data={"a": 1},
    )
    slot_b = SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data={"b": 2},
    )

    rows_a = await write_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION, slot_a
    )
    rows_b = await write_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD, slot_b
    )

    assert rows_a == 1
    assert rows_b == 1
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.SAFETY_MODERATION.value]["data"] == {"a": 1}
    assert sections[SectionSlug.TONE_DYNAMICS_SCD.value]["data"] == {"b": 2}


async def test_slot_data_roundtrips_uuid_and_datetime(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    slot_attempt = uuid4()
    started = datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 22, 12, 0, 5, tzinfo=UTC)
    slot = SectionSlot(
        state=SectionState.DONE,
        attempt_id=slot_attempt,
        data={"scd": {"id": str(uuid4()), "ts": started.isoformat()}},
        started_at=started,
        finished_at=finished,
    )

    rows = await write_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD, slot
    )

    assert rows == 1
    sections = await _read_sections(db_pool, job_id)
    entry = sections[SectionSlug.TONE_DYNAMICS_SCD.value]
    assert entry["attempt_id"] == str(slot_attempt)
    assert entry["started_at"] == started.isoformat().replace("+00:00", "Z") or entry[
        "started_at"
    ] == started.isoformat()
    # Crucially, we can re-parse back into SectionSlot without a type error.
    rebuilt = SectionSlot.model_validate(entry)
    assert rebuilt.attempt_id == slot_attempt
    assert rebuilt.started_at == started
    assert rebuilt.finished_at == finished


# --- maybe_finalize_job ----------------------------------------------------


_ALL_SLUGS = list(SectionSlug)


def _done_slot(data: dict[str, Any]) -> SectionSlot:
    return SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data=data,
        started_at=datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 22, 12, 0, 1, tzinfo=UTC),
    )


def _minimal_slot_payloads() -> dict[SectionSlug, dict[str, Any]]:
    # Each payload matches the slot-level contract `maybe_finalize_job` expects:
    # slot.data is the fragment that contributes to its destination section in
    # `SidebarPayload`.
    return {
        SectionSlug.SAFETY_MODERATION: {"harmful_content_matches": []},
        SectionSlug.TONE_DYNAMICS_FLASHPOINT: {"flashpoint_matches": []},
        SectionSlug.TONE_DYNAMICS_SCD: {
            "scd": {
                "summary": "A neutral exchange.",
                "tone_labels": [],
                "per_speaker_notes": {},
                "insufficient_conversation": True,
            }
        },
        SectionSlug.FACTS_CLAIMS_DEDUP: {
            "claims_report": {
                "deduped_claims": [],
                "total_claims": 0,
                "total_unique": 0,
            }
        },
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: {"known_misinformation": []},
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: {
            "sentiment_stats": {
                "per_utterance": [],
                "positive_pct": 0.0,
                "negative_pct": 0.0,
                "neutral_pct": 100.0,
                "mean_valence": 0.0,
            }
        },
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: {"subjective_claims": []},
    }


async def _seed_slots(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    slugs: list[SectionSlug],
) -> None:
    payloads = _minimal_slot_payloads()
    for slug in slugs:
        slot = _done_slot(payloads[slug])
        rows = await write_slot(pool, job_id, task_attempt, slug, slot)
        assert rows == 1


async def test_maybe_finalize_job_waits_for_all_seven_slots(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    # 6 of 7 done.
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS[:-1])

    finalized = await maybe_finalize_job(db_pool, job_id)

    assert finalized is False
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval("SELECT COUNT(*) FROM vibecheck_analyses")
    assert rowcount == 0


async def test_maybe_finalize_job_upserts_cache_when_all_slots_done(db_pool) -> None:
    task_attempt = uuid4()
    url = "https://example.com/full"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    finalized = await maybe_finalize_job(db_pool, job_id)

    assert finalized is True
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT url, sidebar_payload, expires_at FROM vibecheck_analyses WHERE url = $1",
            url,
        )
    assert row is not None
    assert row["url"] == url
    payload = json.loads(row["sidebar_payload"]) if isinstance(
        row["sidebar_payload"], str
    ) else dict(row["sidebar_payload"])
    assert payload["source_url"] == url
    assert "safety" in payload
    assert "tone_dynamics" in payload
    assert "facts_claims" in payload
    assert "opinions_sentiments" in payload


async def test_maybe_finalize_job_is_idempotent_on_repeat_call(db_pool) -> None:
    task_attempt = uuid4()
    url = "https://example.com/idempotent"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    first = await maybe_finalize_job(db_pool, job_id)
    second = await maybe_finalize_job(db_pool, job_id)

    assert first is True
    assert second is True
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
    assert rowcount == 1
