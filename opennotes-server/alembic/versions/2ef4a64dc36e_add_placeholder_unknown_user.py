"""add_placeholder_unknown_user

Revision ID: 2ef4a64dc36e
Revises: c1bd549e69ec
Create Date: 2026-01-27 17:47:41.959920

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2ef4a64dc36e"
down_revision: str | Sequence[str] | None = "c1bd549e69ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNKNOWN_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Insert placeholder user profile for orphaned records."""
    op.execute(f"""
        INSERT INTO user_profiles (id, display_name, is_human, is_active, created_at, updated_at)
        VALUES (
            '{UNKNOWN_USER_ID}',
            '[Unknown User]',
            false,
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    """Remove placeholder user only if no records reference it."""
    op.execute(f"""
        DELETE FROM user_profiles
        WHERE id = '{UNKNOWN_USER_ID}'
        AND NOT EXISTS (SELECT 1 FROM notes WHERE author_id = '{UNKNOWN_USER_ID}')
        AND NOT EXISTS (SELECT 1 FROM ratings WHERE rater_id = '{UNKNOWN_USER_ID}')
    """)
