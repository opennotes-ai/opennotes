"""wp02_notes_consolidate_author_columns

Revision ID: 436c8fc4c0c4
Revises: 254f9cdd210d
Create Date: 2026-01-27 18:18:00.831520

WP02: Consolidate dual author columns (author_participant_id + author_profile_id)
into a single author_id FK column pointing to user_profiles.

Migration strategy:
1. Add author_id column (nullable initially)
2. Backfill from author_profile_id first (direct UUID match)
3. Backfill remaining from participant_id → user_identities lookup
4. Link orphans to placeholder user (00000000-0000-0000-0000-000000000001)
5. Make column non-nullable
6. Add FK constraint with RESTRICT
7. Create index
8. Drop check constraint
9. Drop old columns and indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "436c8fc4c0c4"
down_revision: str | Sequence[str] | None = "254f9cdd210d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLACEHOLDER_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Consolidate notes author columns into single author_id FK."""
    # 1. Add new column as nullable initially
    op.add_column("notes", sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True))

    # 2. Backfill from author_profile_id first (direct UUID)
    op.execute("""
        UPDATE notes
        SET author_id = author_profile_id
        WHERE author_profile_id IS NOT NULL
          AND author_id IS NULL
    """)

    # 3. Backfill remaining from participant_id → user_identities lookup
    op.execute("""
        UPDATE notes n
        SET author_id = ui.profile_id
        FROM user_identities ui
        WHERE n.author_participant_id IS NOT NULL
          AND n.author_id IS NULL
          AND ui.provider_user_id = n.author_participant_id
          AND ui.provider = 'discord'
    """)

    # 4. Link remaining orphans to placeholder user
    op.execute(f"""
        UPDATE notes
        SET author_id = '{PLACEHOLDER_USER_ID}'
        WHERE author_id IS NULL
    """)

    # 5. Make column non-nullable
    op.alter_column("notes", "author_id", nullable=False)

    # 6. Add FK constraint with RESTRICT
    op.create_foreign_key(
        "fk_notes_author_id", "notes", "user_profiles", ["author_id"], ["id"], ondelete="RESTRICT"
    )

    # 7. Create index (only the custom one, not the duplicate)
    op.create_index("idx_notes_author_id", "notes", ["author_id"])

    # 8. Drop check constraint
    op.drop_constraint("ck_notes_author_source", "notes", type_="check")

    # 9. Drop old indexes
    op.drop_index("idx_notes_author_profile_id", table_name="notes", if_exists=True)
    op.drop_index("idx_notes_author_status", table_name="notes", if_exists=True)
    op.drop_index("ix_notes_author_participant_id", table_name="notes", if_exists=True)

    # 10. Drop old FK constraint
    op.drop_constraint("notes_author_profile_id_fkey", "notes", type_="foreignkey")

    # 11. Drop old columns
    op.drop_column("notes", "author_participant_id")
    op.drop_column("notes", "author_profile_id")


def downgrade() -> None:
    """Restore dual author columns from author_id."""
    # 1. Add old columns back
    op.add_column(
        "notes", sa.Column("author_profile_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("notes", sa.Column("author_participant_id", sa.String(255), nullable=True))

    # 2. Copy author_id to author_profile_id
    op.execute("""
        UPDATE notes
        SET author_profile_id = author_id
    """)

    # 3. Populate author_participant_id from user_identities
    op.execute("""
        UPDATE notes n
        SET author_participant_id = COALESCE(
            (SELECT provider_user_id FROM user_identities
             WHERE profile_id = n.author_id AND provider = 'discord'),
            'unknown'
        )
    """)

    # 4. Make author_participant_id non-nullable
    op.alter_column("notes", "author_participant_id", nullable=False)

    # 5. Recreate check constraint
    op.create_check_constraint(
        "ck_notes_author_source",
        "notes",
        "author_participant_id IS NOT NULL OR author_profile_id IS NOT NULL",
    )

    # 6. Recreate old indexes
    op.create_index("ix_notes_author_participant_id", "notes", ["author_participant_id"])
    op.create_index("idx_notes_author_status", "notes", ["author_participant_id", "status"])
    op.create_index("idx_notes_author_profile_id", "notes", ["author_profile_id"])

    # 7. Recreate old FK
    op.create_foreign_key(
        "notes_author_profile_id_fkey",
        "notes",
        "user_profiles",
        ["author_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 8. Drop new FK and index
    op.drop_constraint("fk_notes_author_id", "notes", type_="foreignkey")
    op.drop_index("idx_notes_author_id", table_name="notes")

    # 9. Drop new column
    op.drop_column("notes", "author_id")
