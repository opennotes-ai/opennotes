"""Migrate legacy models from integer PKs to UUID v7

Revision ID: task_576
Revises: 7ba8a8f5d894
Create Date: 2025-11-12 12:00:00.000000

This migration converts the following tables from integer/bigint primary keys to UUID v7:
1. users (int -> UUID)
2. refresh_tokens (int -> UUID, user_id int -> UUID)
3. api_keys (int -> UUID, user_id int -> UUID)
4. audit_logs (int -> UUID)
5. notes (int -> UUID, removes note_id field)
6. ratings (int -> UUID, note_id BigInteger -> UUID)
7. requests (int -> UUID, note_id BigInteger -> UUID)
8. note_publisher_posts (int -> UUID, note_id BigInteger -> UUID)
9. previously_seen_messages (published_note_id BigInteger -> UUID)

Strategy:
- Drop dependent tables in reverse order
- Recreate with UUID v7 primary keys
- Use server_default=uuidv7() for auto-generation
- Restore all foreign key relationships

This is a destructive migration appropriate for development only.
No data preservation since we're in development environment.

Migration is reversible through downgrade() function.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "task_576"
down_revision: str | Sequence[str] | None = "7ba8a8f5d894"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate all tables to UUID v7 primary keys."""

    # ===================================================================
    # PHASE 0: Remove FK constraint from community_config to users
    # ===================================================================
    # community_config.updated_by references users.id but it's Integer
    # This table is not being migrated, so we need to handle it separately
    # Use raw SQL with IF EXISTS to handle cases where constraint may not exist
    op.execute(
        "ALTER TABLE community_config DROP CONSTRAINT IF EXISTS fk_community_config_updated_by_users_id"
    )

    # ===================================================================
    # PHASE 1: Drop dependent tables (in reverse dependency order)
    # ===================================================================
    # Drop tables that reference notes or other tables first
    # Using IF EXISTS to handle cases where tables may not exist

    # Drop note_publisher_posts (references notes)
    op.execute("DROP TABLE IF EXISTS note_publisher_posts CASCADE")

    # Drop previously_seen_messages (references notes)
    op.execute("DROP TABLE IF EXISTS previously_seen_messages CASCADE")

    # Drop ratings (references notes)
    op.execute("DROP TABLE IF EXISTS ratings CASCADE")

    # Drop api_keys and refresh_tokens (reference users)
    op.execute("DROP TABLE IF EXISTS api_keys CASCADE")
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE")

    # Drop audit_logs (references users)
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")

    # Drop notes table (has FK to requests)
    op.execute("DROP TABLE IF EXISTS notes CASCADE")

    # Drop requests (after notes because notes references requests via request_id)
    op.execute("DROP TABLE IF EXISTS requests CASCADE")

    # Drop users table
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    # ===================================================================
    # PHASE 1.5: Drop ENUM types
    # ===================================================================
    # CASCADE from table drops should automatically remove dependent enums.
    # However, explicitly drop them to ensure clean slate for recreation.
    # This must be done AFTER all tables using these enums are dropped.
    op.execute("DROP TYPE IF EXISTS note_classification CASCADE")
    op.execute("DROP TYPE IF EXISTS note_status CASCADE")
    op.execute("DROP TYPE IF EXISTS helpfulness_level CASCADE")
    op.execute("DROP TYPE IF EXISTS request_status CASCADE")

    # ===================================================================
    # PHASE 1.6: Recreate ENUM types
    # ===================================================================
    # Recreate ENUM types BEFORE creating tables that use them
    op.execute(
        "CREATE TYPE note_classification AS ENUM ('NOT_MISLEADING', 'MISINFORMED_OR_POTENTIALLY_MISLEADING')"
    )
    op.execute(
        "CREATE TYPE note_status AS ENUM ('NEEDS_MORE_RATINGS', 'CURRENTLY_RATED_HELPFUL', 'CURRENTLY_RATED_NOT_HELPFUL')"
    )
    op.execute(
        "CREATE TYPE helpfulness_level AS ENUM ('HELPFUL', 'SOMEWHAT_HELPFUL', 'NOT_HELPFUL')"
    )
    op.execute(
        "CREATE TYPE request_status AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')"
    )

    # ===================================================================
    # PHASE 2: Recreate parent tables with UUID v7 PKs
    # ===================================================================

    # Recreate users table with UUID v7 PK
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_service_account", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("discord_id", sa.String(100), nullable=True),
        sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("discord_id", name="uq_users_discord_id"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_discord_id", "users", ["discord_id"])

    # Recreate notes table without note_id field, with UUID v7 PK
    op.create_table(
        "notes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("author_participant_id", sa.String(255), nullable=False),
        sa.Column(
            "author_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("tweet_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.String(255), nullable=True),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.Column("original_message_content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "classification",
            sa.Enum(
                "NOT_MISLEADING",
                "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                name="note_classification",
            ),
            nullable=False,
        ),
        sa.Column("helpfulness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum(
                "NEEDS_MORE_RATINGS",
                "CURRENTLY_RATED_HELPFUL",
                "CURRENTLY_RATED_NOT_HELPFUL",
                name="note_status",
            ),
            nullable=False,
            server_default="NEEDS_MORE_RATINGS",
        ),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ai_provider", sa.String(50), nullable=True),
        sa.Column("force_published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "force_published_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("force_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="notes_pkey"),
        sa.CheckConstraint(
            "author_participant_id IS NOT NULL OR author_profile_id IS NOT NULL",
            name="ck_notes_author_source",
        ),
    )
    op.create_index("ix_notes_id", "notes", ["id"])
    op.create_index("ix_notes_author_participant_id", "notes", ["author_participant_id"])
    op.create_index("ix_notes_author_profile_id", "notes", ["author_profile_id"])
    op.create_index("ix_notes_community_server_id", "notes", ["community_server_id"])
    op.create_index("ix_notes_request_id", "notes", ["request_id"])
    op.create_index("ix_notes_tweet_id", "notes", ["tweet_id"])
    op.create_index("ix_notes_channel_id", "notes", ["channel_id"])
    op.create_index("ix_notes_force_published_by", "notes", ["force_published_by"])
    op.create_index("idx_notes_created_at", "notes", ["created_at"])
    op.create_index("idx_notes_author_status", "notes", ["author_participant_id", "status"])
    op.create_index("idx_notes_author_profile_id", "notes", ["author_profile_id"])
    op.create_index("idx_notes_status", "notes", ["status"])

    # ===================================================================
    # PHASE 3: Recreate dependent tables with UUID v7 PKs/FKs
    # ===================================================================

    # Recreate refresh_tokens table with UUID v7 PK and FK
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("token", sa.String(500), nullable=True),
        sa.Column("token_hash", sa.String(255), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="refresh_tokens_pkey"),
        sa.UniqueConstraint("token", name="uq_refresh_tokens_token"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index(
        "idx_refresh_token_lookup",
        "refresh_tokens",
        ["token", "is_revoked", "expires_at"],
    )
    op.create_index(
        "idx_refresh_token_user_revoked",
        "refresh_tokens",
        ["user_id", "is_revoked"],
    )

    # Recreate api_keys table with UUID v7 PK and FK
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=True),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="api_keys_pkey"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_id", "api_keys", ["id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # Recreate audit_logs table with UUID v7 PK and FK
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="audit_logs_pkey"),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # Recreate ratings table with UUID v7 PK and UUID FK to notes
    op.create_table(
        "ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("rater_participant_id", sa.String(255), nullable=False),
        sa.Column(
            "rater_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "helpfulness_level",
            sa.Enum(
                "HELPFUL",
                "SOMEWHAT_HELPFUL",
                "NOT_HELPFUL",
                name="helpfulness_level",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rater_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="ratings_pkey"),
    )
    op.create_index("ix_ratings_id", "ratings", ["id"])
    op.create_index("ix_ratings_note_id", "ratings", ["note_id"])
    op.create_index("ix_ratings_rater_participant_id", "ratings", ["rater_participant_id"])
    op.create_index("ix_ratings_rater_profile_id", "ratings", ["rater_profile_id"])
    op.create_index(
        "idx_ratings_note_rater",
        "ratings",
        ["note_id", "rater_participant_id"],
        unique=True,
    )
    op.create_index("idx_ratings_created_at", "ratings", ["created_at"])

    # Recreate requests table with UUID v7 PK and UUID FK to notes
    op.create_table(
        "requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(255), nullable=False),
        sa.Column("tweet_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "message_archive_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("migrated_from_content", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "IN_PROGRESS",
                "COMPLETED",
                "FAILED",
                name="request_status",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("request_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("dataset_name", sa.String(100), nullable=True),
        sa.Column("dataset_item_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["message_archive_id"], ["message_archive.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="requests_pkey"),
        sa.UniqueConstraint("request_id", name="uq_requests_request_id"),
        sa.CheckConstraint(
            "message_archive_id IS NOT NULL",
            name="ck_requests_message_archive_required",
        ),
    )
    op.create_index("ix_requests_id", "requests", ["id"])
    op.create_index("ix_requests_request_id", "requests", ["request_id"])
    op.create_index("ix_requests_tweet_id", "requests", ["tweet_id"])
    op.create_index("ix_requests_community_server_id", "requests", ["community_server_id"])
    op.create_index("ix_requests_message_archive_id", "requests", ["message_archive_id"])
    op.create_index("ix_requests_note_id", "requests", ["note_id"])
    op.create_index("idx_requests_status", "requests", ["status"])
    op.create_index("idx_requests_requested_at", "requests", ["requested_at"])
    op.create_index("idx_requests_tweet_status", "requests", ["tweet_id", "status"])
    op.create_index("idx_requests_message_archive", "requests", ["message_archive_id"])

    # Recreate note_publisher_posts table with UUID v7 PK and UUID FK to notes
    op.create_table(
        "note_publisher_posts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("original_message_id", sa.String(64), nullable=False),
        sa.Column("auto_post_message_id", sa.String(64), nullable=True),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("community_server_id", sa.String(64), nullable=False),
        sa.Column("score_at_post", sa.Float(), nullable=False),
        sa.Column("confidence_at_post", sa.String(32), nullable=False),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="note_publisher_posts_pkey"),
        sa.UniqueConstraint("original_message_id", name="uq_note_publisher_posts_original_message"),
    )
    op.create_index("ix_note_publisher_posts_id", "note_publisher_posts", ["id"])
    op.create_index("ix_note_publisher_posts_note_id", "note_publisher_posts", ["note_id"])
    op.create_index(
        "ix_note_publisher_posts_original_message_id",
        "note_publisher_posts",
        ["original_message_id"],
    )

    # Recreate previously_seen_messages table with UUID FK to notes
    op.create_table(
        "previously_seen_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("original_message_id", sa.String(64), nullable=False),
        sa.Column(
            "published_note_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column("embedding_provider", sa.String(50), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["published_note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="previously_seen_messages_pkey"),
    )
    op.create_index("ix_previously_seen_messages_id", "previously_seen_messages", ["id"])
    op.create_index(
        "ix_previously_seen_messages_community_server_id",
        "previously_seen_messages",
        ["community_server_id"],
    )
    op.create_index(
        "ix_previously_seen_messages_original_message_id",
        "previously_seen_messages",
        ["original_message_id"],
    )
    op.create_index(
        "ix_previously_seen_messages_published_note_id",
        "previously_seen_messages",
        ["published_note_id"],
    )
    op.create_index(
        "idx_previously_seen_messages_community_server_id",
        "previously_seen_messages",
        ["community_server_id"],
    )
    op.create_index(
        "idx_previously_seen_messages_original_message_id",
        "previously_seen_messages",
        ["original_message_id"],
    )
    op.create_index(
        "idx_previously_seen_messages_published_note_id",
        "previously_seen_messages",
        ["published_note_id"],
    )
    op.create_index(
        "idx_previously_seen_messages_metadata",
        "previously_seen_messages",
        ["metadata"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_previously_seen_messages_embedding_version",
        "previously_seen_messages",
        ["embedding_provider", "embedding_model"],
    )

    # Add FK from notes.request_id to requests.request_id
    op.create_foreign_key(
        "notes_request_id_fkey",
        "notes",
        "requests",
        ["request_id"],
        ["request_id"],
        ondelete="SET NULL",
    )

    # ===================================================================
    # PHASE 4: Note on community_config FK
    # ===================================================================
    # community_config.updated_by still uses Integer (not migrated to UUID yet)
    # The FK was dropped in PHASE 0. We cannot recreate it because users.id is now UUID.
    # This requires a separate migration to convert community_config.updated_by to UUID.
    # TODO: Create follow-up task to migrate community_config to use UUID FKs


def downgrade() -> None:
    """Revert to integer primary keys (recreates with integer PKs)."""

    # ===================================================================
    # PHASE 0: Remove FK from community_config (will be recreated after users)
    # ===================================================================
    op.execute(
        "ALTER TABLE community_config DROP CONSTRAINT IF EXISTS fk_community_config_updated_by_users_id"
    )

    # ===================================================================
    # PHASE 1: Drop all dependent tables
    # ===================================================================
    # Using IF EXISTS and CASCADE for safety

    op.execute("DROP TABLE IF EXISTS previously_seen_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS note_publisher_posts CASCADE")
    op.execute("DROP TABLE IF EXISTS requests CASCADE")
    op.execute("DROP TABLE IF EXISTS ratings CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS api_keys CASCADE")
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS notes CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    # Drop ENUM types after tables
    op.execute("DROP TYPE IF EXISTS note_classification CASCADE")
    op.execute("DROP TYPE IF EXISTS note_status CASCADE")
    op.execute("DROP TYPE IF EXISTS helpfulness_level CASCADE")
    op.execute("DROP TYPE IF EXISTS request_status CASCADE")

    # ===================================================================
    # PHASE 1.5: Recreate ENUM types
    # ===================================================================
    # Recreate ENUM types BEFORE creating tables that use them
    op.execute(
        "CREATE TYPE note_classification AS ENUM ('NOT_MISLEADING', 'MISINFORMED_OR_POTENTIALLY_MISLEADING')"
    )
    op.execute(
        "CREATE TYPE note_status AS ENUM ('NEEDS_MORE_RATINGS', 'CURRENTLY_RATED_HELPFUL', 'CURRENTLY_RATED_NOT_HELPFUL')"
    )
    op.execute(
        "CREATE TYPE helpfulness_level AS ENUM ('HELPFUL', 'SOMEWHAT_HELPFUL', 'NOT_HELPFUL')"
    )
    op.execute(
        "CREATE TYPE request_status AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')"
    )

    # ===================================================================
    # PHASE 2: Recreate parent tables with Integer PKs
    # ===================================================================

    # Recreate users table with Integer PK
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_service_account", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("discord_id", sa.String(100), nullable=True),
        sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("discord_id", name="uq_users_discord_id"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_discord_id", "users", ["discord_id"])

    # Recreate notes table with Integer PK and note_id field
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("note_id", sa.BigInteger(), nullable=False),
        sa.Column("author_participant_id", sa.String(255), nullable=False),
        sa.Column("author_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tweet_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.String(255), nullable=True),
        sa.Column("community_server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.Column("original_message_content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "classification",
            sa.Enum(
                "NOT_MISLEADING",
                "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                name="note_classification",
            ),
            nullable=False,
        ),
        sa.Column("helpfulness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum(
                "NEEDS_MORE_RATINGS",
                "CURRENTLY_RATED_HELPFUL",
                "CURRENTLY_RATED_NOT_HELPFUL",
                name="note_status",
            ),
            nullable=False,
            server_default="NEEDS_MORE_RATINGS",
        ),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ai_provider", sa.String(50), nullable=True),
        sa.Column("force_published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("force_published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("force_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="notes_pkey"),
        sa.CheckConstraint(
            "author_participant_id IS NOT NULL OR author_profile_id IS NOT NULL",
            name="ck_notes_author_source",
        ),
    )
    op.create_index("ix_notes_id", "notes", ["id"])
    op.create_index("ix_notes_note_id", "notes", ["note_id"])
    op.create_index("ix_notes_author_participant_id", "notes", ["author_participant_id"])
    op.create_index("ix_notes_author_profile_id", "notes", ["author_profile_id"])
    op.create_index("ix_notes_community_server_id", "notes", ["community_server_id"])
    op.create_index("ix_notes_request_id", "notes", ["request_id"])
    op.create_index("ix_notes_tweet_id", "notes", ["tweet_id"])
    op.create_index("ix_notes_channel_id", "notes", ["channel_id"])
    op.create_index("ix_notes_force_published_by", "notes", ["force_published_by"])
    op.create_index("idx_notes_created_at", "notes", ["created_at"])
    op.create_index("idx_notes_author_status", "notes", ["author_participant_id", "status"])

    # ===================================================================
    # PHASE 3: Recreate dependent tables with Integer PKs/FKs
    # ===================================================================

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(500), nullable=True),
        sa.Column("token_hash", sa.String(255), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="refresh_tokens_pkey"),
        sa.UniqueConstraint("token", name="uq_refresh_tokens_token"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index(
        "idx_refresh_token_lookup",
        "refresh_tokens",
        ["token", "is_revoked", "expires_at"],
    )
    op.create_index(
        "idx_refresh_token_user_revoked",
        "refresh_tokens",
        ["user_id", "is_revoked"],
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=True),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="api_keys_pkey"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_id", "api_keys", ["id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="audit_logs_pkey"),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "ratings",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("rater_participant_id", sa.String(255), nullable=False),
        sa.Column("rater_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "helpfulness_level",
            sa.Enum(
                "HELPFUL",
                "SOMEWHAT_HELPFUL",
                "NOT_HELPFUL",
                name="helpfulness_level",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="ratings_pkey"),
    )
    op.create_index("ix_ratings_id", "ratings", ["id"])
    op.create_index("ix_ratings_note_id", "ratings", ["note_id"])
    op.create_index("ix_ratings_rater_participant_id", "ratings", ["rater_participant_id"])
    op.create_index("ix_ratings_rater_profile_id", "ratings", ["rater_profile_id"])
    op.create_index(
        "idx_ratings_note_rater",
        "ratings",
        ["note_id", "rater_participant_id"],
        unique=True,
    )
    op.create_index("idx_ratings_created_at", "ratings", ["created_at"])

    op.create_table(
        "requests",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("request_id", sa.String(255), nullable=False),
        sa.Column("tweet_id", sa.BigInteger(), nullable=False),
        sa.Column("community_server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_archive_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("migrated_from_content", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "IN_PROGRESS",
                "COMPLETED",
                "FAILED",
                name="request_status",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("note_id", sa.BigInteger(), nullable=True),
        sa.Column("request_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("dataset_name", sa.String(100), nullable=True),
        sa.Column("dataset_item_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="requests_pkey"),
        sa.UniqueConstraint("request_id", name="uq_requests_request_id"),
        sa.CheckConstraint(
            "message_archive_id IS NOT NULL",
            name="ck_requests_message_archive_required",
        ),
    )
    op.create_index("ix_requests_id", "requests", ["id"])
    op.create_index("ix_requests_request_id", "requests", ["request_id"])
    op.create_index("ix_requests_tweet_id", "requests", ["tweet_id"])
    op.create_index("ix_requests_community_server_id", "requests", ["community_server_id"])
    op.create_index("ix_requests_message_archive_id", "requests", ["message_archive_id"])
    op.create_index("ix_requests_note_id", "requests", ["note_id"])
    op.create_index("idx_requests_status", "requests", ["status"])
    op.create_index("idx_requests_requested_at", "requests", ["requested_at"])
    op.create_index("idx_requests_tweet_status", "requests", ["tweet_id", "status"])
    op.create_index("idx_requests_message_archive", "requests", ["message_archive_id"])

    op.create_table(
        "note_publisher_posts",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("note_id", sa.BigInteger(), nullable=False),
        sa.Column("original_message_id", sa.String(64), nullable=False),
        sa.Column("auto_post_message_id", sa.String(64), nullable=True),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("community_server_id", sa.String(64), nullable=False),
        sa.Column("score_at_post", sa.Float(), nullable=False),
        sa.Column("confidence_at_post", sa.String(32), nullable=False),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="note_publisher_posts_pkey"),
        sa.UniqueConstraint("original_message_id", name="uq_note_publisher_posts_original_message"),
    )
    op.create_index("ix_note_publisher_posts_id", "note_publisher_posts", ["id"])
    op.create_index("ix_note_publisher_posts_note_id", "note_publisher_posts", ["note_id"])
    op.create_index(
        "ix_note_publisher_posts_original_message_id",
        "note_publisher_posts",
        ["original_message_id"],
    )

    op.create_table(
        "previously_seen_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("original_message_id", sa.String(64), nullable=False),
        sa.Column("published_note_id", sa.BigInteger(), nullable=False),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column("embedding_provider", sa.String(50), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="previously_seen_messages_pkey"),
    )
    op.create_index("ix_previously_seen_messages_id", "previously_seen_messages", ["id"])
    op.create_index(
        "ix_previously_seen_messages_community_server_id",
        "previously_seen_messages",
        ["community_server_id"],
    )
    op.create_index(
        "ix_previously_seen_messages_original_message_id",
        "previously_seen_messages",
        ["original_message_id"],
    )
    op.create_index(
        "ix_previously_seen_messages_published_note_id",
        "previously_seen_messages",
        ["published_note_id"],
    )
    # ===================================================================
    # PHASE 4: Recreate FK in community_config (Integer to Integer reference)
    # ===================================================================
    # Recreate the FK that was dropped in PHASE 0 (now both are Integer again)
    op.create_foreign_key(
        "fk_community_config_updated_by_users_id",
        "community_config",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="RESTRICT",
    )
