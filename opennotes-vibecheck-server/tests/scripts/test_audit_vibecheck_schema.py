from __future__ import annotations

from scripts.audit_vibecheck_schema import extract_expected_schema


def test_extract_expected_schema_finds_multiline_symbols() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS public.vibecheck_jobs (
        job_id UUID PRIMARY KEY,
        status TEXT NOT NULL
    );
    ALTER TABLE public.vibecheck_jobs
        ADD COLUMN IF NOT EXISTS headline_summary JSONB;
    ALTER TABLE public.vibecheck_jobs
        ADD CONSTRAINT vibecheck_jobs_status_check
        CHECK (status IN ('pending', 'done'));
    CREATE UNIQUE INDEX IF NOT EXISTS vibecheck_jobs_status_idx
        ON public.vibecheck_jobs (status)
        WHERE status = 'done';
    """

    expected = extract_expected_schema(schema)

    assert "vibecheck_jobs" in expected.tables
    assert expected.columns["vibecheck_jobs"] == {"job_id", "status", "headline_summary"}
    assert expected.constraints["vibecheck_jobs"] == {"vibecheck_jobs_status_check"}
    assert "vibecheck_jobs_status_idx" in expected.indexes
    assert expected.indexes["vibecheck_jobs_status_idx"].table == "vibecheck_jobs"
    assert expected.indexes["vibecheck_jobs_status_idx"].unique is True


def test_extract_expected_schema_finds_policy_cron_and_function_metadata() -> None:
    schema = """
    CREATE OR REPLACE FUNCTION public.exec_sql(sql text)
    RETURNS void
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public, pg_temp
    AS $$
    BEGIN
        EXECUTE sql;
    END;
    $$;
    ALTER FUNCTION public.exec_sql(text) OWNER TO postgres;
    REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
    GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;

    ALTER TABLE public.vibecheck_jobs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.vibecheck_jobs FORCE ROW LEVEL SECURITY;
    CREATE POLICY service_role_jobs ON public.vibecheck_jobs
        FOR ALL TO service_role
        USING (true)
        WITH CHECK (true);
    SELECT cron.schedule('vibecheck-orphan-sweep', '* * * * *', $$SELECT 1$$);
    """

    expected = extract_expected_schema(schema)

    assert "exec_sql" in expected.functions
    assert expected.functions["exec_sql"].owner == "postgres"
    assert expected.functions["exec_sql"].security_definer is True
    assert expected.functions["exec_sql"].search_path == "public, pg_temp"
    assert expected.functions["exec_sql"].grants == {"service_role"}
    assert expected.functions["exec_sql"].revokes == {"PUBLIC", "anon", "authenticated"}
    assert expected.rls_enabled == {"vibecheck_jobs"}
    assert expected.rls_forced == {"vibecheck_jobs"}
    assert expected.policies["vibecheck_jobs"] == {"service_role_jobs"}
    assert expected.cron_jobs["vibecheck-orphan-sweep"] == "* * * * *"


def test_extract_expected_schema_unquotes_identifiers() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS "vibecheck weird" (
        "job id" UUID PRIMARY KEY
    );
    ALTER TABLE "vibecheck weird"
        ADD COLUMN IF NOT EXISTS "new column" TEXT;
    """

    expected = extract_expected_schema(schema)

    assert "vibecheck weird" in expected.tables
    assert expected.columns["vibecheck weird"] == {"job id", "new column"}
