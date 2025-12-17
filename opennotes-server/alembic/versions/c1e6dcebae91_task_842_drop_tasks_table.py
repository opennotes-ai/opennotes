"""task_842_drop_tasks_table

Revision ID: c1e6dcebae91
Revises: e304e0f3f0e1
Create Date: 2025-12-17 12:18:55.013682

Drop the tasks table that was part of the TaskQueue webhook infrastructure
removed in task-840 (commit 0894b66).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "c1e6dcebae91"
down_revision: str | Sequence[str] | None = "e304e0f3f0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the tasks table and its indexes."""
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_interaction_id", table_name="tasks")
    op.drop_index("ix_tasks_task_id", table_name="tasks")
    op.drop_index("ix_tasks_id", table_name="tasks")
    op.drop_table("tasks")


def downgrade() -> None:
    """Recreate the tasks table with UUID v7 primary key."""
    op.create_table(
        "tasks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("interaction_id", sa.String(length=50), nullable=False),
        sa.Column("interaction_token", sa.String(length=200), nullable=False),
        sa.Column("application_id", sa.String(length=50), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("task_data", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_id", "tasks", ["id"], unique=False)
    op.create_index("ix_tasks_task_id", "tasks", ["task_id"], unique=True)
    op.create_index("ix_tasks_interaction_id", "tasks", ["interaction_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"], unique=False)
