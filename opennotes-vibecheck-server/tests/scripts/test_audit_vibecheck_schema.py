from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from scripts.audit_vibecheck_schema import (
    ExpectedSchema,
    _audit,
    _audit_cron,
    _execute_grantees,
    _project_ref_from_url,
    extract_expected_schema,
)


class FakeConn:
    def __init__(
        self,
        *,
        tables: list[dict[str, Any]] | None = None,
        columns: list[dict[str, Any]] | None = None,
        indexes: list[dict[str, Any]] | None = None,
        constraints: list[dict[str, Any]] | None = None,
        rls: list[dict[str, Any]] | None = None,
        policies: list[dict[str, Any]] | None = None,
        table_privileges: list[dict[str, Any]] | None = None,
        cron: list[dict[str, Any]] | BaseException | None = None,
        functions: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tables = tables or []
        self.columns = columns or []
        self.indexes = indexes or []
        self.constraints = constraints or []
        self.rls = rls or []
        self.policies = policies or []
        self.table_privileges = table_privileges or []
        self.cron = cron or []
        self.functions = functions or []

    async def fetch(self, query: str, *_args: object) -> list[dict[str, Any]]:
        result_map = {
            "AUDIT_TABLES": self.tables,
            "AUDIT_COLUMNS": self.columns,
            "AUDIT_INDEXES": self.indexes,
            "AUDIT_CONSTRAINTS": self.constraints,
            "AUDIT_RLS": self.rls,
            "AUDIT_POLICIES": self.policies,
            "AUDIT_TABLE_PRIVILEGES": self.table_privileges,
            "AUDIT_FUNCTIONS": self.functions,
        }
        for marker, rows in result_map.items():
            if marker in query:
                return rows
        if "AUDIT_CRON" in query:
            if isinstance(self.cron, BaseException):
                raise self.cron
            return self.cron
        raise AssertionError(f"unexpected query: {query}")


def test_extract_expected_schema_finds_multiline_table_symbols() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS public.vibecheck_jobs (
        job_id UUID PRIMARY KEY,
        status TEXT NOT NULL,
        payload JSONB NOT NULL,
        weather_report JSONB,
        CONSTRAINT vibecheck_jobs_status_check
            CHECK (status IN ('pending', 'done'))
    )
    WITH (fillfactor = 90);
    ALTER TABLE public.vibecheck_jobs
        ADD COLUMN IF NOT EXISTS headline_summary JSONB;
    CREATE UNIQUE INDEX IF NOT EXISTS vibecheck_jobs_status_idx
        ON public.vibecheck_jobs (status, job_id)
        WHERE status = 'done';
    """

    expected = extract_expected_schema(schema)

    table = expected.tables["public.vibecheck_jobs"]
    assert [column.name for column in table.columns] == [
        "job_id",
        "status",
        "payload",
        "weather_report",
        "headline_summary",
    ]
    assert table.columns_by_name["payload"].definition == "JSONB NOT NULL"
    assert table.constraints["vibecheck_jobs_status_check"].expression == (
        "status IN ('pending', 'done')"
    )
    index = expected.indexes["public.vibecheck_jobs_status_idx"]
    assert index.table == "public.vibecheck_jobs"
    assert index.unique is True
    assert index.columns == ("status", "job_id")
    assert index.predicate == "status = 'done'"


def test_extract_expected_schema_skips_dollar_quoted_column_defaults() -> None:
    schema = """
    CREATE TABLE public.vibecheck_jobs (
        job_id UUID PRIMARY KEY,
        note TEXT DEFAULT $$hello, comma (still default)$$,
        payload JSONB NOT NULL
    );
    """

    expected = extract_expected_schema(schema)

    assert [column.name for column in expected.tables["public.vibecheck_jobs"].columns] == [
        "job_id",
        "note",
        "payload",
    ]


def test_extract_expected_schema_tracks_function_signature_and_search_path() -> None:
    schema = """
    CREATE FUNCTION public.exec_sql(sql text)
    RETURNS void
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        RAISE LOG 'schema apply length=% hash=%', length(sql), md5(sql);
        EXECUTE sql;
    END;
    $$;
    ALTER FUNCTION public.exec_sql(text) OWNER TO vibecheck_schema_admin;
    REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
    GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;

    CREATE OR REPLACE FUNCTION public.exec_sql(sql text, dry_run boolean)
    RETURNS void
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN;
    END;
    $$;
    """

    expected = extract_expected_schema(schema)

    assert set(expected.functions) == {
        "public.exec_sql(sql text)",
        "public.exec_sql(sql text, dry_run boolean)",
    }
    function = expected.functions["public.exec_sql(sql text)"]
    assert function.owner == "vibecheck_schema_admin"
    assert function.security_definer is True
    assert function.search_path == ("pg_catalog", "pg_temp")
    assert function.grants == {"service_role"}
    assert function.revokes == {"PUBLIC", "anon", "authenticated"}


def test_extract_expected_schema_handles_nested_policy_and_cron() -> None:
    schema = """
    CREATE POLICY service_role_jobs ON public.vibecheck_jobs
        FOR ALL TO service_role
        USING (((auth.jwt() ->> 'role') = 'service_role'))
        WITH CHECK ((true AND (auth.role() = 'service_role')));
    SELECT CRON.schedule('vibecheck-orphan-sweep', '* * * * *', $$SELECT 1$$);
    """

    expected = extract_expected_schema(schema)

    assert expected.policies["public.vibecheck_jobs"]["service_role_jobs"].using == (
        "((auth.jwt() ->> 'role') = 'service_role')"
    )
    assert expected.policies["public.vibecheck_jobs"]["service_role_jobs"].with_check == (
        "true AND (auth.role() = 'service_role')"
    )
    assert expected.cron_jobs["vibecheck-orphan-sweep"] == "* * * * *"


@pytest.mark.asyncio
async def test_audit_reports_public_execute_acl_drift() -> None:
    expected = extract_expected_schema(
        """
        CREATE FUNCTION public.exec_sql(sql text)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp AS $$BEGIN EXECUTE sql; END;$$;
        ALTER FUNCTION public.exec_sql(text) OWNER TO vibecheck_schema_admin;
        REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
        GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;
        """
    )
    conn = FakeConn(
        functions=[
            {
                "schema_name": "public",
                "function_name": "exec_sql",
                "identity_arguments": "sql text",
                "owner": "vibecheck_schema_admin",
                "security_definer": True,
                "proconfig": ["search_path=pg_catalog, pg_temp"],
                "proacl": ["=X/vibecheck_schema_admin", "service_role=X/vibecheck_schema_admin"],
            }
        ]
    )

    clean, report = await _audit(conn, expected)

    assert clean is False
    assert "`function` `public.exec_sql(sql text)`: **DRIFT**" in report


@pytest.mark.asyncio
async def test_audit_normalizes_function_acl_and_search_path() -> None:
    expected = extract_expected_schema(
        """
        CREATE FUNCTION public.exec_sql(sql text)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp AS $$BEGIN EXECUTE sql; END;$$;
        ALTER FUNCTION public.exec_sql(text) OWNER TO vibecheck_schema_admin;
        REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
        GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;
        """
    )
    conn = FakeConn(
        functions=[
            {
                "schema_name": "public",
                "function_name": "exec_sql",
                "identity_arguments": "sql text",
                "owner": "vibecheck_schema_admin",
                "security_definer": True,
                "proconfig": ["search_path=pg_catalog,pg_temp"],
                "proacl": ["service_role=Xa/vibecheck_schema_admin"],
            }
        ]
    )

    clean, report = await _audit(conn, expected)

    assert clean is True
    assert "`function` `public.exec_sql(sql text)`: **OK**" in report


@pytest.mark.asyncio
async def test_audit_compares_index_predicate_policy_constraint_and_table_revokes() -> None:
    expected = extract_expected_schema(
        """
        CREATE TABLE public.vibecheck_jobs (
            job_id UUID PRIMARY KEY,
            status TEXT NOT NULL,
            payload JSONB NOT NULL,
            CONSTRAINT vibecheck_jobs_status_check
                CHECK (status IN ('pending', 'done'))
        );
        REVOKE ALL ON public.vibecheck_jobs FROM anon, authenticated;
        CREATE INDEX vibecheck_jobs_status_idx ON public.vibecheck_jobs (status)
            WHERE status = 'done';
        CREATE POLICY service_role_jobs ON public.vibecheck_jobs
            USING (status = 'done')
            WITH CHECK (status = 'done');
        """
    )
    conn = FakeConn(
        tables=[
            {"schema_name": "public", "table_name": "vibecheck_jobs", "relkind": "r"},
        ],
        columns=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "column_name": "job_id",
                "ordinal_position": 1,
                "definition": "UUID",
            },
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "column_name": "status",
                "ordinal_position": 2,
                "definition": "TEXT NOT NULL",
            },
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "column_name": "payload",
                "ordinal_position": 3,
                "definition": "JSON NOT NULL",
            },
        ],
        indexes=[
            {
                "schema_name": "public",
                "index_name": "vibecheck_jobs_status_idx",
                "table_name": "vibecheck_jobs",
                "indexdef": (
                    "CREATE INDEX vibecheck_jobs_status_idx "
                    "ON public.vibecheck_jobs USING btree (status) "
                    "WHERE (status = 'pending'::text)"
                ),
            }
        ],
        constraints=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "constraint_name": "vibecheck_jobs_status_check",
                "definition": "CHECK ((status = ANY (ARRAY['pending'::text])))",
            }
        ],
        policies=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "policy_name": "service_role_jobs",
                "using_expr": "(status = 'pending'::text)",
                "with_check_expr": "(status = 'pending'::text)",
            }
        ],
        table_privileges=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "grantee": "anon",
                "privilege_type": "SELECT",
            }
        ],
    )

    clean, report = await _audit(conn, expected)

    assert clean is False
    assert "`column` `public.vibecheck_jobs.payload`: **DRIFT**" in report
    assert "`index` `public.vibecheck_jobs_status_idx`: **DRIFT**" in report
    assert "`constraint` `public.vibecheck_jobs.vibecheck_jobs_status_check`: **DRIFT**" in report
    assert "`policy` `public.vibecheck_jobs.service_role_jobs`: **DRIFT**" in report
    assert "`table revoke` `public.vibecheck_jobs from anon`: **DRIFT**" in report


@pytest.mark.asyncio
async def test_audit_reports_view_replacing_expected_table() -> None:
    expected = extract_expected_schema("CREATE TABLE public.vibecheck_jobs (job_id UUID);")
    conn = FakeConn(
        tables=[
            {"schema_name": "public", "table_name": "vibecheck_jobs", "relkind": "v"},
        ],
        columns=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "column_name": "job_id",
                "ordinal_position": 1,
                "definition": "UUID",
            }
        ],
    )

    clean, report = await _audit(conn, expected)

    assert clean is False
    assert "`table` `public.vibecheck_jobs`: **DRIFT**" in report


@pytest.mark.asyncio
async def test_audit_flags_unqualified_schema_sql_targets() -> None:
    expected = extract_expected_schema("CREATE TABLE vibecheck_jobs (job_id UUID);")
    conn = FakeConn(
        tables=[
            {"schema_name": "public", "table_name": "vibecheck_jobs", "relkind": "r"},
        ],
        columns=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_jobs",
                "column_name": "job_id",
                "ordinal_position": 1,
                "definition": "UUID",
            }
        ],
    )

    clean, report = await _audit(conn, expected)

    assert clean is False
    assert "`schema contract` `CREATE TABLE vibecheck_jobs`: **DRIFT**" in report


def test_project_ref_from_url_rejects_vanity_hosts() -> None:
    with pytest.raises(ValueError, match=r"supabase\.co"):
        _project_ref_from_url("https://db.example.com")


def test_function_drift_flags_null_proacl_with_public_default() -> None:
    grantees = _execute_grantees(None, owner="postgres")
    assert "PUBLIC" in grantees
    assert "postgres" in grantees


@pytest.mark.asyncio
async def test_drop_policy_in_schema_flags_when_present_in_prod() -> None:
    expected = extract_expected_schema(
        """
        CREATE TABLE public.vibecheck_analyses (id UUID PRIMARY KEY);
        DROP POLICY IF EXISTS vibecheck_analyses_full_access ON public.vibecheck_analyses;
        """
    )
    assert "vibecheck_analyses_full_access" in expected.dropped_policies.get(
        "public.vibecheck_analyses", set()
    )

    conn = FakeConn(
        tables=[
            {"schema_name": "public", "table_name": "vibecheck_analyses", "relkind": "r"},
        ],
        columns=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_analyses",
                "column_name": "id",
                "ordinal_position": 1,
                "definition": "UUID",
            }
        ],
        policies=[
            {
                "schema_name": "public",
                "table_name": "vibecheck_analyses",
                "policy_name": "vibecheck_analyses_full_access",
                "using_expr": None,
                "with_check_expr": None,
            }
        ],
    )

    clean, report = await _audit(conn, expected)

    assert clean is False
    assert (
        "`policy` `public.vibecheck_analyses.vibecheck_analyses_full_access`: **DRIFT**" in report
    )


@pytest.mark.asyncio
async def test_audit_cron_inspection_failure_with_expected_jobs_is_drift() -> None:
    expected = ExpectedSchema(cron_jobs={"vibecheck-orphan-sweep": "* * * * *"})
    error_conn = FakeConn(cron=asyncpg.PostgresError())
    report: list[str] = []

    result = await _audit_cron(error_conn, expected, report)

    assert result is False
    assert any("DRIFT" in line for line in report)


@pytest.mark.asyncio
async def test_audit_cron_inspection_failure_with_no_expected_jobs_is_clean() -> None:
    expected = ExpectedSchema(cron_jobs={})
    error_conn = FakeConn(cron=asyncpg.PostgresError())
    report: list[str] = []

    result = await _audit_cron(error_conn, expected, report)

    assert result is True
