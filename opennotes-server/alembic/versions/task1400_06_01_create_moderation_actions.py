"""create moderation_actions table

Revision ID: task1400_06_01
Revises: b58738457bfb
Create Date: 2026-03-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "task1400_06_01"
down_revision: str | Sequence[str] | None = "b58738457bfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moderation_actions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", UUID(as_uuid=True), nullable=True),
        sa.Column("community_server_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("action_tier", sa.String(50), nullable=False),
        sa.Column(
            "action_state", sa.String(50), server_default=sa.text("'proposed'"), nullable=False
        ),
        sa.Column("review_group", sa.String(50), nullable=False),
        sa.Column("classifier_evidence", JSONB, nullable=True),
        sa.Column("platform_action_id", sa.String(255), nullable=True),
        sa.Column("scan_exempt_content_hash", sa.String(255), nullable=True),
        sa.Column("overturned_reason", sa.String(1000), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overturned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="RESTRICT"
        ),
    )

    op.create_index("ix_moderation_actions_id", "moderation_actions", ["id"])
    op.create_index("ix_moderation_actions_request_id", "moderation_actions", ["request_id"])
    op.create_index("ix_moderation_actions_note_id", "moderation_actions", ["note_id"])
    op.create_index(
        "ix_moderation_actions_community_state",
        "moderation_actions",
        ["community_server_id", "action_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_actions_community_state", table_name="moderation_actions")
    op.drop_index("ix_moderation_actions_note_id", table_name="moderation_actions")
    op.drop_index("ix_moderation_actions_request_id", table_name="moderation_actions")
    op.drop_index("ix_moderation_actions_id", table_name="moderation_actions")
    op.drop_table("moderation_actions")
