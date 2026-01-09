"""task-906: Remove duplicate database indexes

Remove 19 duplicate ix_* indexes that have corresponding idx_* indexes.
Each table had both SQLAlchemy auto-generated ix_* indexes (from index=True)
and explicit idx_* indexes defined in __table_args__.

Duplicate indexes by table:
- community_members (6): community_id, profile_id, is_external, role, is_active, joined_at
- community_servers (2): is_active, is_public
- fact_check_items (1): dataset_name
- llm_usage_log (1): success
- notes (1): author_profile_id
- ratings (1): rater_profile_id
- requests (1): message_archive_id
- user_identities (1): profile_id
- user_profiles (5): is_human, is_opennotes_admin, reputation, is_active, is_banned

Revision ID: 906a1b2c3d4e
Revises: 98102a1b2c3d
Create Date: 2025-01-09 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "906a1b2c3d4e"
down_revision: str | Sequence[str] | None = "98102a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop duplicate ix_* indexes (keeping idx_* equivalents)."""
    # community_members (6 duplicates)
    op.drop_index(
        "ix_community_members_community_id", table_name="community_members", if_exists=True
    )
    op.drop_index("ix_community_members_profile_id", table_name="community_members", if_exists=True)
    op.drop_index(
        "ix_community_members_is_external", table_name="community_members", if_exists=True
    )
    op.drop_index("ix_community_members_role", table_name="community_members", if_exists=True)
    op.drop_index("ix_community_members_is_active", table_name="community_members", if_exists=True)
    op.drop_index("ix_community_members_joined_at", table_name="community_members", if_exists=True)

    # community_servers (2 duplicates)
    op.drop_index("ix_community_servers_is_active", table_name="community_servers", if_exists=True)
    op.drop_index("ix_community_servers_is_public", table_name="community_servers", if_exists=True)

    # fact_check_items (1 duplicate)
    op.drop_index("ix_fact_check_items_dataset_name", table_name="fact_check_items", if_exists=True)

    # llm_usage_log (1 duplicate)
    op.drop_index("ix_llm_usage_log_success", table_name="llm_usage_log", if_exists=True)

    # notes (1 duplicate)
    op.drop_index("ix_notes_author_profile_id", table_name="notes", if_exists=True)

    # ratings (1 duplicate)
    op.drop_index("ix_ratings_rater_profile_id", table_name="ratings", if_exists=True)

    # requests (1 duplicate)
    op.drop_index("ix_requests_message_archive_id", table_name="requests", if_exists=True)

    # user_identities (1 duplicate)
    op.drop_index("ix_user_identities_profile_id", table_name="user_identities", if_exists=True)

    # user_profiles (5 duplicates)
    op.drop_index("ix_user_profiles_is_human", table_name="user_profiles", if_exists=True)
    op.drop_index("ix_user_profiles_is_opennotes_admin", table_name="user_profiles", if_exists=True)
    op.drop_index("ix_user_profiles_reputation", table_name="user_profiles", if_exists=True)
    op.drop_index("ix_user_profiles_is_active", table_name="user_profiles", if_exists=True)
    op.drop_index("ix_user_profiles_is_banned", table_name="user_profiles", if_exists=True)


def downgrade() -> None:
    """Recreate the ix_* indexes if needed."""
    # user_profiles (5)
    op.create_index("ix_user_profiles_is_banned", "user_profiles", ["is_banned"], unique=False)
    op.create_index("ix_user_profiles_is_active", "user_profiles", ["is_active"], unique=False)
    op.create_index("ix_user_profiles_reputation", "user_profiles", ["reputation"], unique=False)
    op.create_index(
        "ix_user_profiles_is_opennotes_admin", "user_profiles", ["is_opennotes_admin"], unique=False
    )
    op.create_index("ix_user_profiles_is_human", "user_profiles", ["is_human"], unique=False)

    # user_identities (1)
    op.create_index(
        "ix_user_identities_profile_id", "user_identities", ["profile_id"], unique=False
    )

    # requests (1)
    op.create_index(
        "ix_requests_message_archive_id", "requests", ["message_archive_id"], unique=False
    )

    # ratings (1)
    op.create_index("ix_ratings_rater_profile_id", "ratings", ["rater_profile_id"], unique=False)

    # notes (1)
    op.create_index("ix_notes_author_profile_id", "notes", ["author_profile_id"], unique=False)

    # llm_usage_log (1)
    op.create_index("ix_llm_usage_log_success", "llm_usage_log", ["success"], unique=False)

    # fact_check_items (1)
    op.create_index(
        "ix_fact_check_items_dataset_name", "fact_check_items", ["dataset_name"], unique=False
    )

    # community_servers (2)
    op.create_index(
        "ix_community_servers_is_public", "community_servers", ["is_public"], unique=False
    )
    op.create_index(
        "ix_community_servers_is_active", "community_servers", ["is_active"], unique=False
    )

    # community_members (6)
    op.create_index(
        "ix_community_members_joined_at", "community_members", ["joined_at"], unique=False
    )
    op.create_index(
        "ix_community_members_is_active", "community_members", ["is_active"], unique=False
    )
    op.create_index("ix_community_members_role", "community_members", ["role"], unique=False)
    op.create_index(
        "ix_community_members_is_external", "community_members", ["is_external"], unique=False
    )
    op.create_index(
        "ix_community_members_profile_id", "community_members", ["profile_id"], unique=False
    )
    op.create_index(
        "ix_community_members_community_id", "community_members", ["community_id"], unique=False
    )
