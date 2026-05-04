"""Poll endpoint metadata correctness tests (TASK-1473.60).

Exercises the LATERAL JOIN rewrite in _SELECT_JOB_SQL:

  1. Empty utterances  -> page_title and page_kind are NULL in poll row.
  2. Seeded utterances -> poll row carries the exact values written.
  3. Multiple rows with differing page_title -> position=0 row wins
     deterministically (ORDER BY u.position LIMIT 1 contract).

These run against a real Postgres (testcontainers) since the LATERAL
syntax and ORDER BY LIMIT 1 behaviour must be validated against an actual
query planner, not mocked SQL.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from src.routes.analyze import _SELECT_JOB_SQL, _host_of, _row_to_job_state

from .conftest import insert_pending_job


async def _insert_utterance(
    pool: Any,
    *,
    job_id: UUID,
    position: int,
    page_title: str | None,
    page_kind: str | None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_job_utterances
                (job_id, kind, text, position, page_title, page_kind)
            VALUES ($1, 'post', 'dummy text', $2, $3, $4)
            """,
            job_id,
            position,
            page_title,
            page_kind,
        )


async def _fetch_poll_row(pool: Any, job_id: UUID) -> asyncpg.Record:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_JOB_SQL, job_id)
    assert row is not None
    return row


def _mock_poll_row(
    *,
    status: str,
    source_type: str | None = "url",
) -> dict[str, object]:
    now = datetime.now(UTC)
    job_id = uuid4()
    row = {
        "job_id": job_id,
        "url": "https://example.com/poll-row",
        "status": status,
        "attempt_id": uuid4(),
        "error_code": None,
        "error_message": None,
        "error_host": None,
        "sections": {},
        "sidebar_payload": None,
        "cached": False,
        "created_at": now,
        "updated_at": now,
        "safety_recommendation": None,
        "headline_summary": None,
        "last_stage": None,
        "heartbeat_at": None,
        "source_type": source_type,
        "page_title": None,
        "page_kind": None,
        "utterance_count": 0,
    }
    if source_type is None:
        row.pop("source_type")
    return row


def test_host_of_ignores_pdf_source_type() -> None:
    assert _host_of("not-a-url", source_type="pdf") == ""


def test_row_to_job_state_maps_pdf_source_and_archive_url() -> None:
    row = _mock_poll_row(status="pending", source_type="pdf")
    job = _row_to_job_state(row)
    assert job.source_type == "pdf"
    assert job.pdf_archive_url == (
        f"/api/archive-preview?job_id={row['job_id']}&source_type=pdf"
    )


def test_row_to_job_state_defaults_url_for_missing_source_type() -> None:
    row = _mock_poll_row(status="pending", source_type=None)
    job = _row_to_job_state(row)
    assert job.source_type == "url"
    assert job.pdf_archive_url is None


async def test_empty_utterances_gives_null_metadata(db_pool: Any) -> None:
    """A job with no utterance rows must surface NULL page_title / page_kind."""
    job_id, _ = await insert_pending_job(
        db_pool, url="https://example.com/poll-empty"
    )

    row = await _fetch_poll_row(db_pool, job_id)

    assert row["page_title"] is None
    assert row["page_kind"] is None
    assert int(row["utterance_count"]) == 0


async def test_seeded_utterances_give_correct_metadata(db_pool: Any) -> None:
    """A job with one utterance row surfaces its page_title and page_kind."""
    job_id, _ = await insert_pending_job(
        db_pool, url="https://example.com/poll-seeded"
    )
    await _insert_utterance(
        db_pool,
        job_id=job_id,
        position=0,
        page_title="Fresh Title",
        page_kind="blog_post",
    )

    row = await _fetch_poll_row(db_pool, job_id)

    assert row["page_title"] == "Fresh Title"
    assert row["page_kind"] == "blog_post"
    assert int(row["utterance_count"]) == 1


async def test_multiple_rows_position_zero_wins(db_pool: Any) -> None:
    """When multiple utterance rows exist, position=0 row wins (ORDER BY
    position LIMIT 1). This documents the deterministic-winner contract.
    """
    job_id, _ = await insert_pending_job(
        db_pool, url="https://example.com/poll-multi"
    )
    await _insert_utterance(
        db_pool,
        job_id=job_id,
        position=0,
        page_title="First Title",
        page_kind="article",
    )
    await _insert_utterance(
        db_pool,
        job_id=job_id,
        position=1,
        page_title="Second Title",
        page_kind="blog_post",
    )

    row = await _fetch_poll_row(db_pool, job_id)

    assert row["page_title"] == "First Title"
    assert row["page_kind"] == "article"
    assert int(row["utterance_count"]) == 2
