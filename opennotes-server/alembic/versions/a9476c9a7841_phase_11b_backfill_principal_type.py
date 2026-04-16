"""phase_11b_backfill_principal_type

Revision ID: a9476c9a7841
Revises: 699549351dd8
Create Date: 2026-04-15 20:45:08.724681

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9476c9a7841"
down_revision: str | Sequence[str] | None = "699549351dd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE users
           SET principal_type = CASE
                 WHEN is_service_account THEN 'agent'
                 ELSE 'human'
               END
         WHERE principal_type IS NULL
    """)


def downgrade() -> None:
    pass
