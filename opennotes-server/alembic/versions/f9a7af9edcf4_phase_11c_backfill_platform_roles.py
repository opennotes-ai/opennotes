"""phase_11c_backfill_platform_roles

Revision ID: f9a7af9edcf4
Revises: a9476c9a7841
Create Date: 2026-04-15 20:45:28.538788

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9a7af9edcf4"
down_revision: str | Sequence[str] | None = "a9476c9a7841"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE users u
           SET platform_roles = '["platform_admin"]'::jsonb
          FROM user_identities ui
          JOIN user_profiles p ON p.id = ui.profile_id
         WHERE p.is_opennotes_admin = TRUE
           AND (
             (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
             (ui.provider = 'email'   AND ui.provider_user_id = u.email)
           )
           AND NOT (u.platform_roles @> '["platform_admin"]'::jsonb)
    """)


def downgrade() -> None:
    pass
