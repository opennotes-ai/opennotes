"""fix_workflow_id_unique_constraint

Make workflow_id index unique to match model definition.

Revision ID: fix_workflow_id_unique
Revises: wp01_create_dbos_schema
Create Date: 2026-01-29

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fix_workflow_id_unique"
down_revision: str | Sequence[str] | None = "wp01_create_dbos_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop existing non-unique index
    op.drop_index(op.f("ix_batch_jobs_workflow_id"), table_name="batch_jobs")
    # Recreate with unique=True
    op.create_index(
        op.f("ix_batch_jobs_workflow_id"),
        "batch_jobs",
        ["workflow_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_batch_jobs_workflow_id"), table_name="batch_jobs")
    op.create_index(
        op.f("ix_batch_jobs_workflow_id"),
        "batch_jobs",
        ["workflow_id"],
        unique=False,
    )
