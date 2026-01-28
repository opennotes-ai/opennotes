"""ratings_consolidate_rater_columns

Revision ID: wp03_001
Revises: 254f9cdd210d
Create Date: 2026-01-27 18:18:00.000000

Consolidate dual rater identity columns (rater_participant_id + rater_profile_id)
into a single rater_id FK column in the ratings table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "wp03_001"
down_revision: str | Sequence[str] | None = "254f9cdd210d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNKNOWN_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Consolidate rater columns into single rater_id FK."""
    # 1. Add new rater_id column (nullable initially)
    op.add_column("ratings", sa.Column("rater_id", UUID(as_uuid=True), nullable=True))

    # 2. Backfill from rater_profile_id first (most reliable)
    op.execute("""
        UPDATE ratings
        SET rater_id = rater_profile_id
        WHERE rater_profile_id IS NOT NULL
          AND rater_id IS NULL
    """)

    # 3. Backfill remaining from participant_id lookup via user_profiles
    op.execute("""
        UPDATE ratings r
        SET rater_id = up.id
        FROM user_profiles up
        WHERE r.rater_participant_id IS NOT NULL
          AND r.rater_id IS NULL
          AND (
            up.discord_id = r.rater_participant_id
            OR up.id::text = r.rater_participant_id
          )
    """)

    # 4. Link remaining orphans to placeholder user
    op.execute(f"""
        UPDATE ratings
        SET rater_id = '{UNKNOWN_USER_ID}'
        WHERE rater_id IS NULL
    """)

    # 5. Make column non-nullable
    op.alter_column("ratings", "rater_id", nullable=False)

    # 6. Add FK constraint with RESTRICT
    op.create_foreign_key(
        "fk_ratings_rater_id",
        "ratings",
        "user_profiles",
        ["rater_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 7. Create new index for rater_id
    op.create_index("ix_ratings_rater_id", "ratings", ["rater_id"])

    # 8. Drop the old unique index on (note_id, rater_participant_id)
    op.drop_index("idx_ratings_note_rater", "ratings")

    # 9. Create new unique index on (note_id, rater_id)
    op.create_index("idx_ratings_note_rater", "ratings", ["note_id", "rater_id"], unique=True)

    # 10. Drop old rater_profile_id index
    op.drop_index("idx_ratings_rater_profile_id", "ratings")

    # 11. Drop old FK constraint on rater_profile_id (if exists)
    # Note: The FK might have different names depending on how it was created
    try:
        op.drop_constraint("ratings_rater_profile_id_fkey", "ratings", type_="foreignkey")
    except Exception:
        pass  # Constraint may not exist or have different name

    # 12. Drop old rater_participant_id index
    op.drop_index("ix_ratings_rater_participant_id", "ratings")

    # 13. Drop old columns
    op.drop_column("ratings", "rater_participant_id")
    op.drop_column("ratings", "rater_profile_id")


def downgrade() -> None:
    """Restore dual rater columns from rater_id."""
    # 1. Add back old columns
    op.add_column(
        "ratings",
        sa.Column("rater_participant_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "ratings",
        sa.Column("rater_profile_id", UUID(as_uuid=True), nullable=True),
    )

    # 2. Copy rater_id to rater_profile_id
    op.execute("""
        UPDATE ratings
        SET rater_profile_id = rater_id
    """)

    # 3. Populate rater_participant_id from user_profiles.discord_id
    op.execute("""
        UPDATE ratings r
        SET rater_participant_id = COALESCE(
            (SELECT discord_id FROM user_profiles WHERE id = r.rater_id),
            'unknown'
        )
    """)

    # 4. Make rater_participant_id non-nullable
    op.alter_column("ratings", "rater_participant_id", nullable=False)

    # 5. Recreate old indexes
    op.create_index("ix_ratings_rater_participant_id", "ratings", ["rater_participant_id"])
    op.create_index("idx_ratings_rater_profile_id", "ratings", ["rater_profile_id"])

    # 6. Recreate old FK for rater_profile_id
    op.create_foreign_key(
        "ratings_rater_profile_id_fkey",
        "ratings",
        "user_profiles",
        ["rater_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 7. Drop new unique index and recreate old one
    op.drop_index("idx_ratings_note_rater", "ratings")
    op.create_index(
        "idx_ratings_note_rater",
        "ratings",
        ["note_id", "rater_participant_id"],
        unique=True,
    )

    # 8. Drop new rater_id index
    op.drop_index("ix_ratings_rater_id", "ratings")

    # 9. Drop new FK constraint
    op.drop_constraint("fk_ratings_rater_id", "ratings", type_="foreignkey")

    # 10. Drop new column
    op.drop_column("ratings", "rater_id")
