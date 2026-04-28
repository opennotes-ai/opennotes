from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

BOOTSTRAP_SQL = """
SET LOCAL lock_timeout = '30s';
SELECT pg_advisory_xact_lock(1490, hashtext('schema_apply')::int);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vibecheck_schema_admin') THEN
        CREATE ROLE vibecheck_schema_admin;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT has_schema_privilege('vibecheck_schema_admin', 'public', 'CREATE') THEN
        GRANT USAGE, CREATE ON SCHEMA public TO vibecheck_schema_admin;
    END IF;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'vibecheck_schema_admin already exists but current role cannot grant public schema privileges';
END
$$;

CREATE OR REPLACE FUNCTION public.exec_sql(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE LOG 'vibecheck exec_sql apply length=% hash=%', length(sql), md5(sql);
    EXECUTE sql;
END;
$$;
ALTER FUNCTION public.exec_sql(text) OWNER TO vibecheck_schema_admin;
REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;
"""


@pytest.fixture(scope="module")
def _exec_sql_postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def exec_sql_conn(
    _exec_sql_postgres: PostgresContainer,
) -> AsyncIterator[asyncpg.Connection]:
    raw = _exec_sql_postgres.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    await conn.execute("DROP FUNCTION IF EXISTS public.exec_sql(text);")
    await conn.execute("DROP TABLE IF EXISTS public.exec_sql_smoke;")
    await conn.execute(BOOTSTRAP_SQL)
    try:
        yield conn
    finally:
        await conn.close()


async def test_exec_sql_permission_model(exec_sql_conn: asyncpg.Connection) -> None:
    row = await exec_sql_conn.fetchrow(
        """
        SELECT
            pg_get_userbyid(p.proowner) AS owner,
            p.prosecdef,
            p.proconfig
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'exec_sql'
          AND pg_get_function_identity_arguments(p.oid) = 'sql text'
        """
    )

    assert row is not None
    assert row["owner"] == "vibecheck_schema_admin"
    assert row["prosecdef"] is True
    assert row["proconfig"] == ["search_path=pg_catalog, pg_temp"]

    await exec_sql_conn.execute("SET ROLE anon")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_sql_conn.execute("SELECT public.exec_sql('SELECT 1')")
    await exec_sql_conn.execute("RESET ROLE")

    await exec_sql_conn.execute("SET ROLE authenticated")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_sql_conn.execute("SELECT public.exec_sql('SELECT 1')")
    await exec_sql_conn.execute("RESET ROLE")

    await exec_sql_conn.execute("SET ROLE service_role")
    await exec_sql_conn.execute(
        "SELECT public.exec_sql('CREATE TABLE IF NOT EXISTS public.exec_sql_smoke (id int)')"
    )
    await exec_sql_conn.execute("RESET ROLE")

    exists = await exec_sql_conn.fetchval("SELECT to_regclass('public.exec_sql_smoke')")
    assert exists == "exec_sql_smoke"


async def test_exec_sql_bootstrap_is_idempotent(exec_sql_conn: asyncpg.Connection) -> None:
    await exec_sql_conn.execute("SET ROLE service_role")
    await exec_sql_conn.execute("SELECT public.exec_sql($1)", BOOTSTRAP_SQL)
    await exec_sql_conn.execute("RESET ROLE")

    grants = await exec_sql_conn.fetch(
        """
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE r.rolname END AS grantee,
               a.privilege_type
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        CROSS JOIN LATERAL aclexplode(p.proacl) a
        LEFT JOIN pg_roles r ON r.oid = a.grantee
        WHERE n.nspname = 'public'
          AND p.proname = 'exec_sql'
          AND pg_get_function_identity_arguments(p.oid) = 'sql text'
        """
    )

    execute_grantees = {
        row["grantee"] for row in grants if row["privilege_type"] == "EXECUTE"
    }
    assert "service_role" in execute_grantees
    assert execute_grantees.isdisjoint({"PUBLIC", "anon", "authenticated"})
