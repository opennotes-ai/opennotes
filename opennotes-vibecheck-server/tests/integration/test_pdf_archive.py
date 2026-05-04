"""Integration tests for the vibecheck_pdf_archives table (TASK-1498.22).

The pdf_extract_step writes raw HTML into vibecheck_pdf_archives keyed by
job_id, and frame.py's _get_pdf_gcs_key reads back through a join on the
same row to resolve the durable GCS key for the archive-preview route.

These paths were previously untested at the integration level because the
INTEGRATION_DDL fixture omitted the vibecheck_pdf_archives table — every
write would have raised UndefinedTableError against the testcontainers
Postgres. This module exercises the round-trip end-to-end with a real
asyncpg pool so the table contract (PK on job_id, FK cascade from
vibecheck_jobs, default 7-day expires_at, ON CONFLICT upsert) is covered.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from src.jobs.pdf_extract import _store_pdf_archive
from src.routes.frame import _get_pdf_gcs_key


async def _insert_pdf_job(
    pool: Any, *, gcs_key: str = "gs://bucket/path/file.pdf"
) -> UUID:
    """Insert a job with source_type='pdf' and normalized_url set to the GCS key.

    frame.py's _SELECT_PDF_JOB_SQL returns `j.normalized_url AS gcs_key`, so
    that's what _get_pdf_gcs_key actually round-trips.
    """
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, source_type
            )
            VALUES ($1, $1, 'pdf-upload', 'pending', 'pdf')
            RETURNING job_id
            """,
            gcs_key,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def test_store_pdf_archive_inserts_row_with_seven_day_ttl(
    db_pool: Any,
) -> None:
    """_store_pdf_archive writes a row keyed by job_id with ~7d expires_at."""
    job_id = await _insert_pdf_job(db_pool)
    html = "<article>persisted PDF body</article>"

    before = datetime.now(UTC)
    await _store_pdf_archive(db_pool, job_id, html)
    after = datetime.now(UTC)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT job_id, html, created_at, expires_at
            FROM vibecheck_pdf_archives
            WHERE job_id = $1
            """,
            job_id,
        )
    assert row is not None
    assert row["job_id"] == job_id
    assert row["html"] == html
    expected_min = before + timedelta(days=7) - timedelta(seconds=5)
    expected_max = after + timedelta(days=7) + timedelta(seconds=5)
    assert expected_min <= row["expires_at"] <= expected_max


async def test_store_pdf_archive_upsert_replaces_html(db_pool: Any) -> None:
    """A second _store_pdf_archive call for the same job_id overwrites html."""
    job_id = await _insert_pdf_job(db_pool)

    await _store_pdf_archive(db_pool, job_id, "<article>first</article>")
    await _store_pdf_archive(db_pool, job_id, "<article>second</article>")

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT html FROM vibecheck_pdf_archives WHERE job_id = $1",
            job_id,
        )
    assert len(rows) == 1
    assert rows[0]["html"] == "<article>second</article>"


async def test_get_pdf_gcs_key_returns_key_for_persisted_archive(
    db_pool: Any,
) -> None:
    """After _store_pdf_archive, _get_pdf_gcs_key surfaces the durable GCS key."""
    gcs_key = "gs://bucket/uploads/abc123.pdf"
    job_id = await _insert_pdf_job(db_pool, gcs_key=gcs_key)
    await _store_pdf_archive(db_pool, job_id, "<article>body</article>")

    result = await _get_pdf_gcs_key(db_pool, job_id)

    assert result == gcs_key


async def test_get_pdf_gcs_key_returns_none_when_archive_missing(
    db_pool: Any,
) -> None:
    """Without a vibecheck_pdf_archives row, the join filters the job out."""
    job_id = await _insert_pdf_job(db_pool)

    result = await _get_pdf_gcs_key(db_pool, job_id)

    assert result is None


async def test_get_pdf_gcs_key_returns_none_when_archive_expired(
    db_pool: Any,
) -> None:
    """Expired archive rows are filtered by the `expires_at > now()` predicate."""
    job_id = await _insert_pdf_job(db_pool)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_pdf_archives (job_id, html, expires_at)
            VALUES ($1, $2, now() - INTERVAL '1 hour')
            """,
            job_id,
            "<article>stale</article>",
        )

    result = await _get_pdf_gcs_key(db_pool, job_id)

    assert result is None


async def test_pdf_archive_cascade_delete_with_job(db_pool: Any) -> None:
    """Deleting the parent job cascades to vibecheck_pdf_archives (FK)."""
    job_id = await _insert_pdf_job(db_pool)
    await _store_pdf_archive(db_pool, job_id, "<article>body</article>")

    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM vibecheck_jobs WHERE job_id = $1", job_id
        )
        remaining = await conn.fetchval(
            "SELECT count(*) FROM vibecheck_pdf_archives WHERE job_id = $1",
            job_id,
        )
    assert remaining == 0
