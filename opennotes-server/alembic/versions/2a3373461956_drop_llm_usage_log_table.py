"""drop_llm_usage_log_table

Revision ID: 2a3373461956
Revises: 1185d275f39b
Create Date: 2026-03-27 16:54:48.430831

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a3373461956"
down_revision: str | Sequence[str] | None = "1185d275f39b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_llm_usage_community_timestamp", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_provider_timestamp", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_success", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_community_server_id", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_id", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_provider", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_timestamp", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")


def downgrade() -> None:
    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("community_server_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.VARCHAR(length=50), nullable=False),
        sa.Column("model", sa.VARCHAR(length=100), nullable=False),
        sa.Column("tokens_used", sa.INTEGER(), nullable=False),
        sa.Column("success", sa.BOOLEAN(), nullable=False),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "cost_usd",
            sa.NUMERIC(precision=10, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_log_id", "llm_usage_log", ["id"])
    op.create_index(
        "ix_llm_usage_log_community_server_id", "llm_usage_log", ["community_server_id"]
    )
    op.create_index("ix_llm_usage_log_provider", "llm_usage_log", ["provider"])
    op.create_index("ix_llm_usage_log_timestamp", "llm_usage_log", ["timestamp"])
    op.create_index(
        "idx_llm_usage_community_timestamp", "llm_usage_log", ["community_server_id", "timestamp"]
    )
    op.create_index("idx_llm_usage_provider_timestamp", "llm_usage_log", ["provider", "timestamp"])
    op.create_index("idx_llm_usage_success", "llm_usage_log", ["success"])
