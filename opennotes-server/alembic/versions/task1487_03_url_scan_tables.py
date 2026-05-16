"""Create URL scan persistence tables.

Revision ID: task1487_03
Revises: task1444_10
Create Date: 2026-05-04

TASK-1487.03 replaces the old vibecheck in-app ``schema.sql`` tables with
Alembic-owned public tables for URL scan persistence.

Application role / RLS decision:
- The application connects as the username embedded in ``DATABASE_URL``. In
  local dev/test that role is typically ``opennotes`` per ``.env.yaml.example``.
- This migration parses that app role from ``DATABASE_URL`` before it stamps
  any policies. If ``DATABASE_URL`` is absent, it falls back to the migration
  connection's ``current_user`` because no separate app-role signal is
  available in that environment.
- The chosen role is verified against ``pg_roles`` before policy creation.
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

import os
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.engine import make_url

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


def _get_application_role_name(database_url: str | None = None) -> str | None:
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None

    try:
        return make_url(database_url).username
    except Exception as exc:  # pragma: no cover - exact SQLAlchemy exception type is not stable
        raise ValueError(
            "DATABASE_URL could not be parsed to determine the application role"
        ) from exc


def _resolve_application_role_name(bind, database_url: str | None = None) -> str:
    role_name = _get_application_role_name(database_url)
    if role_name:
        return role_name
    return bind.execute(text("SELECT current_user")).scalar_one()


def _ensure_role_exists(bind, role_name: str) -> None:
    role_exists = bind.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role_name)"),
        {"role_name": role_name},
    ).scalar_one()
    if not role_exists:
        raise RuntimeError(f"Application role {role_name!r} does not exist in pg_roles")


def _role_has_bypassrls(bind, role_name: str) -> bool:
    return bind.execute(
        text(
            """
            SELECT COALESCE(rolbypassrls, FALSE)
            FROM pg_roles
            WHERE rolname = :role_name
            """
        ),
        {"role_name": role_name},
    ).scalar_one()


def _policy_exists(bind, table_name: str, role_name: str) -> bool:
    return bind.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = :table_name
                  AND policyname = :policy_name
            )
            """
        ),
        {
            "table_name": table_name,
            "policy_name": _policy_name(table_name, role_name),
        },
    ).scalar_one()


def _quote_identifier(bind, identifier: str) -> str:
    return bind.dialect.identifier_preparer.quote_identifier(identifier)


def _policy_name(table_name: str, role_name: str) -> str:
    return f"{table_name}_{role_name}_full_access"


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


def _enable_rls_and_role_policy(table_name: str, database_url: str | None = None) -> None:
    bind = op.get_bind()
    role_name = _resolve_application_role_name(bind, database_url)
    _ensure_role_exists(bind, role_name)

    op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY")

    if _role_has_bypassrls(bind, role_name):
        return
    if _policy_exists(bind, table_name, role_name):
        return

    quoted_policy_name = _quote_identifier(bind, _policy_name(table_name, role_name))
    quoted_role_name = _quote_identifier(bind, role_name)
    op.execute(
        f"CREATE POLICY {quoted_policy_name} "
        f"ON public.{table_name} FOR ALL TO {quoted_role_name} "
        "USING (true) WITH CHECK (true)"
    )


def _drop_role_policy_for_table(table_name: str, database_url: str | None = None) -> None:
    bind = op.get_bind()
    role_name = _resolve_application_role_name(bind, database_url)
    policy_name = _quote_identifier(bind, _policy_name(table_name, role_name))
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table_name}")


def upgrade() -> None:
    _create_tables()
    _create_indexes()
    for table_name in URL_SCAN_TABLES:
        _enable_rls_and_role_policy(table_name)


def downgrade() -> None:
    for table_name in reversed(URL_SCAN_TABLES):
        _drop_role_policy_for_table(table_name)
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP TABLE IF EXISTS public.url_scan_sidebar_cache")
    op.execute("DROP TABLE IF EXISTS public.url_scan_web_risk_lookups")
    op.execute("DROP TABLE IF EXISTS public.url_scan_utterances")
    op.execute("DROP TABLE IF EXISTS public.url_scan_scrapes")
    op.execute("DROP TABLE IF EXISTS public.url_scan_section_slots")
    op.execute("DROP TABLE IF EXISTS public.url_scan_state")
