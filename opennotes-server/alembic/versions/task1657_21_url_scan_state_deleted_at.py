"""Add deleted_at column to url_scan_state for on-read soft-delete.

Revision ID: task1657_21
Revises: task1487_03
Create Date: 2026-05-22

TASK-1657.21 ports vibecheck-server PR477 server-side behavior: the poll
handler returns 410 GONE and flips ``deleted_at`` when a job is past its TTL;
the gallery excludes soft-deleted jobs.

DDL is fully idempotent: ``ADD COLUMN IF NOT EXISTS`` ensures re-running the
migration is a no-op. RLS on ``url_scan_state`` is preserved as established
in task1487_03; no new policies are needed because the column inherits the
existing full-access policy for the application role.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task1657_21"
down_revision: str | Sequence[str] | None = "task1487_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("url_scan_state")}
    if "deleted_at" not in existing_cols:
        op.add_column(
            "url_scan_state",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_url_scan_state_deleted_at",
            "url_scan_state",
            ["deleted_at"],
            postgresql_where=sa.text("deleted_at IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("url_scan_state")}
    if "deleted_at" in existing_cols:
        op.drop_index(
            "ix_url_scan_state_deleted_at",
            table_name="url_scan_state",
            if_exists=True,
        )
        op.drop_column("url_scan_state", "deleted_at")
