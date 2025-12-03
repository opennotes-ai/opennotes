"""add_community_server_llm_config

Add tables for per-community-server LLM provider API key configuration.
Enables community servers to configure their own OpenAI, Anthropic, or other
LLM providers with encrypted API keys and usage tracking.

Revision ID: 94badc57d821
Revises: d12b267754d2
Create Date: 2025-10-29 11:36:53.470546

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94badc57d821"
down_revision: str | Sequence[str] | None = "d12b267754d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add community_servers, community_server_llm_config, and llm_usage_log tables."""

    # Create community_servers table
    op.create_table(
        "community_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("platform_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "platform IN ('discord', 'reddit', 'slack', 'matrix', 'discourse', 'other')",
            name="ck_community_servers_platform",
        ),
    )
    op.create_index("idx_community_servers_id", "community_servers", ["id"])
    op.create_index("idx_community_servers_platform", "community_servers", ["platform"])
    op.create_index("idx_community_servers_platform_id", "community_servers", ["platform_id"])
    op.create_index(
        "idx_community_servers_platform_id_unique",
        "community_servers",
        ["platform", "platform_id"],
        unique=True,
    )
    op.create_index("idx_community_servers_is_active", "community_servers", ["is_active"])
    op.create_index("idx_community_servers_created_at", "community_servers", ["created_at"])

    # Create community_server_llm_config table
    op.create_table(
        "community_server_llm_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("community_server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("daily_request_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_request_limit", sa.Integer(), nullable=True),
        sa.Column("daily_token_limit", sa.BigInteger(), nullable=True),
        sa.Column("monthly_token_limit", sa.BigInteger(), nullable=True),
        sa.Column("current_daily_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_monthly_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_daily_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("current_monthly_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_daily_reset", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_monthly_reset", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'google', 'cohere', 'custom')",
            name="ck_llm_config_provider",
        ),
        sa.CheckConstraint(
            "daily_request_limit IS NULL OR daily_request_limit > 0",
            name="ck_llm_config_daily_request_limit",
        ),
        sa.CheckConstraint(
            "monthly_request_limit IS NULL OR monthly_request_limit > 0",
            name="ck_llm_config_monthly_request_limit",
        ),
        sa.CheckConstraint(
            "daily_token_limit IS NULL OR daily_token_limit > 0",
            name="ck_llm_config_daily_token_limit",
        ),
        sa.CheckConstraint(
            "monthly_token_limit IS NULL OR monthly_token_limit > 0",
            name="ck_llm_config_monthly_token_limit",
        ),
    )
    op.create_index("idx_llm_config_id", "community_server_llm_config", ["id"])
    op.create_index(
        "idx_llm_config_community_server_id", "community_server_llm_config", ["community_server_id"]
    )
    op.create_index("idx_llm_config_provider", "community_server_llm_config", ["provider"])
    op.create_index(
        "idx_llm_config_community_provider",
        "community_server_llm_config",
        ["community_server_id", "provider"],
        unique=True,
    )
    op.create_index(
        "idx_llm_config_enabled", "community_server_llm_config", ["community_server_id", "enabled"]
    )
    op.create_index("idx_llm_config_created_at", "community_server_llm_config", ["created_at"])

    # Create llm_usage_log table
    op.create_table(
        "llm_usage_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("community_server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("idx_llm_usage_id", "llm_usage_log", ["id"])
    op.create_index("idx_llm_usage_community_server_id", "llm_usage_log", ["community_server_id"])
    op.create_index("idx_llm_usage_provider", "llm_usage_log", ["provider"])
    op.create_index("idx_llm_usage_success", "llm_usage_log", ["success"])
    op.create_index("idx_llm_usage_timestamp", "llm_usage_log", ["timestamp"])
    op.create_index(
        "idx_llm_usage_community_timestamp", "llm_usage_log", ["community_server_id", "timestamp"]
    )
    op.create_index("idx_llm_usage_provider_timestamp", "llm_usage_log", ["provider", "timestamp"])


def downgrade() -> None:
    """Remove LLM configuration tables."""

    # Drop llm_usage_log table
    op.drop_index("idx_llm_usage_provider_timestamp", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_community_timestamp", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_timestamp", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_success", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_provider", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_community_server_id", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_id", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")

    # Drop community_server_llm_config table
    op.drop_index("idx_llm_config_created_at", table_name="community_server_llm_config")
    op.drop_index("idx_llm_config_enabled", table_name="community_server_llm_config")
    op.drop_index("idx_llm_config_community_provider", table_name="community_server_llm_config")
    op.drop_index("idx_llm_config_provider", table_name="community_server_llm_config")
    op.drop_index("idx_llm_config_community_server_id", table_name="community_server_llm_config")
    op.drop_index("idx_llm_config_id", table_name="community_server_llm_config")
    op.drop_table("community_server_llm_config")

    # Drop community_servers table
    op.drop_index("idx_community_servers_created_at", table_name="community_servers")
    op.drop_index("idx_community_servers_is_active", table_name="community_servers")
    op.drop_index("idx_community_servers_platform_id_unique", table_name="community_servers")
    op.drop_index("idx_community_servers_platform_id", table_name="community_servers")
    op.drop_index("idx_community_servers_platform", table_name="community_servers")
    op.drop_index("idx_community_servers_id", table_name="community_servers")
    op.drop_table("community_servers")
