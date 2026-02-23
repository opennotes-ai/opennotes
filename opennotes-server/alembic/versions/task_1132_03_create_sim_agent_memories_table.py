"""task-1132.03: create sim_agent_memories table

Revision ID: 7a3b4c5d6e7f
Revises: 5cf98a2d1250
Create Date: 2026-02-21 12:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7a3b4c5d6e7f"
down_revision: str | Sequence[str] | None = "5cf98a2d1250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sim_agent_memories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "agent_instance_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "message_history",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "turn_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "last_compacted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "compaction_strategy",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
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
    op.create_index(op.f("ix_sim_agent_memories_id"), "sim_agent_memories", ["id"])
    op.create_index(
        "idx_sim_agent_memories_agent_instance_id",
        "sim_agent_memories",
        ["agent_instance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_sim_agent_memories_agent_instance_id",
        table_name="sim_agent_memories",
    )
    op.drop_index(op.f("ix_sim_agent_memories_id"), table_name="sim_agent_memories")
    op.drop_table("sim_agent_memories")
