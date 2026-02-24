"""task-1145: default dataset_tags to empty array (all datasets)

Change MonitoredChannel.dataset_tags server_default from {snopes} to {} (empty = all datasets).
Migrate existing rows with dataset_tags=['snopes'] to [] so they also search all datasets.

Revision ID: task1145001
Revises: 8a2a91a60527
Create Date: 2026-02-23 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task1145001"
down_revision: str | Sequence[str] | None = "8a2a91a60527"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "monitored_channels",
        "dataset_tags",
        server_default="{}",
    )
    op.execute(
        sa.text("UPDATE monitored_channels SET dataset_tags = '{}' WHERE dataset_tags = '{snopes}'")
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE monitored_channels SET dataset_tags = '{snopes}' WHERE dataset_tags = '{}'")
    )
    op.alter_column(
        "monitored_channels",
        "dataset_tags",
        server_default="{snopes}",
    )
