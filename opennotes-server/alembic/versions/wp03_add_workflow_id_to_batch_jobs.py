"""WP03: Add workflow_id to batch_jobs table

Add workflow_id column to batch_jobs table for linking DBOS workflows
to BatchJob records. This enables API compatibility during the
TaskIQ → DBOS migration.

Revision ID: wp03_workflow_id
Revises: c1bd549e69ec
Create Date: 2026-01-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "wp03_workflow_id"
down_revision: str | Sequence[str] | None = "c1bd549e69ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batch_jobs",
        sa.Column("workflow_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_batch_jobs_workflow_id"),
        "batch_jobs",
        ["workflow_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_batch_jobs_workflow_id"), table_name="batch_jobs")
    op.drop_column("batch_jobs", "workflow_id")
