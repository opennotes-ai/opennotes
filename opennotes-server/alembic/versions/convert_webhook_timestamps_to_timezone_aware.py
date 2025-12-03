"""Convert webhook table timestamps to timezone-aware TIMESTAMPTZ

Revision ID: convert_webhook_timestamps_to_tz
Revises: 175da5e91d70
Create Date: 2025-11-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

revision: str = "convert_webhook_timestamps_to_tz"
down_revision: str | Sequence[str] | None = "175da5e91d70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert 7 TIMESTAMP columns to TIMESTAMPTZ in webhook-related tables.

    Converts:
    - webhooks.created_at
    - webhooks.updated_at
    - interactions.processed_at
    - interactions.created_at
    - tasks.created_at
    - tasks.started_at
    - tasks.completed_at

    Uses AT TIME ZONE 'UTC' to interpret existing TIMESTAMP values as UTC.
    """

    # Webhook table conversions
    op.alter_column(
        "webhooks",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "webhooks",
        "updated_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )

    # Interaction table conversions
    op.alter_column(
        "interactions",
        "processed_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="processed_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "interactions",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # Task table conversions
    op.alter_column(
        "tasks",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "tasks",
        "started_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "tasks",
        "completed_at",
        type_=sa.DateTime(timezone=True),
        existing_type=TIMESTAMP(),
        postgresql_using="completed_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    """Revert 7 TIMESTAMPTZ columns back to TIMESTAMP without timezone.

    Reverts:
    - webhooks.created_at
    - webhooks.updated_at
    - interactions.processed_at
    - interactions.created_at
    - tasks.created_at
    - tasks.started_at
    - tasks.completed_at

    Converts timezone-aware timestamps back to naive UTC timestamps.
    """

    # Webhook table reversions
    op.alter_column(
        "webhooks",
        "created_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "webhooks",
        "updated_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )

    # Interaction table reversions
    op.alter_column(
        "interactions",
        "processed_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="processed_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "interactions",
        "created_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # Task table reversions
    op.alter_column(
        "tasks",
        "created_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "tasks",
        "started_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "tasks",
        "completed_at",
        type_=TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="completed_at AT TIME ZONE 'UTC'",
    )
