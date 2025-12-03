"""Add community_config table for per-community bot configuration

Revision ID: b7e8f9a0b1c2
Revises: a1b2c3d4e5f6
Create Date: 2025-10-23 20:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add community_config table for storing per-community bot configuration."""
    op.create_table(
        "community_config",
        sa.Column("community_id", sa.String(length=64), nullable=False),
        sa.Column("config_key", sa.String(length=128), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("community_id", "config_key"),
    )
    op.create_index(
        op.f("ix_community_config_community_id"), "community_config", ["community_id"], unique=False
    )
    op.create_index(
        op.f("ix_community_config_updated_at"), "community_config", ["updated_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema - remove community_config table."""
    op.drop_index(op.f("ix_community_config_updated_at"), table_name="community_config")
    op.drop_index(op.f("ix_community_config_community_id"), table_name="community_config")
    op.drop_table("community_config")
