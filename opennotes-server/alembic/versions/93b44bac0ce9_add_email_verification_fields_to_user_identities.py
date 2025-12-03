"""add email verification fields to user identities

Revision ID: 93b44bac0ce9
Revises: jr6tfrxtvuut
Create Date: 2025-10-30 18:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "93b44bac0ce9"
down_revision: str | Sequence[str] | None = "jr6tfrxtvuut"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_identities",
        sa.Column("email_verified", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "user_identities",
        sa.Column("email_verification_token", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "user_identities",
        sa.Column("email_verification_token_expires", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        op.f("idx_user_identities_email_verified"),
        "user_identities",
        ["email_verified"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("idx_user_identities_email_verified"), table_name="user_identities")
    op.drop_column("user_identities", "email_verification_token_expires")
    op.drop_column("user_identities", "email_verification_token")
    op.drop_column("user_identities", "email_verified")
