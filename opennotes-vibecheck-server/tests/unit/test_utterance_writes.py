"""Integration tests for persist_utterances helper (TASK-1473.57).

Runs against real Postgres (testcontainers) — the DELETE+INSERT transaction
and FOR UPDATE lock semantics are the heart of what we're testing.
"""
from __future__ import annotations

import socket
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.schemas import PageKind
from src.jobs.utterance_writes import UtterancePersistenceSuperseded, persist_utterances
from src.utterances.schema import Utterance, UtterancesPayload
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
"""
    + VIBECHECK_JOBS_DDL
    + """
CREATE TABLE vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    page_title TEXT,
    page_kind TEXT NOT NULL DEFAULT 'other',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
)


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[Any]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: Any) -> Any:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_job_utterances CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


async def _insert_job(pool: Any, attempt_id: UUID) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, attempt_id)
            VALUES ('https://example.com/a', 'https://example.com/a', 'example.com', 'extracting', $1)
            RETURNING job_id
            """,
            attempt_id,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _count_utterances(pool: Any, job_id: UUID) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_job_utterances WHERE job_id = $1",
            job_id,
        )


async def _fetch_utterances(pool: Any, job_id: UUID) -> list[Any]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM vibecheck_job_utterances WHERE job_id = $1 ORDER BY position",
            job_id,
        )


def _make_payload(
    utterances: list[Utterance],
    page_title: str | None = "Test Page",
    page_kind: PageKind = PageKind.FORUM_THREAD,
) -> UtterancesPayload:
    return UtterancesPayload(
        source_url="https://example.com/a",
        scraped_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        utterances=utterances,
        page_title=page_title,
        page_kind=page_kind,
    )


def _make_utterances(n: int) -> list[Utterance]:
    return [
        Utterance(
            utterance_id=f"uid-{i}",
            kind="comment",
            text=f"message {i}",
            author=f"user{i}",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            parent_id=None,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Happy path — N rows land with correct position ordering.
# ---------------------------------------------------------------------------


async def test_persist_utterances_happy_path(db_pool: Any) -> None:
    attempt_id = uuid4()
    job_id = await _insert_job(db_pool, attempt_id)
    utterances = _make_utterances(3)
    payload = _make_payload(utterances)

    await persist_utterances(db_pool, job_id, attempt_id, payload)

    rows = await _fetch_utterances(db_pool, job_id)
    assert len(rows) == 3
    for idx, row in enumerate(rows):
        assert row["position"] == idx
        assert row["kind"] == "comment"
        assert row["text"] == f"message {idx}"
        assert row["utterance_id"] == f"uid-{idx}"


# ---------------------------------------------------------------------------
# Retry-from-zero shorter list — DELETE-before-INSERT ensures only M rows.
# ---------------------------------------------------------------------------


async def test_persist_utterances_shorter_list_replaces(db_pool: Any) -> None:
    attempt_id = uuid4()
    job_id = await _insert_job(db_pool, attempt_id)

    payload_5 = _make_payload(_make_utterances(5))
    await persist_utterances(db_pool, job_id, attempt_id, payload_5)
    assert await _count_utterances(db_pool, job_id) == 5

    payload_2 = _make_payload(_make_utterances(2))
    await persist_utterances(db_pool, job_id, attempt_id, payload_2)
    assert await _count_utterances(db_pool, job_id) == 2


# ---------------------------------------------------------------------------
# Attempt drift raises UtterancePersistenceSuperseded, no rows written.
# ---------------------------------------------------------------------------


async def test_persist_utterances_attempt_drift_raises(db_pool: Any) -> None:
    actual_attempt = uuid4()
    wrong_attempt = uuid4()
    job_id = await _insert_job(db_pool, actual_attempt)
    payload = _make_payload(_make_utterances(2))

    with pytest.raises(UtterancePersistenceSuperseded, match="attempt drift"):
        await persist_utterances(db_pool, job_id, wrong_attempt, payload)

    assert await _count_utterances(db_pool, job_id) == 0


# ---------------------------------------------------------------------------
# Job not found raises UtterancePersistenceSuperseded, no rows written.
# ---------------------------------------------------------------------------


async def test_persist_utterances_job_not_found_raises(db_pool: Any) -> None:
    missing_job_id = uuid4()
    attempt_id = uuid4()
    payload = _make_payload(_make_utterances(1))

    with pytest.raises(UtterancePersistenceSuperseded, match="not found"):
        await persist_utterances(db_pool, missing_job_id, attempt_id, payload)


# ---------------------------------------------------------------------------
# Page metadata — every inserted row carries same page_title and page_kind.
# ---------------------------------------------------------------------------


async def test_persist_utterances_page_metadata_per_row(db_pool: Any) -> None:
    attempt_id = uuid4()
    job_id = await _insert_job(db_pool, attempt_id)
    payload = _make_payload(
        _make_utterances(3),
        page_title="My Forum Thread",
        page_kind=PageKind.HIERARCHICAL_THREAD,
    )

    await persist_utterances(db_pool, job_id, attempt_id, payload)

    rows = await _fetch_utterances(db_pool, job_id)
    assert len(rows) == 3
    for row in rows:
        assert row["page_title"] == "My Forum Thread"
        assert row["page_kind"] == PageKind.HIERARCHICAL_THREAD.value
