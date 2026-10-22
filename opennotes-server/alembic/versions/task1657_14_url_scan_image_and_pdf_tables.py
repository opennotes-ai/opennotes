"""Add url_scan_image_upload_batches and url_scan_pdf_archives tables.

Revision ID: task1657_14
Revises: task1657_07
Create Date: 2026-05-22

TASK-1657.14 ports vibecheck-server PR525 (TASK-1590): image batch upload and
PDF conversion pipeline for the url_scan module.

Table design:
- ``url_scan_image_upload_batches``: tracks ordered source images and
  conversion status for an image-to-PDF job. One row per batch_jobs row.
  UUID v7 surrogate PK (per ADR-001); job_id FK -> batch_jobs.id CASCADE.
  conversion_status CHECK constraint mirrors vibecheck-server schema.
- ``url_scan_pdf_archives``: caches HTML extracted from PDFs so re-analysis
  skips re-extraction. One row per batch_jobs row (unique job_id).
  UUID v7 surrogate PK; job_id FK -> batch_jobs.id CASCADE; TTL via expires_at.

Both tables:
- Use uuidv7() server default for the PK (requires pg_uuidv7 extension,
  already installed for existing tables on this branch).
- RLS enabled + forced; application-role full-access policy created when
  the configured role lacks BYPASSRLS (same pattern as task1657_07).

Idempotency: every table/index/constraint create uses ``IF NOT EXISTS``;
RLS enable/force and policy creation are guarded so re-running is a no-op.

TASK-1657.28 (PDF extract) depends on url_scan_pdf_archives being present.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.engine import make_url

from alembic import op

revision: str = "task1657_14"
down_revision: str | Sequence[str] | None = "task1657_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TABLES = (
    "url_scan_image_upload_batches",
    "url_scan_pdf_archives",
)


def _get_application_role_name(database_url: str | None = None) -> str | None:
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    try:
        return make_url(database_url).username
    except Exception as exc:
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


def _policy_name(table_name: str, role_name: str) -> str:
    return f"{table_name}_{role_name}_full_access"


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


def _create_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_image_upload_batches (
            id UUID PRIMARY KEY DEFAULT uuidv7(),
            job_id UUID NOT NULL REFERENCES public.batch_jobs(id) ON DELETE CASCADE,
            images JSONB NOT NULL,
            conversion_status TEXT NOT NULL DEFAULT 'awaiting_upload',
            generated_pdf_gcs_key TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            CONSTRAINT url_scan_image_upload_batches_status_check
                CHECK (conversion_status IN (
                    'awaiting_upload', 'submitted', 'converting', 'converted', 'failed'
                )),
            CONSTRAINT url_scan_image_upload_batches_images_array_check
                CHECK (pg_catalog.jsonb_typeof(images) = 'array')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.url_scan_pdf_archives (
            id UUID PRIMARY KEY DEFAULT uuidv7(),
            job_id UUID NOT NULL UNIQUE REFERENCES public.batch_jobs(id) ON DELETE CASCADE,
            html TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
            expires_at TIMESTAMPTZ NOT NULL DEFAULT (pg_catalog.now() + INTERVAL '60 days')
        )
        """
    )


def _create_indexes() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_url_scan_image_upload_batches_job_id
            ON public.url_scan_image_upload_batches (job_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_url_scan_pdf_archives_expires_at
            ON public.url_scan_pdf_archives (expires_at)
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
    for table_name in _NEW_TABLES:
        _enable_rls_and_role_policy(table_name)


def downgrade() -> None:
    for table_name in reversed(_NEW_TABLES):
        _drop_role_policy_for_table(table_name)
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS public.{table_name} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP TABLE IF EXISTS public.url_scan_pdf_archives")
    op.execute("DROP TABLE IF EXISTS public.url_scan_image_upload_batches")
