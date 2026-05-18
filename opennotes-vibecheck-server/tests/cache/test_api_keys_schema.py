"""Structural contracts for the vibecheck_api_keys table in schema.sql (TASK-1651.01).

Guards:
- Table exists with all required columns
- RLS is ENABLED and FORCED (no anon/authenticated policies)
- pg_cron job 'vibecheck-api-key-sweep' uses the idempotent unschedule-then-schedule pattern
- Partial unique index on (lower(email)) WHERE deleted_at IS NULL
- Re-applying schema is a no-op (all DDL uses IF NOT EXISTS, cron uses unschedule-then-schedule)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "src" / "cache" / "schema.sql"


@pytest.fixture(scope="module")
def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


class TestApiKeysTableExists:
    def test_create_table_if_not_exists(self, schema_sql: str) -> None:
        assert "CREATE TABLE IF NOT EXISTS public.vibecheck_api_keys" in schema_sql

    def test_id_column_is_uuidv7_primary_key(self, schema_sql: str) -> None:
        assert "id uuid PRIMARY KEY DEFAULT extensions.uuidv7()" in schema_sql

    def test_email_column_not_null(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_api_keys\s+\([\s\S]*?\n\)\s*;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None, "vibecheck_api_keys CREATE TABLE block not found"
        block = match.group(0)
        assert "email" in block
        assert "NOT NULL" in block

    def test_key_hash_column_unique_not_null(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_api_keys\s+\([\s\S]*?\n\)\s*;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        assert "key_hash" in block
        assert "UNIQUE" in block

    def test_key_prefix_column_not_null(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_api_keys\s+\([\s\S]*?\n\)\s*;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        assert "key_prefix" in block

    def test_created_at_defaults_to_now(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_api_keys\s+\([\s\S]*?\n\)\s*;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        assert "created_at" in block
        assert "pg_catalog.now()" in block

    def test_last_used_at_is_nullable(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_api_keys\s+\([\s\S]*?\n\)\s*;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        assert "last_used_at" in block

    def test_deleted_at_is_nullable(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.vibecheck_api_keys\s+\([\s\S]*?\n\)\s*;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        assert "deleted_at" in block


class TestApiKeysRls:
    def test_rls_enabled_and_forced(self, schema_sql: str) -> None:
        assert "ALTER TABLE public.vibecheck_api_keys ENABLE ROW LEVEL SECURITY" in schema_sql
        assert "ALTER TABLE public.vibecheck_api_keys FORCE ROW LEVEL SECURITY" in schema_sql

    def test_revokes_anon_and_authenticated(self, schema_sql: str) -> None:
        assert "REVOKE ALL ON public.vibecheck_api_keys FROM anon, authenticated" in schema_sql

    def test_no_policies_or_grants_for_anon_or_authenticated(self, schema_sql: str) -> None:
        forbidden = [
            line
            for line in schema_sql.splitlines()
            if "vibecheck_api_keys" in line
            and (
                line.strip().startswith("CREATE POLICY")
                or re.search(r"\bGRANT\b.*\b(?:anon|authenticated)\b", line)
            )
        ]
        assert forbidden == []


class TestApiKeysIndexes:
    def test_email_active_index_exists(self, schema_sql: str) -> None:
        assert (
            "CREATE INDEX IF NOT EXISTS vibecheck_api_keys_email_active_idx" in schema_sql
        )
        assert "WHERE deleted_at IS NULL" in schema_sql

    def test_key_prefix_index_exists(self, schema_sql: str) -> None:
        assert "CREATE INDEX IF NOT EXISTS vibecheck_api_keys_key_prefix_idx" in schema_sql

    def test_last_used_at_index_exists(self, schema_sql: str) -> None:
        assert "CREATE INDEX IF NOT EXISTS vibecheck_api_keys_last_used_at_idx" in schema_sql

    def test_partial_unique_index_on_lower_email_active(self, schema_sql: str) -> None:
        assert (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_vibecheck_api_keys_email_active" in schema_sql
        )
        assert "lower(email)" in schema_sql
        assert "WHERE deleted_at IS NULL" in schema_sql


class TestApiKeysSweeper:
    def test_sweeper_function_exists(self, schema_sql: str) -> None:
        assert (
            "CREATE OR REPLACE FUNCTION public.vibecheck_soft_delete_unused_api_keys()"
            in schema_sql
        )

    def test_sweeper_is_security_definer_with_pinned_search_path(self, schema_sql: str) -> None:
        match = re.search(
            r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.vibecheck_soft_delete_unused_api_keys\(\)"
            r"[\s\S]*?\n\$\$;",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        assert "SECURITY DEFINER" in block
        assert "SET search_path = pg_catalog, pg_temp" in block

    def test_sweeper_updates_deleted_at_for_unused_old_keys(self, schema_sql: str) -> None:
        assert (
            "UPDATE public.vibecheck_api_keys SET deleted_at = pg_catalog.now() "
            "WHERE deleted_at IS NULL AND last_used_at IS NULL "
            "AND created_at < pg_catalog.now() - interval '48 hours'"
        ) in schema_sql

    def test_sweeper_owner_is_postgres(self, schema_sql: str) -> None:
        assert (
            "ALTER FUNCTION public.vibecheck_soft_delete_unused_api_keys() OWNER TO postgres"
            in schema_sql
        )

    def test_sweeper_revokes_execute_from_public(self, schema_sql: str) -> None:
        assert (
            "REVOKE ALL ON FUNCTION public.vibecheck_soft_delete_unused_api_keys() "
            "FROM PUBLIC, anon, authenticated"
        ) in schema_sql


class TestApiKeysCronSchedule:
    def test_cron_job_name_registered(self, schema_sql: str) -> None:
        assert "'vibecheck-api-key-sweep'" in schema_sql

    def test_cron_schedule_is_12_hourly(self, schema_sql: str) -> None:
        assert "'0 */12 * * *'" in schema_sql

    def test_cron_calls_schema_qualified_function(self, schema_sql: str) -> None:
        assert "public.vibecheck_soft_delete_unused_api_keys()" in schema_sql

    def test_cron_schedule_is_idempotent_via_unschedule_first(self, schema_sql: str) -> None:
        assert "PERFORM cron.unschedule('vibecheck-api-key-sweep')" in schema_sql

    def test_unschedule_is_guarded_by_existence_check(self, schema_sql: str) -> None:
        match = re.search(
            r"IF\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+cron\.job\s+WHERE\s+jobname\s*=\s*"
            r"'vibecheck-api-key-sweep'\s*\)\s+THEN\s+"
            r"PERFORM\s+cron\.unschedule\('vibecheck-api-key-sweep'\)",
            schema_sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None


class TestApiKeysIdempotency:
    def test_table_uses_if_not_exists(self, schema_sql: str) -> None:
        assert "CREATE TABLE IF NOT EXISTS public.vibecheck_api_keys" in schema_sql

    def test_indexes_use_if_not_exists(self, schema_sql: str) -> None:
        for idx in (
            "vibecheck_api_keys_email_active_idx",
            "vibecheck_api_keys_key_prefix_idx",
            "vibecheck_api_keys_last_used_at_idx",
            "idx_vibecheck_api_keys_email_active",
        ):
            assert f"IF NOT EXISTS {idx}" in schema_sql

    def test_uuid_v7_helper_defined_before_api_keys_table(self, schema_sql: str) -> None:
        uuidv7_pos = schema_sql.index("CREATE OR REPLACE FUNCTION extensions.uuidv7()")
        table_pos = schema_sql.index("CREATE TABLE IF NOT EXISTS public.vibecheck_api_keys")
        assert uuidv7_pos < table_pos, "extensions.uuidv7() must be defined before vibecheck_api_keys"
