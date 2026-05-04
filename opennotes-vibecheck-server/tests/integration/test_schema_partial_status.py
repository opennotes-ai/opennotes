"""Integration tests for TASK-1529: ALTER TABLE constraint sync for status='partial'.

Simulates the pre-1474.29 production state (vibecheck_jobs_status_check and
vibecheck_jobs_terminal_finished_at constraints without 'partial') and verifies
that applying schema.sql fixes them so finalize.py can write status='partial'
without CheckViolationError.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

SCHEMA_PATH = Path(__file__).parents[2] / "src" / "cache" / "schema.sql"

PG_CRON_SHIM = """
CREATE SCHEMA IF NOT EXISTS cron;
CREATE TABLE IF NOT EXISTS cron.job (
    jobname text PRIMARY KEY,
    schedule text NOT NULL,
    command text NOT NULL
);
CREATE OR REPLACE FUNCTION cron.unschedule(p_jobname text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM cron.job WHERE cron.job.jobname = p_jobname;
END;
$$;
CREATE OR REPLACE FUNCTION cron.schedule(p_jobname text, p_schedule text, p_command text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO cron.job(jobname, schedule, command)
    VALUES (p_jobname, p_schedule, p_command)
    ON CONFLICT (jobname) DO UPDATE SET schedule = p_schedule, command = p_command;
END;
$$;
"""

CREATE_POSTGRES_ROLE_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
        CREATE ROLE postgres SUPERUSER LOGIN;
    END IF;
END
$$;
"""

PRE_1474_29_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS public.vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS public.vibecheck_jobs (
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
    source_type TEXT NOT NULL DEFAULT 'url',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    test_fail_slug TEXT,
    safety_recommendation JSONB,
    headline_summary JSONB,
    last_stage TEXT,
    preview_description TEXT,
    extract_transient_attempts INT NOT NULL DEFAULT 0,
    CONSTRAINT vibecheck_jobs_status_check
        CHECK (status IN ('pending', 'extracting', 'analyzing', 'done', 'failed')),
    CONSTRAINT vibecheck_jobs_error_code_check
        CHECK (
            error_code IS NULL
            OR error_code IN (
                'invalid_url', 'unsafe_url', 'unsupported_site', 'upstream_error',
                'extraction_failed', 'section_failure', 'timeout',
                'rate_limited', 'internal'
            )
        ),
    CONSTRAINT vibecheck_jobs_source_type_check
        CHECK (source_type IN ('url', 'pdf', 'browser_html')),
    CONSTRAINT vibecheck_jobs_terminal_finished_at
        CHECK (
            (status NOT IN ('done', 'failed') AND finished_at IS NULL)
            OR (status IN ('done', 'failed') AND finished_at IS NOT NULL)
        )
);

CREATE TABLE IF NOT EXISTS public.vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalized_url TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'scrape'
        CHECK (tier IN ('scrape', 'interact', 'browser_html')),
    url TEXT NOT NULL,
    final_url TEXT,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours'),
    evicted_at TIMESTAMPTZ,
    CONSTRAINT vibecheck_scrapes_page_kind_check
        CHECK (page_kind IN (
            'blog_post', 'forum_thread', 'hierarchical_thread',
            'blog_index', 'article', 'other'
        ))
);

CREATE TABLE IF NOT EXISTS public.vibecheck_web_risk_lookups (
    url TEXT PRIMARY KEY,
    finding_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS public.vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES public.vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    page_title TEXT,
    page_kind TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT vibecheck_job_utterances_kind_check
        CHECK (kind IN ('post', 'comment', 'reply'))
);
"""


def _schema_sql_for_test() -> str:
    raw = SCHEMA_PATH.read_text()
    return raw.replace(
        "CREATE EXTENSION IF NOT EXISTS pg_cron;",
        "SELECT 1; -- pg_cron not available in test container; shim pre-created above",
    )


@pytest.fixture(scope="module")
def _partial_status_postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def legacy_conn(
    _partial_status_postgres: PostgresContainer,
) -> AsyncIterator[asyncpg.Connection]:
    """Connection with the pre-1474.29 schema state (no 'partial' in constraints)."""
    raw = _partial_status_postgres.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    await conn.execute("DROP SCHEMA IF EXISTS cron CASCADE")
    for table in (
        "vibecheck_job_utterances",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_analyses",
        "vibecheck_web_risk_lookups",
    ):
        await conn.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")
    for fn in (
        "public.exec_sql(text)",
        "public.vibecheck_upsert_scrape_if_not_evicted("
        "text, text, text, text, text, text, text, text, text, text, "
        "timestamp with time zone, timestamp with time zone, "
        "timestamp with time zone, integer)",
        "public.vibecheck_sweep_orphan_jobs()",
        "public.vibecheck_purge_terminal_jobs()",
    ):
        await conn.execute(f"DROP FUNCTION IF EXISTS {fn} CASCADE")

    await conn.execute(PG_CRON_SHIM)
    await conn.execute(CREATE_POSTGRES_ROLE_SQL)
    await conn.execute(PRE_1474_29_DDL)

    try:
        yield conn
    finally:
        await conn.close()


async def test_partial_status_blocked_before_schema_apply(
    legacy_conn: asyncpg.Connection,
) -> None:
    """Baseline: the pre-1474.29 constraint rejects status='partial'."""
    with pytest.raises(asyncpg.CheckViolationError):
        await legacy_conn.execute(
            """
            INSERT INTO public.vibecheck_jobs
                (url, normalized_url, host, status, finished_at)
            VALUES ($1, $1, 'example.com', 'partial', now())
            """,
            "https://example.com/pre-fix",
        )


async def test_partial_status_allowed_after_schema_apply(
    legacy_conn: asyncpg.Connection,
) -> None:
    """After applying schema.sql, INSERT with status='partial' must succeed."""
    await legacy_conn.execute(_schema_sql_for_test())

    now = datetime.now(UTC)
    await legacy_conn.execute(
        """
        INSERT INTO public.vibecheck_jobs
            (url, normalized_url, host, status, finished_at)
        VALUES ($1, $1, 'example.com', 'partial', $2)
        """,
        "https://example.com/post-fix",
        now,
    )

    row = await legacy_conn.fetchrow(
        "SELECT status FROM public.vibecheck_jobs WHERE normalized_url = $1",
        "https://example.com/post-fix",
    )
    assert row is not None
    assert row["status"] == "partial"


async def test_invalid_status_still_rejected_after_schema_apply(
    legacy_conn: asyncpg.Connection,
) -> None:
    """The constraint must still reject unknown status values after the fix."""
    await legacy_conn.execute(_schema_sql_for_test())

    with pytest.raises(asyncpg.CheckViolationError):
        await legacy_conn.execute(
            """
            INSERT INTO public.vibecheck_jobs
                (url, normalized_url, host, status)
            VALUES ($1, $1, 'example.com', 'garbage')
            """,
            "https://example.com/invalid-status",
        )


async def test_schema_apply_idempotent_after_constraint_sync(
    legacy_conn: asyncpg.Connection,
) -> None:
    """Re-applying schema.sql a second time must not raise 'already exists' errors."""
    await legacy_conn.execute(_schema_sql_for_test())
    await legacy_conn.execute(_schema_sql_for_test())

    row = await legacy_conn.fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM pg_constraint
        WHERE conname IN (
            'vibecheck_jobs_status_check',
            'vibecheck_jobs_terminal_finished_at'
        )
        """
    )
    assert row is not None
    assert row["cnt"] == 2


async def test_terminal_finished_at_allows_partial_with_finished_at(
    legacy_conn: asyncpg.Connection,
) -> None:
    """After schema apply, partial+finished_at satisfies terminal_finished_at constraint."""
    await legacy_conn.execute(_schema_sql_for_test())

    now = datetime.now(UTC)
    await legacy_conn.execute(
        """
        INSERT INTO public.vibecheck_jobs
            (url, normalized_url, host, status, finished_at)
        VALUES ($1, $1, 'example.com', 'partial', $2)
        """,
        "https://example.com/terminal-check",
        now,
    )

    row = await legacy_conn.fetchrow(
        "SELECT status, finished_at FROM public.vibecheck_jobs WHERE normalized_url = $1",
        "https://example.com/terminal-check",
    )
    assert row is not None
    assert row["status"] == "partial"
    assert row["finished_at"] is not None


async def test_terminal_finished_at_rejects_partial_without_finished_at(
    legacy_conn: asyncpg.Connection,
) -> None:
    """After schema apply, partial without finished_at still violates terminal_finished_at."""
    await legacy_conn.execute(_schema_sql_for_test())

    with pytest.raises(asyncpg.CheckViolationError):
        await legacy_conn.execute(
            """
            INSERT INTO public.vibecheck_jobs
                (url, normalized_url, host, status, finished_at)
            VALUES ($1, $1, 'example.com', 'partial', NULL)
            """,
            "https://example.com/no-finished-at",
        )
