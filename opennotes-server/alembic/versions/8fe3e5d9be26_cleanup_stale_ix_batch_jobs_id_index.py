"""Cleanup stale ix_batch_jobs_id index

The original task-984.01 migration created ix_batch_jobs_id, but was later
modified to remove it. This leaves existing databases with a stale index
that the models don't expect, causing schema drift detection failures.

This migration drops the stale index if it exists, making it safe to run
on both affected (has index) and unaffected (no index) databases.

Revision ID: 8fe3e5d9be26
Revises: 37e6e78f25ba
Create Date: 2026-01-12 13:04:27.322863

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8fe3e5d9be26"
down_revision: str | Sequence[str] | None = "37e6e78f25ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop stale ix_batch_jobs_id index if it exists."""
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_batch_jobs_id"))


def downgrade() -> None:
    """No-op: index shouldn't exist per current model definition."""
