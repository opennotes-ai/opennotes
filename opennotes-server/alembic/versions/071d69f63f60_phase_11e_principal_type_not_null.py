"""phase_11e_principal_type_not_null

Revision ID: 071d69f63f60
Revises: d8dbceb4128b
Create Date: 2026-04-15 20:46:03.526578

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "071d69f63f60"
down_revision: str | Sequence[str] | None = "d8dbceb4128b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Promote to NOT NULL and add server default for new rows.
    # Test fixtures and legacy callers may not set principal_type explicitly;
    # the default "human" matches registration hardening (Phase 1.3).
    op.alter_column(
        "users",
        "principal_type",
        nullable=False,
        server_default=sa.text("'human'"),
        existing_type=sa.String(),
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "principal_type",
        nullable=True,
        server_default=None,
        existing_type=sa.String(),
    )
