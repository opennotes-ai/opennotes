"""phase_11a_add_principal_taxonomy_columns

Revision ID: 699549351dd8
Revises: task1451_02b
Create Date: 2026-04-15 20:44:50.538699

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "699549351dd8"
down_revision: str | Sequence[str] | None = "task1451_02b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("principal_type", sa.String(), nullable=True))
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_principal_type CHECK (principal_type IN ('human','agent','system'))"
    )
    op.add_column(
        "users", sa.Column("platform_roles", JSONB(), server_default="[]", nullable=False)
    )
    op.add_column("users", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("ban_reason", sa.String(), nullable=True))

    op.create_index("idx_users_principal_type", "users", ["principal_type"])
    op.create_index(
        "idx_users_banned_at",
        "users",
        ["banned_at"],
        postgresql_where=sa.text("banned_at IS NOT NULL"),
    )
    op.create_index(
        "idx_users_platform_roles_gin",
        "users",
        ["platform_roles"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_users_platform_roles_gin", "users")
    op.drop_index("idx_users_banned_at", "users")
    op.drop_index("idx_users_principal_type", "users")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_principal_type")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "banned_at")
    op.drop_column("users", "platform_roles")
    op.drop_column("users", "principal_type")
