"""task_846_add_bulk_content_scan_log

Revision ID: a37eb031fffa
Revises: 56e80052d351
Create Date: 2025-12-17 17:41:36.851063

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a37eb031fffa"
down_revision: str | Sequence[str] | None = "56e80052d351"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create bulk_content_scan_logs table."""
    op.create_table(
        "bulk_content_scan_logs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("community_server_id", UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("scan_window_days", sa.Integer(), nullable=False),
        sa.Column(
            "initiated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_scanned", sa.Integer(), server_default="0", nullable=False),
        sa.Column("messages_flagged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="in_progress", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["user_profiles.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_bulk_content_scan_logs_id", "bulk_content_scan_logs", ["id"])
    op.create_index(
        "ix_bulk_content_scan_logs_community_server_id",
        "bulk_content_scan_logs",
        ["community_server_id"],
    )
    op.create_index(
        "ix_bulk_content_scan_logs_initiated_by_user_id",
        "bulk_content_scan_logs",
        ["initiated_by_user_id"],
    )
    op.create_index(
        "ix_bulk_content_scan_logs_completed_at", "bulk_content_scan_logs", ["completed_at"]
    )


def downgrade() -> None:
    """Drop bulk_content_scan_logs table."""
    op.drop_index("ix_bulk_content_scan_logs_completed_at", table_name="bulk_content_scan_logs")
    op.drop_index(
        "ix_bulk_content_scan_logs_initiated_by_user_id", table_name="bulk_content_scan_logs"
    )
    op.drop_index(
        "ix_bulk_content_scan_logs_community_server_id", table_name="bulk_content_scan_logs"
    )
    op.drop_index("ix_bulk_content_scan_logs_id", table_name="bulk_content_scan_logs")
    op.drop_table("bulk_content_scan_logs")
