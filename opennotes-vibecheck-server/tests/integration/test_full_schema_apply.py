from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
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


@pytest.fixture(scope="module")
def _full_schema_postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def full_schema_conn(
    _full_schema_postgres: PostgresContainer,
) -> AsyncIterator[asyncpg.Connection]:
    raw = _full_schema_postgres.get_connection_url()
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
        await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
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

    try:
        yield conn
    finally:
        await conn.close()


def _schema_sql_for_test() -> str:
    raw = SCHEMA_PATH.read_text()
    return raw.replace(
        "CREATE EXTENSION IF NOT EXISTS pg_cron;",
        "SELECT 1; -- pg_cron not available in test container; shim pre-created above",
    )


async def _apply_full_schema_as_superuser(conn: asyncpg.Connection) -> None:
    await conn.execute(_schema_sql_for_test())


async def _apply_full_schema_via_exec_sql(conn: asyncpg.Connection) -> None:
    schema_sql = _schema_sql_for_test()
    await conn.execute("SET ROLE service_role")
    try:
        await conn.execute("SELECT public.exec_sql($1)", schema_sql)
    finally:
        await conn.execute("RESET ROLE")


async def _assert_rls_enabled(conn: asyncpg.Connection, table: str) -> None:
    row = await conn.fetchrow(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = $1",
        table,
    )
    assert row is not None, f"Table {table} not found in pg_class"
    assert row["relrowsecurity"] is True, f"RLS not enabled on {table}"
    assert row["relforcerowsecurity"] is True, f"RLS not forced on {table}"


async def _assert_vibecheck_tables_exist(conn: asyncpg.Connection) -> None:
    expected = {
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
    }
    rows = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY($1)",
        list(expected),
    )
    found = {row["tablename"] for row in rows}
    assert found == expected, f"Missing tables: {expected - found}"


async def _assert_sweeper_functions_owned_by_postgres(conn: asyncpg.Connection) -> None:
    for fn_name in ("vibecheck_sweep_orphan_jobs", "vibecheck_purge_terminal_jobs"):
        row = await conn.fetchrow(
            """
            SELECT pg_get_userbyid(p.proowner) AS owner,
                   rolsuper
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            JOIN pg_roles r ON r.oid = p.proowner
            WHERE n.nspname = 'public' AND p.proname = $1
            """,
            fn_name,
        )
        assert row is not None, f"Function {fn_name} not found"
        assert row["rolsuper"] is True, (
            f"{fn_name} must be owned by a superuser role; "
            f"owner={row['owner']!r} is not a superuser"
        )


async def test_full_schema_apply_first_seed(full_schema_conn: asyncpg.Connection) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await _assert_vibecheck_tables_exist(full_schema_conn)

    for table in (
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
    ):
        await _assert_rls_enabled(full_schema_conn, table)

    await _assert_sweeper_functions_owned_by_postgres(full_schema_conn)


async def test_full_schema_apply_resolves_uuid_ossp_from_extensions_schema(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await full_schema_conn.execute('DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE')
    await full_schema_conn.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    await full_schema_conn.execute('CREATE EXTENSION "uuid-ossp" WITH SCHEMA extensions')

    await _apply_full_schema_as_superuser(full_schema_conn)

    await _assert_vibecheck_tables_exist(full_schema_conn)
    default_exprs = await full_schema_conn.fetch(
        """
        SELECT table_name, column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY($1)
          AND column_default LIKE '%uuid_generate_v4%'
        ORDER BY table_name, column_name
        """,
        ["vibecheck_jobs", "vibecheck_scrapes", "vibecheck_job_utterances"],
    )
    assert {
        (row["table_name"], row["column_name"], row["column_default"]) for row in default_exprs
    } == {
        ("vibecheck_job_utterances", "utterance_pk", "extensions.uuid_generate_v4()"),
        ("vibecheck_jobs", "attempt_id", "extensions.uuid_generate_v4()"),
        ("vibecheck_jobs", "job_id", "extensions.uuid_generate_v4()"),
        ("vibecheck_scrapes", "scrape_id", "extensions.uuid_generate_v4()"),
    }


async def test_full_schema_reapply_via_exec_sql_idempotent(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await _apply_full_schema_via_exec_sql(full_schema_conn)

    await _assert_vibecheck_tables_exist(full_schema_conn)

    for table in (
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
    ):
        await _assert_rls_enabled(full_schema_conn, table)

    await _assert_sweeper_functions_owned_by_postgres(full_schema_conn)


async def test_full_schema_reapply_twice_idempotent(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await _apply_full_schema_via_exec_sql(full_schema_conn)

    await _apply_full_schema_via_exec_sql(full_schema_conn)

    await _assert_vibecheck_tables_exist(full_schema_conn)

    for table in (
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
    ):
        await _assert_rls_enabled(full_schema_conn, table)

    await _assert_sweeper_functions_owned_by_postgres(full_schema_conn)

    row = await full_schema_conn.fetchrow(
        """
        SELECT pg_get_userbyid(p.proowner) AS owner
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'exec_sql'
          AND pg_get_function_identity_arguments(p.oid) = 'sql text'
        """
    )
    assert row is not None
    assert row["owner"] != "vibecheck_schema_admin", (
        "exec_sql must not be owned by vibecheck_schema_admin after re-apply; "
        "ownership must remain with the superuser who seeded it"
    )


async def test_atomic_scrape_upsert_rpc_respects_newer_tombstone(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    now = datetime.now(UTC)
    wrote = await full_schema_conn.fetchval(
        """
        SELECT public.vibecheck_upsert_scrape_if_not_evicted(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """,
        "https://example.com/rpc",
        "scrape",
        "https://example.com/rpc",
        "https://example.com/rpc",
        "example.com",
        "other",
        "RPC",
        "fresh",
        "<main>fresh</main>",
        None,
        now,
        now + timedelta(hours=72),
        now,
        1,
    )
    assert wrote is True

    tombstone_time = datetime.now(UTC)
    await full_schema_conn.execute(
        """
        UPDATE public.vibecheck_scrapes
        SET markdown = NULL,
            html = NULL,
            expires_at = $2,
            evicted_at = $3
        WHERE normalized_url = $1 AND tier = 'scrape'
        """,
        "https://example.com/rpc",
        tombstone_time - timedelta(hours=1),
        tombstone_time,
    )

    await full_schema_conn.execute("SET ROLE service_role")
    try:
        wrote_after_tombstone = await full_schema_conn.fetchval(
            """
            SELECT public.vibecheck_upsert_scrape_if_not_evicted(
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            """,
            "https://example.com/rpc",
            "scrape",
            "https://example.com/rpc",
            "https://example.com/rpc",
            "example.com",
            "other",
            "RPC",
            "resurrected",
            "<main>resurrected</main>",
            None,
            tombstone_time + timedelta(seconds=1),
            tombstone_time + timedelta(hours=72),
            tombstone_time - timedelta(seconds=2),
            1,
        )
    finally:
        await full_schema_conn.execute("RESET ROLE")

    assert wrote_after_tombstone is False
    row = await full_schema_conn.fetchrow(
        """
        SELECT markdown, html, evicted_at
        FROM public.vibecheck_scrapes
        WHERE normalized_url = $1 AND tier = 'scrape'
        """,
        "https://example.com/rpc",
    )
    assert row is not None
    assert row["markdown"] is None
    assert row["html"] is None
    assert row["evicted_at"] == tombstone_time
