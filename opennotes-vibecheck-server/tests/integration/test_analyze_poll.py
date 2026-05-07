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

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
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
) -> dict[str, Any]:
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


def _weather_report_dict() -> dict[str, Any]:
    return {
        "truth": {
            "label": "sourced",
            "alternatives": [{"label": "mostly_factual", "logprob": 0.05}],
            "logprob": 0.82,
        },
        "relevance": {
            "label": "insightful",
            "alternatives": [{"label": "on_topic", "logprob": 0.1}],
            "logprob": 0.76,
        },
        "sentiment": {
            "label": "supportive",
            "alternatives": [{"label": "positive", "logprob": 0.18}],
            "logprob": 0.93,
        },
    }


def test_host_of_ignores_pdf_source_type() -> None:
    assert _host_of("not-a-url", source_type="pdf") == ""


def test_row_to_job_state_maps_pdf_source_and_archive_url() -> None:
    # Non-terminal PDF jobs must NOT expose pdf_archive_url; the URL is only
    # safe to publish once the archive is persisted (terminal status).
    pending_row = _mock_poll_row(status="pending", source_type="pdf")
    pending_job = _row_to_job_state(pending_row)
    assert pending_job.source_type == "pdf"
    assert pending_job.pdf_archive_url is None

    done_row = _mock_poll_row(status="done", source_type="pdf")
    done_job = _row_to_job_state(done_row)
    assert done_job.source_type == "pdf"
    assert done_job.pdf_archive_url == (
        f"/api/archive-preview?job_id={done_row['job_id']}&source_type=pdf"
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


async def test_non_terminal_poll_includes_weather_report_in_sidebar_payload(
    db_pool: Any,
) -> None:
    job_id, _ = await insert_pending_job(
        db_pool,
        url="https://example.com/poll-weather",
    )
    sections = {
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value: SectionSlot(
            state=SectionState.DONE,
            attempt_id=uuid4(),
            data={
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                },
                "subjective_claims": [],
            },
        ).model_dump(mode="json")
    }

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET status = 'analyzing',
                sections = $2::jsonb,
                weather_report = $3::jsonb
            WHERE job_id = $1
            """,
            job_id,
            json.dumps(sections),
            json.dumps(_weather_report_dict()),
        )

    row = await _fetch_poll_row(db_pool, job_id)
    job = _row_to_job_state(row)

    assert job.status.value == "analyzing"
    assert job.sidebar_payload is not None
    assert job.sidebar_payload.weather_report is not None
    assert job.sidebar_payload.weather_report.truth.label == "sourced"
    assert job.sidebar_payload_complete is False
