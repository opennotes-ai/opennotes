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
        "vibecheck_feedback",
        "vibecheck_job_utterances",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_analyses",
        "vibecheck_web_risk_lookups",
    ):
        await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for fn in (
        "public.exec_sql(text)",
        # Pre-TASK-1577.01 14-arg signature: drop guarded by IF EXISTS so this
        # cleanup is a no-op once the new 15-arg form is the only one present.
        "public.vibecheck_upsert_scrape_if_not_evicted("
        "text, text, text, text, text, text, text, text, text, text, "
        "timestamp with time zone, timestamp with time zone, "
        "timestamp with time zone, integer)",
        # Post-TASK-1577.01 15-arg signature with p_raw_html.
        "public.vibecheck_upsert_scrape_if_not_evicted("
        "text, text, text, text, text, text, text, text, text, text, text, "
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


async def _install_legacy_defaulted_scrape_upsert(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE OR REPLACE FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
            p_normalized_url TEXT,
            p_tier TEXT,
            p_url TEXT,
            p_final_url TEXT,
            p_host TEXT,
            p_page_kind TEXT,
            p_page_title TEXT,
            p_markdown TEXT,
            p_html TEXT,
            p_screenshot_storage_key TEXT,
            p_scraped_at TIMESTAMPTZ,
            p_expires_at TIMESTAMPTZ,
            p_put_started_at TIMESTAMPTZ,
            p_clock_skew_seconds INT DEFAULT 1
        )
        RETURNS BOOLEAN
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT public.vibecheck_upsert_scrape_if_not_evicted(
                p_normalized_url,
                p_tier,
                p_url,
                p_final_url,
                p_host,
                p_page_kind,
                p_page_title,
                p_markdown,
                p_html,
                NULL::TEXT,
                p_screenshot_storage_key,
                p_scraped_at,
                p_expires_at,
                p_put_started_at,
                p_clock_skew_seconds
            );
        $$;
        """
    )


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
        "vibecheck_feedback",
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


async def _assert_weather_report_column_exists(conn: asyncpg.Connection) -> None:
    row = await conn.fetchrow(
        """
        SELECT is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'vibecheck_jobs'
          AND column_name = 'weather_report'
        """
    )
    assert row is not None, "weather_report column missing from public.vibecheck_jobs"
    assert row["is_nullable"] == "YES"
    assert row["column_default"] is None


async def test_full_schema_apply_first_seed(full_schema_conn: asyncpg.Connection) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await _assert_vibecheck_tables_exist(full_schema_conn)
    await _assert_weather_report_column_exists(full_schema_conn)

    for table in (
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
        "vibecheck_feedback",
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
    await _assert_weather_report_column_exists(full_schema_conn)

    for table in (
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
        "vibecheck_feedback",
    ):
        await _assert_rls_enabled(full_schema_conn, table)

    await _assert_sweeper_functions_owned_by_postgres(full_schema_conn)


async def test_full_schema_reapply_over_legacy_defaulted_scrape_upsert_function(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)
    await _install_legacy_defaulted_scrape_upsert(full_schema_conn)

    await _apply_full_schema_via_exec_sql(full_schema_conn)

    signatures = await full_schema_conn.fetch(
        """
        SELECT pronargs, pg_get_function_arguments(p.oid) AS arguments
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'vibecheck_upsert_scrape_if_not_evicted'
        ORDER BY pronargs
        """
    )
    assert [(row["pronargs"], row["arguments"]) for row in signatures] == [
        (
            14,
            "p_normalized_url text, p_tier text, p_url text, p_final_url text, "
            "p_host text, p_page_kind text, p_page_title text, p_markdown text, "
            "p_html text, p_screenshot_storage_key text, "
            "p_scraped_at timestamp with time zone, "
            "p_expires_at timestamp with time zone, "
            "p_put_started_at timestamp with time zone, "
            "p_clock_skew_seconds integer DEFAULT 1",
        ),
        (
            15,
            "p_normalized_url text, p_tier text, p_url text, p_final_url text, "
            "p_host text, p_page_kind text, p_page_title text, p_markdown text, "
            "p_html text, p_raw_html text, p_screenshot_storage_key text, "
            "p_scraped_at timestamp with time zone, "
            "p_expires_at timestamp with time zone, "
            "p_put_started_at timestamp with time zone, "
            "p_clock_skew_seconds integer",
        ),
    ]

    now = datetime.now(UTC)
    wrote_raw = await full_schema_conn.fetchval(
        """
        SELECT public.vibecheck_upsert_scrape_if_not_evicted(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
        )
        """,
        "https://example.com/reapply/raw",
        "scrape",
        "https://example.com/reapply/raw",
        "https://example.com/reapply/raw",
        "example.com",
        "other",
        "Reapply raw",
        "new replica",
        "<main>new</main>",
        "<html><body><main>new</main></body></html>",
        None,
        now,
        now + timedelta(hours=72),
        now,
        1,
    )
    assert wrote_raw is True

    wrote_legacy = await full_schema_conn.fetchval(
        """
        SELECT public.vibecheck_upsert_scrape_if_not_evicted(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        """,
        "https://example.com/reapply/legacy",
        "scrape",
        "https://example.com/reapply/legacy",
        "https://example.com/reapply/legacy",
        "example.com",
        "other",
        "Reapply legacy",
        "old replica",
        "<main>legacy</main>",
        None,
        now,
        now + timedelta(hours=72),
        now,
    )
    assert wrote_legacy is True

    rows = await full_schema_conn.fetch(
        """
        SELECT normalized_url, html, raw_html
        FROM public.vibecheck_scrapes
        WHERE normalized_url LIKE 'https://example.com/reapply/%'
        ORDER BY normalized_url
        """
    )
    assert [(row["normalized_url"], row["html"], row["raw_html"]) for row in rows] == [
        ("https://example.com/reapply/legacy", "<main>legacy</main>", None),
        (
            "https://example.com/reapply/raw",
            "<main>new</main>",
            "<html><body><main>new</main></body></html>",
        ),
    ]


async def test_full_schema_reapply_twice_idempotent(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await _apply_full_schema_via_exec_sql(full_schema_conn)

    await _apply_full_schema_via_exec_sql(full_schema_conn)

    await _assert_vibecheck_tables_exist(full_schema_conn)
    await _assert_weather_report_column_exists(full_schema_conn)

    for table in (
        "vibecheck_analyses",
        "vibecheck_jobs",
        "vibecheck_scrapes",
        "vibecheck_job_utterances",
        "vibecheck_web_risk_lookups",
        "vibecheck_feedback",
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
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
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
        None,  # p_raw_html (TASK-1577.01)
        None,  # p_screenshot_storage_key
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
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
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
            None,  # p_raw_html (TASK-1577.01)
            None,  # p_screenshot_storage_key
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


async def test_atomic_scrape_upsert_rpc_writes_raw_html(
    full_schema_conn: asyncpg.Connection,
) -> None:
    # TASK-1577.01: assert the new 15-arg signature actually persists
    # raw_html when a non-NULL value is supplied. The earlier tombstone
    # test passes NULL and only asserts evict-fence semantics.
    await _apply_full_schema_as_superuser(full_schema_conn)

    now = datetime.now(UTC)
    raw_html = "<html><body><div id='shell'>shell</div><article>post</article></body></html>"
    wrote = await full_schema_conn.fetchval(
        """
        SELECT public.vibecheck_upsert_scrape_if_not_evicted(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
        )
        """,
        "https://example.com/raw",
        "scrape",
        "https://example.com/raw",
        "https://example.com/raw",
        "example.com",
        "other",
        "Raw",
        "fresh",
        "<main>main-content</main>",
        raw_html,
        None,
        now,
        now + timedelta(hours=72),
        now,
        1,
    )
    assert wrote is True

    row = await full_schema_conn.fetchrow(
        """
        SELECT html, raw_html
        FROM public.vibecheck_scrapes
        WHERE normalized_url = $1 AND tier = 'scrape'
        """,
        "https://example.com/raw",
    )
    assert row is not None
    assert row["html"] == "<main>main-content</main>"
    assert row["raw_html"] == raw_html


async def test_atomic_scrape_upsert_rpc_14_arg_shim_writes_null_raw_html(
    full_schema_conn: asyncpg.Connection,
) -> None:
    # TASK-1577.01 rolling-deploy shim: the prior 14-arg signature must
    # remain callable so old replicas can keep serving traffic during a
    # rolling Cloud Run deploy. The shim delegates to the 15-arg form
    # with raw_html defaulted to NULL.
    await _apply_full_schema_as_superuser(full_schema_conn)

    now = datetime.now(UTC)
    wrote = await full_schema_conn.fetchval(
        """
        SELECT public.vibecheck_upsert_scrape_if_not_evicted(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """,
        "https://example.com/legacy",
        "scrape",
        "https://example.com/legacy",
        "https://example.com/legacy",
        "example.com",
        "other",
        "Legacy",
        "old replica",
        "<main>old-replica-html</main>",
        None,  # p_screenshot_storage_key (14-arg form has no p_raw_html)
        now,
        now + timedelta(hours=72),
        now,
        1,
    )
    assert wrote is True

    row = await full_schema_conn.fetchrow(
        """
        SELECT html, raw_html
        FROM public.vibecheck_scrapes
        WHERE normalized_url = $1 AND tier = 'scrape'
        """,
        "https://example.com/legacy",
    )
    assert row is not None
    assert row["html"] == "<main>old-replica-html</main>"
    assert row["raw_html"] is None


# ============= VIBECHECK FEEDBACK tests (TASK-1588.01) =============


async def _assert_feedback_table_rls(conn: asyncpg.Connection) -> None:
    await _assert_rls_enabled(conn, "vibecheck_feedback")


async def test_vibecheck_feedback_table_exists_after_schema_apply(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    row = await full_schema_conn.fetchrow(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'vibecheck_feedback'"
    )
    assert row is not None, "vibecheck_feedback table was not created"


async def test_vibecheck_feedback_rls_enabled_and_forced(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await _assert_feedback_table_rls(full_schema_conn)


async def test_vibecheck_feedback_anon_can_insert_valid_row(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await full_schema_conn.execute("SET ROLE anon")
    try:
        await full_schema_conn.execute(
            """
            INSERT INTO public.vibecheck_feedback
                (id, page_path, user_agent, uid, bell_location, initial_type)
            VALUES
                ('00000000-0000-0000-0000-000000000001',
                 '/some/page', 'Mozilla/5.0', '00000000-0000-0000-0000-000000000002',
                 'bottom-right', 'thumbs_up')
            """
        )
    finally:
        await full_schema_conn.execute("RESET ROLE")

    count = await full_schema_conn.fetchval(
        "SELECT COUNT(*) FROM public.vibecheck_feedback WHERE id = '00000000-0000-0000-0000-000000000001'"
    )
    assert count == 1


async def test_vibecheck_feedback_anon_cannot_update_row(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    await full_schema_conn.execute(
        """
        INSERT INTO public.vibecheck_feedback
            (id, page_path, user_agent, uid, bell_location, initial_type)
        VALUES
            ('00000000-0000-0000-0000-000000000010',
             '/page', 'ua', '00000000-0000-0000-0000-000000000011',
             'top-left', 'thumbs_down')
        """
    )

    await full_schema_conn.execute("SET ROLE anon")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await full_schema_conn.execute(
                "UPDATE public.vibecheck_feedback SET final_type = 'thumbs_up'"
            )
    finally:
        await full_schema_conn.execute("RESET ROLE")


async def test_vibecheck_feedback_no_dedicated_select_policy_for_anon(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    rows = await full_schema_conn.fetch(
        """
        SELECT policyname, cmd
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'vibecheck_feedback'
          AND roles @> ARRAY['anon']::name[]
          AND cmd = 'SELECT'
        """
    )
    assert rows == [], (
        "no SELECT policy should exist for anon on vibecheck_feedback; "
        "anon is INSERT-only (TASK-1588.18 dropped the anon UPDATE policy)"
    )


async def test_vibecheck_feedback_check_constraint_rejects_invalid_initial_type(
    full_schema_conn: asyncpg.Connection,
) -> None:
    await _apply_full_schema_as_superuser(full_schema_conn)

    with pytest.raises(asyncpg.CheckViolationError):
        await full_schema_conn.execute(
            """
            INSERT INTO public.vibecheck_feedback
                (id, page_path, user_agent, uid, bell_location, initial_type)
            VALUES
                ('00000000-0000-0000-0000-000000000030',
                 '/page', 'ua', '00000000-0000-0000-0000-000000000031',
                 'bottom-right', 'lol')
            """
        )
