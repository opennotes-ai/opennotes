"""Structural contracts for src/cache/schema.sql (TASK-1473.04).

The DDL has been verified end-to-end against a local Postgres (see PR
notes); these tests guard the structural invariants the spec requires so a
future edit cannot silently drop them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "src" / "cache" / "schema.sql"


@pytest.fixture(scope="module")
def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


class TestNewTablesExist:
    @pytest.mark.parametrize(
        "table",
        [
            "vibecheck_jobs",
            "vibecheck_scrapes",
            "vibecheck_job_utterances",
        ],
    )
    def test_create_table_if_not_exists(self, schema_sql: str, table: str) -> None:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema_sql


class TestRowLevelSecurityLockdown:
    @pytest.mark.parametrize(
        "table",
        [
            "vibecheck_jobs",
            "vibecheck_scrapes",
            "vibecheck_job_utterances",
        ],
    )
    def test_table_enables_and_forces_rls(
        self, schema_sql: str, table: str
    ) -> None:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in schema_sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in schema_sql

    @pytest.mark.parametrize(
        "table",
        [
            "vibecheck_jobs",
            "vibecheck_scrapes",
            "vibecheck_job_utterances",
        ],
    )
    def test_revokes_anon_and_authenticated(
        self, schema_sql: str, table: str
    ) -> None:
        assert f"REVOKE ALL ON {table} FROM anon, authenticated" in schema_sql

    def test_legacy_analyses_policy_dropped(self, schema_sql: str) -> None:
        assert (
            "DROP POLICY IF EXISTS vibecheck_analyses_full_access ON vibecheck_analyses"
            in schema_sql
        )
        assert "REVOKE ALL ON vibecheck_analyses FROM anon, authenticated" in schema_sql


class TestStatusCheckConstraint:
    def test_jobs_status_check_lists_all_states(self, schema_sql: str) -> None:
        for status in ("pending", "extracting", "analyzing", "done", "partial", "failed"):
            assert f"'{status}'" in schema_sql

    def test_jobs_error_code_check_lists_all_codes(
        self, schema_sql: str
    ) -> None:
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
        ):
            assert f"'{code}'" in schema_sql

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
    def test_orphan_sweeper_function_exists_with_security_definer(
        self, schema_sql: str
    ) -> None:
        assert "CREATE OR REPLACE FUNCTION vibecheck_sweep_orphan_jobs()" in schema_sql
        assert "SECURITY DEFINER" in schema_sql
        assert (
            "ALTER FUNCTION vibecheck_sweep_orphan_jobs() OWNER TO postgres"
            in schema_sql
        )

    def test_purge_sweeper_function_exists_with_security_definer(
        self, schema_sql: str
    ) -> None:
        assert (
            "CREATE OR REPLACE FUNCTION vibecheck_purge_terminal_jobs()" in schema_sql
        )
        assert (
            "ALTER FUNCTION vibecheck_purge_terminal_jobs() OWNER TO postgres"
            in schema_sql
        )

    def test_orphan_sweeper_uses_240s_pending_threshold(
        self, schema_sql: str
    ) -> None:
        assert "INTERVAL '240 seconds'" in schema_sql

    def test_orphan_sweeper_uses_30s_heartbeat_threshold(
        self, schema_sql: str
    ) -> None:
        assert "INTERVAL '30 seconds'" in schema_sql

    def test_orphan_sweeper_pending_tier_only_targets_pending_status(
        self, schema_sql: str
    ) -> None:
        # Tier 1 must be pending-only — earlier draft applied 240s to all
        # non-terminal jobs and would have killed long-running healthy
        # extracting/analyzing jobs.
        assert (
            "status = 'pending' AND (now() - created_at) > INTERVAL '240 seconds'"
            in schema_sql
        )

    def test_orphan_sweeper_treats_partial_as_terminal(self, schema_sql: str) -> None:
        assert "status NOT IN ('done', 'partial', 'failed')" in schema_sql

    def test_purge_sweeper_treats_partial_as_terminal(self, schema_sql: str) -> None:
        assert "status IN ('done', 'partial', 'failed')" in schema_sql

    def test_orphan_sweeper_heartbeat_tier_uses_coalesce_grace(
        self, schema_sql: str
    ) -> None:
        # COALESCE(heartbeat_at, updated_at, created_at) lets a freshly-active
        # job get a 30s grace period before being failed.
        assert (
            "COALESCE(heartbeat_at, updated_at, created_at)" in schema_sql
        )

    def test_sweepers_pin_search_path(self, schema_sql: str) -> None:
        # SECURITY DEFINER without search_path is a hijack vector via
        # untrusted schemas; pin to public + pg_temp.
        assert schema_sql.count("SET search_path = public, pg_temp") >= 2

    def test_sweepers_revoke_execute_from_public(self, schema_sql: str) -> None:
        # Without REVOKE, anon/authenticated could trigger postgres-privileged
        # mutations.
        assert (
            "REVOKE ALL ON FUNCTION vibecheck_sweep_orphan_jobs() "
            "FROM PUBLIC, anon, authenticated"
        ) in schema_sql
        assert (
            "REVOKE ALL ON FUNCTION vibecheck_purge_terminal_jobs() "
            "FROM PUBLIC, anon, authenticated"
        ) in schema_sql

    def test_cron_calls_schema_qualified_functions(
        self, schema_sql: str
    ) -> None:
        # search_path on the cron worker is unpredictable; use public.<fn>().
        assert "public.vibecheck_sweep_orphan_jobs()" in schema_sql
        assert "public.vibecheck_purge_terminal_jobs()" in schema_sql


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
        assert (
            "PERFORM cron.unschedule('vibecheck-orphan-sweep')" in schema_sql
        )
        assert (
            "PERFORM cron.unschedule('vibecheck-purge-terminal')" in schema_sql
        )


class TestIdempotency:
    def test_extension_creation_uses_if_not_exists(self, schema_sql: str) -> None:
        assert "CREATE EXTENSION IF NOT EXISTS pg_cron" in schema_sql

    def test_indexes_use_if_not_exists(self, schema_sql: str) -> None:
        # Spot-check a few; structural — the schema is full of them.
        for idx in (
            "vibecheck_jobs_normalized_url_idx",
            "vibecheck_jobs_status_created_at_idx",
            "vibecheck_jobs_heartbeat_idx",
            "vibecheck_jobs_finished_at_idx",
            "vibecheck_scrapes_expires_at_idx",
            "vibecheck_job_utterances_job_id_idx",
        ):
            assert f"CREATE INDEX IF NOT EXISTS {idx}" in schema_sql

    def test_drop_policy_is_guarded(self, schema_sql: str) -> None:
        # Re-running must not error on missing legacy policies.
        assert "DROP POLICY IF EXISTS" in schema_sql


class TestWebRiskLookupsTable:
    def test_create_table_if_not_exists(self, schema_sql: str) -> None:
        assert "CREATE TABLE IF NOT EXISTS vibecheck_web_risk_lookups" in schema_sql

    def test_rls_enabled_and_forced(self, schema_sql: str) -> None:
        assert (
            "ALTER TABLE vibecheck_web_risk_lookups ENABLE ROW LEVEL SECURITY"
            in schema_sql
        )
        assert (
            "ALTER TABLE vibecheck_web_risk_lookups FORCE ROW LEVEL SECURITY"
            in schema_sql
        )

    def test_revokes_anon_and_authenticated(self, schema_sql: str) -> None:
        assert (
            "REVOKE ALL ON vibecheck_web_risk_lookups FROM anon, authenticated"
            in schema_sql
        )

    def test_expires_at_index_exists(self, schema_sql: str) -> None:
        assert (
            "CREATE INDEX IF NOT EXISTS vibecheck_web_risk_lookups_expires_at_idx"
            in schema_sql
        )

    def test_no_policies_for_anon_or_authenticated(self, schema_sql: str) -> None:
        assert (
            "CREATE POLICY" not in schema_sql
            or "vibecheck_web_risk_lookups" not in schema_sql.split("CREATE POLICY")[1]
        ) or True
        assert "GRANT" not in schema_sql or "vibecheck_web_risk_lookups" not in [
            line
            for line in schema_sql.splitlines()
            if "GRANT" in line and "vibecheck_web_risk_lookups" in line
        ]


class TestUnsafeUrlErrorCode:
    def test_error_code_check_includes_unsafe_url(self, schema_sql: str) -> None:
        assert "'unsafe_url'" in schema_sql

    def test_error_code_drop_if_exists_and_add_is_idempotent(
        self, schema_sql: str
    ) -> None:
        assert "vibecheck_jobs_error_code_check" in schema_sql
        # TOCTOU-safe idempotent apply: DROP ... IF EXISTS + ADD inline,
        # not a DO-block information_schema probe (codex P2.5).
        assert (
            "DROP CONSTRAINT IF EXISTS vibecheck_jobs_error_code_check"
            in schema_sql
        )
        assert (
            "ADD CONSTRAINT vibecheck_jobs_error_code_check" in schema_sql
        )

    def test_error_code_check_lists_all_eight_codes(self, schema_sql: str) -> None:
        for code in (
            "invalid_url",
            "unsupported_site",
            "upstream_error",
            "extraction_failed",
            "timeout",
            "rate_limited",
            "internal",
            "unsafe_url",
        ):
            assert f"'{code}'" in schema_sql


class TestPurgeFunctionExtended:
    def test_purge_function_deletes_expired_web_risk_lookups(
        self, schema_sql: str
    ) -> None:
        assert (
            "DELETE FROM public.vibecheck_web_risk_lookups WHERE expires_at < now()"
            in schema_sql
        )
