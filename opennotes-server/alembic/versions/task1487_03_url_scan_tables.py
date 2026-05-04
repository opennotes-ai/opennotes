"""Create URL scan persistence tables.

Revision ID: task1487_03
Revises: task1444_10
Create Date: 2026-05-04

TASK-1487.03 replaces the old vibecheck in-app ``schema.sql`` tables with
Alembic-owned public tables for URL scan persistence.

Application role / RLS decision:
- The application connects as the username embedded in ``DATABASE_URL``. In
  local dev/test that role is typically ``opennotes`` per ``.env.yaml.example``.
- This migration verifies the connected ``current_user`` at runtime before it
  stamps policies.
- If that role has ``BYPASSRLS``, no table-level allow-all policy is needed.
- If that role does not have ``BYPASSRLS``, the migration creates one policy per
  table named ``<table>_<role>_full_access`` with ``USING (true)`` and
  ``WITH CHECK (true)`` scoped only to that role, while keeping RLS enabled and
  forced on all six tables.

Schema decisions:
- ``url_scan_state`` is a 1:1 child of ``batch_jobs`` and deliberately has no
  ``status`` column and no monolithic ``sections`` JSONB column.
- ``url_scan_section_slots`` stores one row per ``(job_id, slug)`` so section
  writers can compare-and-swap on ``attempt_id`` without cross-slot clobbering.
- ``url_scan_scrapes`` keeps metadata only; markdown/html bodies are not
  migrated here. The newer tier split is preserved with composite key
  ``(normalized_url, tier)`` so Tier 1 and Tier 2 cache rows can coexist.
- The old pg_cron sweepers are intentionally not migrated here; TASK-1487.15
  replaces them with scheduled DBOS workflows.

Idempotency:
- Every table/index create uses ``IF NOT EXISTS``.
- RLS enable/force and role-scoped policy creation are guarded so re-running the
  upgrade is a no-op.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1487_03"
down_revision: str | Sequence[str] | None = "task1444_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

URL_SCAN_TABLES = (
    "url_scan_state",
    "url_scan_section_slots",
    "url_scan_scrapes",
    "url_scan_utterances",
    "url_scan_web_risk_lookups",
    "url_scan_sidebar_cache",
)


def _create_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_state (
            job_id UUID PRIMARY KEY
                REFERENCES public.batch_jobs(id) ON DELETE CASCADE,
            source_url TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            host TEXT NOT NULL,
            attempt_id UUID NOT NULL,
            error_code TEXT,
            error_message TEXT,
            error_host TEXT,
            sidebar_payload JSONB,
            page_title TEXT,
            page_kind TEXT,
            utterance_count INT NOT NULL DEFAULT 0,
            heartbeat_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_section_slots (
            job_id UUID NOT NULL
                REFERENCES public.batch_jobs(id) ON DELETE CASCADE,
            slug TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'PENDING',
            attempt_id UUID NOT NULL,
            data JSONB,
            error_code TEXT,
            error_message TEXT,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            updated_at TIMESTAMPTZ DEFAULT pg_catalog.now(),
            CONSTRAINT url_scan_section_slots_pkey PRIMARY KEY (job_id, slug),
            CONSTRAINT url_scan_section_slots_state_check
                CHECK (state IN ('PENDING', 'RUNNING', 'DONE', 'FAILED'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_scrapes (
            normalized_url TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'scrape',
            source_url TEXT NOT NULL,
            host TEXT NOT NULL,
            page_kind TEXT NOT NULL DEFAULT 'other',
            page_title TEXT,
            screenshot_storage_key TEXT,
            scraped_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            expires_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT url_scan_scrapes_pkey PRIMARY KEY (normalized_url, tier),
            CONSTRAINT url_scan_scrapes_tier_check
                CHECK (tier IN ('scrape', 'interact', 'browser_html'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_utterances (
            job_id UUID NOT NULL
                REFERENCES public.batch_jobs(id) ON DELETE CASCADE,
            utterance_id TEXT NOT NULL,
            payload JSONB NOT NULL,
            CONSTRAINT url_scan_utterances_pkey PRIMARY KEY (job_id, utterance_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_web_risk_lookups (
            normalized_url TEXT PRIMARY KEY,
            findings JSONB NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_sidebar_cache (
            normalized_url TEXT PRIMARY KEY,
            sidebar_payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def _create_indexes() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_state_normalized_url
            ON public.url_scan_state (normalized_url)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_state_heartbeat_at_active
            ON public.url_scan_state (heartbeat_at)
            WHERE finished_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_state_finished_at_terminal
            ON public.url_scan_state (finished_at)
            WHERE finished_at IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_section_slots_job_id_state
            ON public.url_scan_section_slots (job_id, state)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_scrapes_expires_at
            ON public.url_scan_scrapes (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_web_risk_lookups_expires_at
            ON public.url_scan_web_risk_lookups (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_sidebar_cache_expires_at
            ON public.url_scan_sidebar_cache (expires_at)
        """
    )


def _enable_rls_and_role_policy(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        DECLARE
            has_bypass boolean := FALSE;
            role_name text := current_user;
            policy_name text := format('{table_name}_%s_full_access', role_name);
        BEGIN
            IF NOT (
                SELECT relrowsecurity
                  FROM pg_class
                 WHERE oid = 'public.{table_name}'::regclass
            ) THEN
                EXECUTE 'ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY';
            END IF;

            IF NOT (
                SELECT relforcerowsecurity
                  FROM pg_class
                 WHERE oid = 'public.{table_name}'::regclass
            ) THEN
                EXECUTE 'ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY';
            END IF;

            SELECT COALESCE(rolbypassrls, FALSE)
              INTO has_bypass
              FROM pg_roles
             WHERE rolname = role_name;

            IF NOT has_bypass THEN
                IF NOT EXISTS (
                    SELECT 1
                      FROM pg_policies
                     WHERE schemaname = 'public'
                       AND tablename = '{table_name}'
                       AND policyname = policy_name
                ) THEN
                    EXECUTE format(
                        'CREATE POLICY %I ON public.%I FOR ALL TO %I USING (true) WITH CHECK (true)',
                        policy_name,
                        '{table_name}',
                        role_name
                    );
                END IF;
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    _create_tables()
    _create_indexes()
    for table_name in URL_SCAN_TABLES:
        _enable_rls_and_role_policy(table_name)


def downgrade() -> None:
    for table_name in reversed(URL_SCAN_TABLES):
        op.execute(
            f"""
            DO $$
            DECLARE
                role_name text := current_user;
                policy_name text := format('{table_name}_%s_full_access', role_name);
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM pg_policies
                     WHERE schemaname = 'public'
                       AND tablename = '{table_name}'
                       AND policyname = policy_name
                ) THEN
                    EXECUTE format('DROP POLICY %I ON public.%I', policy_name, '{table_name}');
                END IF;
            END
            $$;
            """
        )
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP TABLE IF EXISTS public.url_scan_sidebar_cache")
    op.execute("DROP TABLE IF EXISTS public.url_scan_web_risk_lookups")
    op.execute("DROP TABLE IF EXISTS public.url_scan_utterances")
    op.execute("DROP TABLE IF EXISTS public.url_scan_scrapes")
    op.execute("DROP TABLE IF EXISTS public.url_scan_section_slots")
    op.execute("DROP TABLE IF EXISTS public.url_scan_state")
