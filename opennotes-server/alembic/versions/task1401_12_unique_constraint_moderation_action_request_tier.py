"""add unique constraint on moderation_actions(request_id, action_tier)

Revision ID: task1401_12
Revises: f718d7324989
Create Date: 2026-04-15

"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1401_12"
down_revision: str | Sequence[str] | None = "f718d7324989"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "uq_moderation_action_request_tier"
TABLE_NAME = "moderation_actions"


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{CONSTRAINT_NAME}'
                  AND conrelid = '{TABLE_NAME}'::regclass
            ) THEN
                ALTER TABLE {TABLE_NAME}
                    ADD CONSTRAINT {CONSTRAINT_NAME}
                    UNIQUE (request_id, action_tier);
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute(f"""
        ALTER TABLE {TABLE_NAME}
            DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};
    """)
