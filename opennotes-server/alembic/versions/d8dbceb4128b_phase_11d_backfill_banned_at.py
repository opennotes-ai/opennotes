"""phase_11d_backfill_banned_at

Revision ID: d8dbceb4128b
Revises: f9a7af9edcf4
Create Date: 2026-04-15 20:45:46.838168

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8dbceb4128b"
down_revision: str | Sequence[str] | None = "f9a7af9edcf4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE users u
           SET banned_at = p.banned_at,
               ban_reason = p.banned_reason
          FROM user_identities ui
          JOIN user_profiles p ON p.id = ui.profile_id
         WHERE p.is_banned = TRUE
           AND u.banned_at IS NULL
           AND (
             (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
             (ui.provider = 'email'   AND ui.provider_user_id = u.email)
           )
    """)


def downgrade() -> None:
    pass
