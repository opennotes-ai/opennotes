"""Fix LLM config timestamps from TIMESTAMP to TIMESTAMPTZ

Fixes the regression from migration 7bc4295d643c which incorrectly downgraded
last_daily_reset and last_monthly_reset from TIMESTAMPTZ to TIMESTAMP (naive).
These columns must be timezone-aware to match datetime.now(UTC) usage in code.

Revision ID: fix_llm_config_tz
Revises: convert_webhook_timestamps_to_tz
Create Date: 2025-11-18 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

revision: str = "fix_llm_config_tz"
down_revision: str | Sequence[str] | None = "convert_webhook_timestamps_to_tz"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert 3 TIMESTAMP columns to TIMESTAMPTZ in LLM config tables.

    Converts:
    - community_server_llm_config.last_daily_reset
    - community_server_llm_config.last_monthly_reset
    - llm_usage_log.timestamp

    Uses AT TIME ZONE 'UTC' to interpret existing TIMESTAMP values as UTC.
    """

    op.alter_column(
        "community_server_llm_config",
        "last_daily_reset",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="last_daily_reset AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "community_server_llm_config",
        "last_monthly_reset",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="last_monthly_reset AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "llm_usage_log",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    """Revert 3 TIMESTAMPTZ columns back to TIMESTAMP without timezone.

    Reverts:
    - community_server_llm_config.last_daily_reset
    - community_server_llm_config.last_monthly_reset
    - llm_usage_log.timestamp

    Converts timezone-aware timestamps back to naive UTC timestamps.
    """

    op.alter_column(
        "llm_usage_log",
        "timestamp",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "community_server_llm_config",
        "last_monthly_reset",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="last_monthly_reset AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "community_server_llm_config",
        "last_daily_reset",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="last_daily_reset AT TIME ZONE 'UTC'",
    )
