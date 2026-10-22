"""Add url_scan_image_analysis_cache and url_scan_video_analysis_cache tables.

Revision ID: task1657_07
Revises: task1657_21
Create Date: 2026-05-22

TASK-1657.07 ports vibecheck-server PR497 + PR504: per-URL caching of Vision
API SafeSearch results (image) and frame findings (video). Storing results by
URL avoids redundant Vertex calls for the same media across multiple scans.

Table design:
- ``url_scan_image_analysis_cache``: one row per image URL; stores the full
  SafeSearchResult dataclass payload as JSONB.
- ``url_scan_video_analysis_cache``: one row per video URL; stores a list of
  FrameFinding payloads as JSONB.

Both tables:
- Use TEXT primary key (the URL) rather than a surrogate UUID because the
  lookup key is always the normalized URL.
- TTL-based expiry enforced by the ``expires_at`` column; stale rows are
  purged by the existing ``url_scan_purge_expired_data_workflow``.
- RLS enabled + forced; application-role full-access policy created when
  the configured role lacks BYPASSRLS (same pattern as task1487_03).

Idempotency: every table/index create uses ``IF NOT EXISTS``; RLS and policy
creation are guarded so re-running the upgrade is a no-op.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.engine import make_url

from alembic import op

revision: str = "task1657_07"
down_revision: str | Sequence[str] | None = "task1657_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VISION_CACHE_TABLES = (
    "url_scan_image_analysis_cache",
    "url_scan_video_analysis_cache",
)


def _get_application_role_name(database_url: str | None = None) -> str | None:
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    try:
        return make_url(database_url).username
    except Exception as exc:  # pragma: no cover
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
        CREATE TABLE IF NOT EXISTS public.url_scan_image_analysis_cache (
            image_url TEXT PRIMARY KEY,
            result_payload JSONB NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_video_analysis_cache (
            video_url TEXT PRIMARY KEY,
            frame_findings_payload JSONB NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def _create_indexes() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_image_analysis_cache_expires_at
            ON public.url_scan_image_analysis_cache (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_video_analysis_cache_expires_at
            ON public.url_scan_video_analysis_cache (expires_at)
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
    for table_name in _VISION_CACHE_TABLES:
        _enable_rls_and_role_policy(table_name)


def downgrade() -> None:
    for table_name in reversed(_VISION_CACHE_TABLES):
        _drop_role_policy_for_table(table_name)
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP TABLE IF EXISTS public.url_scan_video_analysis_cache")
    op.execute("DROP TABLE IF EXISTS public.url_scan_image_analysis_cache")
