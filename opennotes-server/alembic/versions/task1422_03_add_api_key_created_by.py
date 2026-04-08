"""add created_by_user_id to api_keys

Revision ID: task1422_03
Revises: task1422_02
Create Date: 2026-04-08

This migration is idempotent: checks column existence before adding.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "task1422_03"
down_revision: str | Sequence[str] | None = "task1422_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("api_keys")]
    if "created_by_user_id" not in columns:
        op.add_column(
            "api_keys",
            sa.Column(
                "created_by_user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_api_keys_created_by_user_id",
            "api_keys",
            ["created_by_user_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_api_keys_created_by_user_id", table_name="api_keys")
    op.drop_column("api_keys", "created_by_user_id")
