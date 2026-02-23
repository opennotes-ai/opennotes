"""task-1132.02: create opennotes_sim_agents table

Revision ID: 5cf98a2d1250
Revises: 52df7eba1d88
Create Date: 2026-02-21 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "5cf98a2d1250"
down_revision: str | Sequence[str] | None = "52df7eba1d88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opennotes_sim_agents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("personality", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column(
            "model_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "tool_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "memory_compaction_strategy",
            sa.String(length=50),
            server_default="sliding_window",
            nullable=False,
        ),
        sa.Column(
            "memory_compaction_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["community_server_id"],
            ["community_servers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_opennotes_sim_agents_id"), "opennotes_sim_agents", ["id"])
    op.create_index(
        op.f("ix_opennotes_sim_agents_community_server_id"),
        "opennotes_sim_agents",
        ["community_server_id"],
    )
    op.create_index("idx_sim_agents_deleted_at", "opennotes_sim_agents", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_sim_agents_deleted_at", table_name="opennotes_sim_agents")
    op.drop_index(
        op.f("ix_opennotes_sim_agents_community_server_id"),
        table_name="opennotes_sim_agents",
    )
    op.drop_index(op.f("ix_opennotes_sim_agents_id"), table_name="opennotes_sim_agents")
    op.drop_table("opennotes_sim_agents")
