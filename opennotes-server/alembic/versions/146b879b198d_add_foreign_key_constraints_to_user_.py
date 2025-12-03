"""add_foreign_key_constraints_to_user_related_models

Revision ID: 146b879b198d
Revises: jr6tfrxtvuut
Create Date: 2025-10-30 17:05:05.634151

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "146b879b198d"
down_revision: str | Sequence[str] | None = "jr6tfrxtvuut"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add foreign key constraints to user-related models.

    This migration adds foreign key constraints to ensure referential integrity:
    - RefreshToken.user_id -> users.id (CASCADE on delete)
    - APIKey.user_id -> users.id (CASCADE on delete)
    - AuditLog.user_id -> users.id (SET NULL on delete)

    Before applying constraints, we clean up any orphaned records that would
    violate the foreign key constraints.
    """

    op.execute("""
        DELETE FROM refresh_tokens
        WHERE user_id NOT IN (SELECT id FROM users)
    """)

    op.execute("""
        DELETE FROM api_keys
        WHERE user_id NOT IN (SELECT id FROM users)
    """)

    op.execute("""
        UPDATE audit_logs
        SET user_id = NULL
        WHERE user_id IS NOT NULL
        AND user_id NOT IN (SELECT id FROM users)
    """)

    op.create_foreign_key(
        "fk_refresh_tokens_user_id",
        "refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_api_keys_user_id", "api_keys", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    op.create_foreign_key(
        "fk_audit_logs_user_id", "audit_logs", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Remove foreign key constraints from user-related models."""
    op.drop_constraint("fk_audit_logs_user_id", "audit_logs", type_="foreignkey")
    op.drop_constraint("fk_api_keys_user_id", "api_keys", type_="foreignkey")
    op.drop_constraint("fk_refresh_tokens_user_id", "refresh_tokens", type_="foreignkey")
