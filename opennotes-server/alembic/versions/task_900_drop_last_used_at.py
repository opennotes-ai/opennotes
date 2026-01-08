"""Drop last_used_at column from api_keys table

Revision ID: task_900_001
Revises: task_poi_001
Create Date: 2026-01-07 16:00:00.000000

The last_used_at field was causing 504 timeouts under database load because
updating it required a synchronous database write on every API key verification.

This telemetry is now published as a fire-and-forget NATS event instead,
removing the database write from the critical request path.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task_900_001"
down_revision: str | Sequence[str] | None = "task_poi_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the last_used_at column from api_keys table."""
    op.drop_column("api_keys", "last_used_at")


def downgrade() -> None:
    """Restore the last_used_at column to api_keys table."""
    op.add_column(
        "api_keys",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
