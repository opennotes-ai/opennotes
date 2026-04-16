"""phase_16_drop_replaced_columns

Revision ID: f7ee12c696d5
Revises: 9214033f36bf
Create Date: 2026-04-15 22:07:41.257647

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7ee12c696d5"
down_revision: str | Sequence[str] | None = "9214033f36bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "is_service_account")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "role")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
    )
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("is_service_account", sa.Boolean(), nullable=False, server_default="false"),
    )
