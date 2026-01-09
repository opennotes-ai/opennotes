"""task-984.01: Add batch_jobs table

Create batch_jobs table for tracking long-running batch operations.
Provides persistent storage for job status, progress, and error information.

Revision ID: c5d6fa98fac1
Revises: 8669929ca521
Create Date: 2026-01-08 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c5d6fa98fac1"
down_revision: str | Sequence[str] | None = "8669929ca521"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "batch_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("total_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "error_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes - use SQLAlchemy naming convention (ix_tablename_column)
    op.create_index(op.f("ix_batch_jobs_id"), "batch_jobs", ["id"])
    op.create_index(op.f("ix_batch_jobs_job_type"), "batch_jobs", ["job_type"])
    op.create_index(op.f("ix_batch_jobs_status"), "batch_jobs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_batch_jobs_status"), table_name="batch_jobs")
    op.drop_index(op.f("ix_batch_jobs_job_type"), table_name="batch_jobs")
    op.drop_index(op.f("ix_batch_jobs_id"), table_name="batch_jobs")
    op.drop_table("batch_jobs")
