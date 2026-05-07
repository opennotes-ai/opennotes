"""Structural contracts for src/cache/schema.sql (TASK-1473.04).

The DDL has been verified end-to-end against a local Postgres (see PR
notes); these tests guard the structural invariants the spec requires so a
future edit cannot silently drop them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "src" / "cache" / "schema.sql"
DDL_TARGET_PATTERNS = {
    "CREATE TABLE": re.compile(r"(?im)^\s*CREATE\s+TABLE\s+(?!(?:IF\s+NOT\s+EXISTS\s+)?public\.)"),
    "ALTER TABLE": re.compile(r"(?im)^\s*ALTER\s+TABLE\s+(?!public\.)"),
    "DROP POLICY": re.compile(
        r"(?im)^\s*DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?\w+\s+ON\s+(?!public\.)"
    ),
    "REVOKE TABLE": re.compile(r"(?im)^\s*REVOKE\s+ALL\s+ON\s+(?!FUNCTION\b|public\.)"),
    "CREATE INDEX ON": re.compile(
        r"(?im)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:public\.)?\w+\s+ON\s+(?!public\.)"
    ),
    "DROP INDEX": re.compile(r"(?im)^\s*DROP\s+INDEX\s+(?!(?:IF\s+EXISTS\s+)?public\.)"),
    "ALTER FUNCTION": re.compile(r"(?im)^\s*ALTER\s+FUNCTION\s+(?!public\.)"),
    "REVOKE FUNCTION": re.compile(r"(?im)^\s*REVOKE\s+ALL\s+ON\s+FUNCTION\s+(?!public\.)"),
}
UNQUALIFIED_FUNCTION_CALLS = re.compile(
    r"(?<!\.)\b("
    r"uuid_generate_v4|now|length|md5|hashtext|pg_advisory_xact_lock|"
    r"has_schema_privilege"
    r")\s*\(",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _without_line_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _exec_sql_statement(sql: str) -> str:
    match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.exec_sql\(sql text\)"
        r".*?\n\$\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _vibecheck_jobs_create_table(sql: str) -> str:
    pattern = (
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_jobs\s+\([\s\S]*?\n\)\s*;"
    )
    match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    assert match is not None
    return match.group(0)


def _jobs_error_code_check_body(sql: str) -> str:
    jobs_create = _vibecheck_jobs_create_table(sql)
    pattern = (
        r"CONSTRAINT\s+vibecheck_jobs_error_code_check\s+CHECK\s*\(\s*"
        r"error_code\s+IS\s+NULL\s+OR\s+error_code\s+IN\s*\((.*?)\)\s*\)"
    )
    match = re.search(pattern, jobs_create, re.IGNORECASE | re.DOTALL)
    assert match is not None
    return match.group(1)


def _jobs_error_code_alter_check_body(sql: str) -> str:
    pattern = (
        r"ALTER\s+TABLE\s+public\.vibecheck_jobs\s+"
        r"ADD\s+CONSTRAINT\s+vibecheck_jobs_error_code_check\s+"
        r"CHECK\s*\(\s*error_code\s+IS\s+NULL\s+OR\s+error_code\s+IN\s*\((.*?)\)\s*\)"
    )
    matches = re.findall(pattern, sql, re.IGNORECASE | re.DOTALL)
    assert matches
    return matches[-1]


class TestNewTablesExist:
    @pytest.mark.parametrize(
        "table",
        [
            "vibecheck_jobs",
            "vibecheck_scrapes",
            "vibecheck_job_utterances",
            "vibecheck_pdf_archives",
        ],
    )
    def test_create_table_if_not_exists(self, schema_sql: str, table: str) -> None:
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in schema_sql


class TestExecSqlBootstrap:
    def test_exec_sql_function_is_locked_to_service_role(self, schema_sql: str) -> None:
        statement = _exec_sql_statement(schema_sql)
        assert "CREATE OR REPLACE FUNCTION public.exec_sql(sql text)" in statement
        assert "SECURITY DEFINER" in statement
        assert "SET search_path = pg_catalog, pg_temp" in statement
        assert "SET search_path = public, pg_temp" not in statement
        assert (
            "ALTER FUNCTION public.exec_sql(text) OWNER TO vibecheck_schema_admin" not in schema_sql
        )
        assert (
            "REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated"
        ) in schema_sql
        assert "GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role" in schema_sql
        assert "GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO authenticator" not in schema_sql

    def test_exec_sql_has_dashboard_warning_comment(self, schema_sql: str) -> None:
        assert "COMMENT ON FUNCTION public.exec_sql(text)" in schema_sql
        assert "TEMPORARY" in schema_sql
        assert "TASK-1490.20" in schema_sql
        assert "Do NOT flip search_path" in schema_sql
        assert "TASK-1490.10" in schema_sql
        assert "TASK-1490.21" in schema_sql
        assert "TASK-1490.39" in schema_sql

    def test_schema_apply_uses_namespaced_lock_before_all_create_alter(
        self, schema_sql: str
    ) -> None:
        lock_index = schema_sql.index("SELECT pg_catalog.pg_advisory_xact_lock(")
        ddl_matches = list(re.finditer(r"(?m)^(CREATE|ALTER)\s+(?!ROLE\b)", schema_sql))

        assert "SET LOCAL lock_timeout = '30s'" in schema_sql
        assert (
            "pg_catalog.pg_advisory_xact_lock(1490, pg_catalog.hashtext('schema_apply')::int)"
            in schema_sql
        )
        assert ddl_matches
        assert all(lock_index < match.start() for match in ddl_matches)

    def test_exec_sql_comment_documents_temporary_removal_criteria(self, schema_sql: str) -> None:
        assert "TEMPORARY exec_sql bootstrap" in schema_sql
        assert "TASK-1490.20" in schema_sql
        assert "privilege-escalation" in schema_sql
        assert "opennotes-server merge" in schema_sql
        assert "Alembic owns vibecheck schema changes" in schema_sql


class TestRowLevelSecurityLockdown:
    @pytest.mark.parametrize(
        "table",
        [
            "vibecheck_jobs",
            "vibecheck_scrapes",
            "vibecheck_job_utterances",
            "vibecheck_pdf_archives",
        ],
    )
    def test_table_enables_and_forces_rls(self, schema_sql: str, table: str) -> None:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in schema_sql
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in schema_sql

    @pytest.mark.parametrize(
        "table",
        [
            "vibecheck_jobs",
            "vibecheck_scrapes",
            "vibecheck_job_utterances",
            "vibecheck_pdf_archives",
        ],
    )
    def test_revokes_anon_and_authenticated(self, schema_sql: str, table: str) -> None:
        assert f"REVOKE ALL ON public.{table} FROM anon, authenticated" in schema_sql

    def test_legacy_analyses_policy_dropped(self, schema_sql: str) -> None:
        assert (
            "DROP POLICY IF EXISTS vibecheck_analyses_full_access ON public.vibecheck_analyses"
            in schema_sql
        )
        assert "REVOKE ALL ON public.vibecheck_analyses FROM anon, authenticated" in schema_sql


class TestStatusCheckConstraint:
    def test_jobs_status_check_lists_all_states(self, schema_sql: str) -> None:
        for status in ("pending", "extracting", "analyzing", "done", "partial", "failed"):
            assert f"'{status}'" in schema_sql

    def test_jobs_error_code_check_lists_all_codes(self, schema_sql: str) -> None:
        for code in (
            "invalid_url",
            "unsafe_url",
            "unsupported_site",
            "upstream_error",
            "extraction_failed",
            "timeout",
            "rate_limited",
            "section_failure",
            "internal",
            "pdf_too_large",
            "pdf_extraction_failed",
        ):
            assert f"'{code}'" in _jobs_error_code_check_body(schema_sql)

    def test_scrapes_page_kind_check_lists_six_kinds(self, schema_sql: str) -> None:
        for kind in (
            "blog_post",
            "forum_thread",
            "hierarchical_thread",
            "blog_index",
            "article",
            "other",
        ):
            assert f"'{kind}'" in schema_sql

    def test_utterances_kind_check(self, schema_sql: str) -> None:
        assert "vibecheck_job_utterances_kind_check" in schema_sql
        for kind in ("post", "comment", "reply"):
            assert f"'{kind}'" in schema_sql


class TestSweeperFunctions:
    def test_orphan_sweeper_function_exists_with_security_definer(self, schema_sql: str) -> None:
        assert "CREATE OR REPLACE FUNCTION public.vibecheck_sweep_orphan_jobs()" in schema_sql
        assert "SECURITY DEFINER" in schema_sql
        assert "ALTER FUNCTION public.vibecheck_sweep_orphan_jobs() OWNER TO postgres" in schema_sql

    def test_purge_sweeper_function_exists_with_security_definer(self, schema_sql: str) -> None:
        assert "CREATE OR REPLACE FUNCTION public.vibecheck_purge_terminal_jobs()" in schema_sql
        assert (
            "ALTER FUNCTION public.vibecheck_purge_terminal_jobs() OWNER TO postgres" in schema_sql
        )

    def test_orphan_sweeper_uses_240s_pending_threshold(self, schema_sql: str) -> None:
        assert "INTERVAL '240 seconds'" in schema_sql

    def test_orphan_sweeper_uses_30s_heartbeat_threshold(self, schema_sql: str) -> None:
        assert "INTERVAL '30 seconds'" in schema_sql

    def test_orphan_sweeper_pending_tier_only_targets_pending_status(self, schema_sql: str) -> None:
        # Tier 1 must be pending-only — earlier draft applied 240s to all
        # non-terminal jobs and would have killed long-running healthy
        # extracting/analyzing jobs.
        assert (
            "status = 'pending' AND (pg_catalog.now() - created_at) > INTERVAL '240 seconds'"
            in schema_sql
        )

    def test_orphan_sweeper_treats_partial_as_terminal(self, schema_sql: str) -> None:
        assert "status NOT IN ('done', 'partial', 'failed')" in schema_sql

    def test_purge_sweeper_treats_partial_as_terminal(self, schema_sql: str) -> None:
        assert "status IN ('done', 'partial', 'failed')" in schema_sql

    def test_orphan_sweeper_heartbeat_tier_uses_coalesce_grace(self, schema_sql: str) -> None:
        # COALESCE(heartbeat_at, updated_at, created_at) lets a freshly-active
        # job get a 30s grace period before being failed.
        assert "COALESCE(heartbeat_at, updated_at, created_at)" in schema_sql

    def test_security_definer_functions_pin_search_path(self, schema_sql: str) -> None:
        # SECURITY DEFINER without search_path is a hijack vector via
        # untrusted schemas; pin to pg_catalog + pg_temp.
        assert schema_sql.count("SET search_path = pg_catalog, pg_temp") == 5
        assert "SET search_path = public, pg_temp" not in schema_sql

    def test_sweepers_revoke_execute_from_public(self, schema_sql: str) -> None:
        # Without REVOKE, anon/authenticated could trigger postgres-privileged
        # mutations.
        assert (
            "REVOKE ALL ON FUNCTION public.vibecheck_sweep_orphan_jobs() "
            "FROM PUBLIC, anon, authenticated"
        ) in schema_sql
        assert (
            "REVOKE ALL ON FUNCTION public.vibecheck_purge_terminal_jobs() "
            "FROM PUBLIC, anon, authenticated"
        ) in schema_sql

    def test_cron_calls_schema_qualified_functions(self, schema_sql: str) -> None:
        # search_path on the cron worker is unpredictable; use public.<fn>().
        assert "public.vibecheck_sweep_orphan_jobs()" in schema_sql
        assert "public.vibecheck_purge_terminal_jobs()" in schema_sql


class TestScrapeCacheFunctions:
    def test_atomic_scrape_upsert_function_exists(self, schema_sql: str) -> None:
        assert (
            "CREATE OR REPLACE FUNCTION public.vibecheck_upsert_scrape_if_not_evicted("
            in schema_sql
        )
        assert "ON CONFLICT (normalized_url, tier)" in schema_sql
        assert "WHERE tier IN ('scrape', 'interact')" in schema_sql
        assert "DO UPDATE" in schema_sql
        assert "public.vibecheck_scrapes.evicted_at IS NULL" in schema_sql
        assert "RETURN COALESCE(wrote_row, FALSE)" in schema_sql

    def test_atomic_scrape_upsert_function_is_service_role_only(
        self, schema_sql: str
    ) -> None:
        assert (
            "ALTER FUNCTION public.vibecheck_upsert_scrape_if_not_evicted("
            in schema_sql
        )
        assert (
            "REVOKE ALL ON FUNCTION public.vibecheck_upsert_scrape_if_not_evicted("
            in schema_sql
        )
        assert (
            "GRANT EXECUTE ON FUNCTION public.vibecheck_upsert_scrape_if_not_evicted("
            in schema_sql
        )

    def test_atomic_scrape_upsert_reload_notifies_postgrest_schema_cache(
        self, schema_sql: str
    ) -> None:
        assert "NOTIFY pgrst, 'reload schema'" in schema_sql


class TestPgCronSchedules:
    def test_orphan_sweep_scheduled_every_minute(self, schema_sql: str) -> None:
        assert "'vibecheck-orphan-sweep'" in schema_sql
        # Block of cron schedule literal is on its own line.
        assert "'* * * * *'" in schema_sql

    def test_purge_scheduled_hourly_at_minute_5(self, schema_sql: str) -> None:
        assert "'vibecheck-purge-terminal'" in schema_sql
        assert "'5 * * * *'" in schema_sql

    def test_schedules_are_idempotent(self, schema_sql: str) -> None:
        # Both schedules unschedule themselves first when present.
        assert "PERFORM cron.unschedule('vibecheck-orphan-sweep')" in schema_sql
        assert "PERFORM cron.unschedule('vibecheck-purge-terminal')" in schema_sql


class TestIdempotency:
    def test_extension_creation_uses_if_not_exists(self, schema_sql: str) -> None:
        assert "CREATE EXTENSION IF NOT EXISTS pg_cron" in schema_sql
        assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions' in schema_sql

    def test_indexes_use_if_not_exists(self, schema_sql: str) -> None:
        # Spot-check a few; structural — the schema is full of them.
        for idx in (
            "vibecheck_jobs_normalized_url_idx",
            "vibecheck_jobs_status_created_at_idx",
            "vibecheck_jobs_heartbeat_idx",
            "vibecheck_jobs_finished_at_idx",
            "vibecheck_scrapes_expires_at_idx",
            "vibecheck_job_utterances_job_id_idx",
            "vibecheck_pdf_archives_expires_at_idx",
        ):
            assert f"CREATE INDEX IF NOT EXISTS {idx}" in schema_sql

    def test_drop_policy_is_guarded(self, schema_sql: str) -> None:
        # Re-running must not error on missing legacy policies.
        assert "DROP POLICY IF EXISTS" in schema_sql

    def test_safety_recommendation_column_is_added_idempotently(self, schema_sql: str) -> None:
        assert "safety_recommendation JSONB" in schema_sql
        assert (
            "ALTER TABLE public.vibecheck_jobs\n"
            "    ADD COLUMN IF NOT EXISTS safety_recommendation JSONB"
        ) in schema_sql

    def test_preview_description_column_is_added_idempotently(self, schema_sql: str) -> None:
        # TASK-1485.01: gallery preview blurb persisted at job-completion time.
        assert (
            "ALTER TABLE public.vibecheck_jobs\n"
            "    ADD COLUMN IF NOT EXISTS preview_description TEXT"
        ) in schema_sql

    def test_headline_summary_column_is_added_idempotently(self, schema_sql: str) -> None:
        # TASK-1508.04.01: synthesized headline summation column.
        assert (
            "ALTER TABLE public.vibecheck_jobs\n    ADD COLUMN IF NOT EXISTS headline_summary JSONB"
        ) in schema_sql

    def test_weather_report_column_is_added_idempotently(self, schema_sql: str) -> None:
        # TASK-1508.19.04: weather report persisted for weather-aware analyses.
        assert (
            "ALTER TABLE public.vibecheck_jobs\n    ADD COLUMN IF NOT EXISTS weather_report JSONB"
        ) in schema_sql


class TestWebRiskLookupsTable:
    def test_create_table_if_not_exists(self, schema_sql: str) -> None:
        assert "CREATE TABLE IF NOT EXISTS public.vibecheck_web_risk_lookups" in schema_sql

    def test_rls_enabled_and_forced(self, schema_sql: str) -> None:
        assert (
            "ALTER TABLE public.vibecheck_web_risk_lookups ENABLE ROW LEVEL SECURITY" in schema_sql
        )
        assert (
            "ALTER TABLE public.vibecheck_web_risk_lookups FORCE ROW LEVEL SECURITY" in schema_sql
        )

    def test_revokes_anon_and_authenticated(self, schema_sql: str) -> None:
        assert (
            "REVOKE ALL ON public.vibecheck_web_risk_lookups FROM anon, authenticated" in schema_sql
        )

    def test_expires_at_index_exists(self, schema_sql: str) -> None:
        assert "CREATE INDEX IF NOT EXISTS vibecheck_web_risk_lookups_expires_at_idx" in schema_sql

    def test_no_policies_for_anon_or_authenticated(self, schema_sql: str) -> None:
        forbidden = [
            line
            for line in schema_sql.splitlines()
            if "vibecheck_web_risk_lookups" in line
            and (line.strip().startswith("CREATE POLICY") or re.search(r"\bGRANT\b", line))
        ]
        assert forbidden == []


class TestUnsafeUrlErrorCode:
    def test_error_code_check_includes_unsafe_url(self, schema_sql: str) -> None:
        assert "'unsafe_url'" in schema_sql

    def test_error_code_drop_if_exists_and_add_is_idempotent(self, schema_sql: str) -> None:
        assert "vibecheck_jobs_error_code_check" in schema_sql
        # TOCTOU-safe idempotent apply: DROP ... IF EXISTS + ADD inline,
        # not a DO-block information_schema probe (codex P2.5).
        assert "DROP CONSTRAINT IF EXISTS vibecheck_jobs_error_code_check" in schema_sql
        assert "ADD CONSTRAINT vibecheck_jobs_error_code_check" in schema_sql

    def test_error_code_alter_check_lists_all_codes(self, schema_sql: str) -> None:
        for code in (
            "invalid_url",
            "unsupported_site",
            "upstream_error",
            "extraction_failed",
            "timeout",
            "rate_limited",
            "internal",
            "unsafe_url",
            "pdf_too_large",
            "pdf_extraction_failed",
        ):
            assert f"'{code}'" in _jobs_error_code_alter_check_body(schema_sql)


class TestPurgeFunctionExtended:
    def test_purge_function_deletes_expired_web_risk_lookups(self, schema_sql: str) -> None:
        assert (
            "DELETE FROM public.vibecheck_web_risk_lookups WHERE expires_at < pg_catalog.now()"
            in schema_sql
        )


class TestSchemaQualification:
    def test_all_public_ddl_targets_are_schema_qualified(self, schema_sql: str) -> None:
        sql = _without_line_comments(schema_sql)
        failures = {
            name: pattern.findall(sql)
            for name, pattern in DDL_TARGET_PATTERNS.items()
            if pattern.findall(sql)
        }
        assert failures == {}

    def test_builtin_and_extension_calls_are_schema_qualified(self, schema_sql: str) -> None:
        sql = _without_line_comments(schema_sql)
        unqualified = [match.group(0) for match in UNQUALIFIED_FUNCTION_CALLS.finditer(sql)]
        assert unqualified == []
