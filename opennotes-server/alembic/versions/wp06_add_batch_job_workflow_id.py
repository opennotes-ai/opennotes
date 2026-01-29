"""WP06: Add workflow_id column to batch_jobs table

Add workflow_id column to support DBOS workflow tracking.
The column is nullable to maintain backward compatibility with
existing non-DBOS batch jobs.

Revision ID: a1b2c3d4e5f6
Revises: c1bd549e69ec
Create Date: 2026-01-28 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "wp06a1b2c3d4"
down_revision: str | Sequence[str] | None = "c1bd549e69ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batch_jobs",
        sa.Column(
            "workflow_id",
            sa.String(length=255),
            nullable=True,
            comment="DBOS workflow ID for workflow-backed jobs",
        ),
    )
    op.create_index(
        op.f("ix_batch_jobs_workflow_id"),
        "batch_jobs",
        ["workflow_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_batch_jobs_workflow_id"), table_name="batch_jobs")
    op.drop_column("batch_jobs", "workflow_id")
