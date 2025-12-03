"""add_rater_profile_id_to_ratings

Revision ID: 0f34e2cd94ca
Revises: 187cc4a55d92
Create Date: 2025-10-29 12:10:45.399061

Adds rater_profile_id column to ratings table to link ratings to user profiles.
This enables multiple authentication methods to link to the same rater identity.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0f34e2cd94ca"
down_revision: str | Sequence[str] | None = "187cc4a55d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add rater_profile_id column to ratings table."""
    op.add_column(
        "ratings", sa.Column("rater_profile_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_ratings_rater_profile_id",
        "ratings",
        "user_profiles",
        ["rater_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_ratings_rater_profile_id", "ratings", ["rater_profile_id"])


def downgrade() -> None:
    """Remove rater_profile_id column from ratings table."""
    op.drop_index("idx_ratings_rater_profile_id", table_name="ratings")
    op.drop_constraint("fk_ratings_rater_profile_id", "ratings", type_="foreignkey")
    op.drop_column("ratings", "rater_profile_id")
