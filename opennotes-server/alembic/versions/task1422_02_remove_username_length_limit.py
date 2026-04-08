"""remove username 50-char length limit

Revision ID: task1422_02
Revises: task1400_06_06
Create Date: 2026-04-07

This migration is idempotent: it checks the column type before altering.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task1422_02"
down_revision: str | Sequence[str] | None = "task1400_06_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = inspector.get_columns("users")
    username_col = next(c for c in columns if c["name"] == "username")
    if hasattr(username_col["type"], "length") and username_col["type"].length is not None:
        op.alter_column("users", "username", type_=sa.String())


def downgrade() -> None:
    op.alter_column("users", "username", type_=sa.String(50))
