"""task-508: add cost tracking fields for LLM usage

Revision ID: task_508_add_cost_tracking
Revises: b10c6c2da1b8
Create Date: 2025-11-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "task_508_add_cost_tracking"
down_revision: str | Sequence[str] | None = "b10c6c2da1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add cost tracking fields to LLM configuration and usage tables."""
    # Add spending limit fields to community_server_llm_config
    op.add_column(
        "community_server_llm_config",
        sa.Column(
            "daily_spend_limit",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="Daily spending limit in USD",
        ),
    )
    op.add_column(
        "community_server_llm_config",
        sa.Column(
            "monthly_spend_limit",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="Monthly spending limit in USD",
        ),
    )

    # Add current spending counters to community_server_llm_config
    op.add_column(
        "community_server_llm_config",
        sa.Column(
            "current_daily_spend",
            sa.Numeric(precision=10, scale=4),
            nullable=False,
            server_default="0.0000",
            comment="Current daily spend in USD",
        ),
    )
    op.add_column(
        "community_server_llm_config",
        sa.Column(
            "current_monthly_spend",
            sa.Numeric(precision=10, scale=4),
            nullable=False,
            server_default="0.0000",
            comment="Current monthly spend in USD",
        ),
    )

    # Add cost tracking to llm_usage_log
    op.add_column(
        "llm_usage_log",
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0.000000",
            comment="Cost of this API call in USD",
        ),
    )

    # Add check constraints for spending limits
    op.create_check_constraint(
        "ck_llm_config_daily_spend_limit",
        "community_server_llm_config",
        "daily_spend_limit IS NULL OR daily_spend_limit > 0",
    )
    op.create_check_constraint(
        "ck_llm_config_monthly_spend_limit",
        "community_server_llm_config",
        "monthly_spend_limit IS NULL OR monthly_spend_limit > 0",
    )


def downgrade() -> None:
    """Remove cost tracking fields from LLM configuration and usage tables."""
    # Drop check constraints
    op.drop_constraint(
        "ck_llm_config_monthly_spend_limit", "community_server_llm_config", type_="check"
    )
    op.drop_constraint(
        "ck_llm_config_daily_spend_limit", "community_server_llm_config", type_="check"
    )

    # Drop columns from llm_usage_log
    op.drop_column("llm_usage_log", "cost_usd")

    # Drop columns from community_server_llm_config
    op.drop_column("community_server_llm_config", "current_monthly_spend")
    op.drop_column("community_server_llm_config", "current_daily_spend")
    op.drop_column("community_server_llm_config", "monthly_spend_limit")
    op.drop_column("community_server_llm_config", "daily_spend_limit")
