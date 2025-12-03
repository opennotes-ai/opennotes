"""sync schema drift: fix timestamp types, indexes, constraints, and foreign keys

Revision ID: 454e533b87ec
Revises: a6de0b1c4d3f
Create Date: 2025-11-13 11:55:48.677681

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "454e533b87ec"
down_revision: str | Sequence[str] | None = "a6de0b1c4d3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "api_keys",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_constraint(op.f("uq_api_keys_key_hash"), "api_keys", type_="unique")
    op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=True)
    op.alter_column(
        "audit_logs",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "note_publisher_posts",
        "posted_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_index(op.f("ix_note_publisher_posts_note_id"), table_name="note_publisher_posts")
    op.drop_index(
        op.f("ix_note_publisher_posts_original_message_id"), table_name="note_publisher_posts"
    )
    op.alter_column(
        "notes",
        "helpfulness_score",
        existing_type=sa.INTEGER(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "notes",
        "status",
        existing_type=postgresql.ENUM(
            "NEEDS_MORE_RATINGS",
            "CURRENTLY_RATED_HELPFUL",
            "CURRENTLY_RATED_NOT_HELPFUL",
            name="note_status",
        ),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "notes",
        "force_published_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "notes",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "notes",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_foreign_key(
        None, "notes", "user_profiles", ["force_published_by"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        None, "notes", "community_servers", ["community_server_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        None, "notes", "user_profiles", ["author_profile_id"], ["id"], ondelete="SET NULL"
    )
    op.alter_column(
        "previously_seen_messages",
        "original_message_id",
        existing_type=sa.VARCHAR(length=64),
        comment="Platform-specific message ID",
        existing_nullable=False,
    )
    op.alter_column(
        "previously_seen_messages",
        "published_note_id",
        existing_type=sa.UUID(),
        comment="Note that was published for this message",
        existing_nullable=False,
    )
    op.alter_column(
        "previously_seen_messages",
        "embedding",
        existing_type=postgresql.ARRAY(sa.DOUBLE_PRECISION(precision=53)),
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
        existing_nullable=True,
    )
    op.alter_column(
        "previously_seen_messages",
        "embedding_provider",
        existing_type=sa.VARCHAR(length=50),
        comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
        existing_nullable=True,
    )
    op.alter_column(
        "previously_seen_messages",
        "embedding_model",
        existing_type=sa.VARCHAR(length=100),
        comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
        existing_nullable=True,
    )
    op.alter_column(
        "previously_seen_messages",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.create_index(
        "idx_previously_seen_messages_embedding_ivfflat",
        "previously_seen_messages",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )
    # REMOVED: Composite B-tree index on [community_server_id, embedding]
    # This index exceeds PostgreSQL's B-tree size limit (6176 bytes > 2704 byte limit)
    # due to the 1536-dimension embedding vector. Migration f9fec89fa9be drops it.
    # Index creation removed to prevent partial index creation errors.
    op.alter_column(
        "ratings",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "ratings",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_ratings_note_id"), table_name="ratings")
    op.create_index("idx_ratings_rater_profile_id", "ratings", ["rater_profile_id"], unique=False)
    op.alter_column(
        "refresh_tokens",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_constraint(op.f("uq_refresh_tokens_token"), "refresh_tokens", type_="unique")
    op.drop_constraint(op.f("uq_refresh_tokens_token_hash"), "refresh_tokens", type_="unique")
    op.drop_index(op.f("ix_refresh_tokens_token"), table_name="refresh_tokens")
    op.create_index(op.f("ix_refresh_tokens_token"), "refresh_tokens", ["token"], unique=True)
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.create_index(
        op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True
    )
    op.alter_column(
        "requests",
        "migrated_from_content",
        existing_type=sa.BOOLEAN(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "requests",
        "requested_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "requests",
        "status",
        existing_type=postgresql.ENUM(
            "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", name="request_status"
        ),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "requests",
        "request_metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default="{}",
        existing_nullable=True,
    )
    op.alter_column(
        "requests",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "requests",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_requests_note_id"), table_name="requests")
    op.drop_index(op.f("ix_requests_request_id"), table_name="requests")
    op.create_index(op.f("ix_requests_request_id"), "requests", ["request_id"], unique=True)
    op.create_foreign_key(
        None, "requests", "community_servers", ["community_server_id"], ["id"], ondelete="RESTRICT"
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        nullable=False,
    )
    op.drop_index(op.f("ix_users_discord_id"), table_name="users")
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_unique_constraint(
        op.f("uq_users_username"), "users", ["username"], postgresql_nulls_not_distinct=False
    )
    op.create_unique_constraint(
        op.f("uq_users_email"), "users", ["email"], postgresql_nulls_not_distinct=False
    )
    op.create_index(op.f("ix_users_discord_id"), "users", ["discord_id"], unique=False)
    op.alter_column(
        "users",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        nullable=True,
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.drop_index(op.f("ix_requests_request_id"), table_name="requests")
    op.create_index(op.f("ix_requests_request_id"), "requests", ["request_id"], unique=False)
    op.create_index(op.f("ix_requests_note_id"), "requests", ["note_id"], unique=False)
    op.alter_column(
        "requests",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "requests",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "requests",
        "request_metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default=None,
        existing_nullable=True,
    )
    op.alter_column(
        "requests",
        "status",
        existing_type=postgresql.ENUM(
            "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", name="request_status"
        ),
        server_default=sa.text("'PENDING'::request_status"),
        existing_nullable=False,
    )
    op.alter_column(
        "requests",
        "requested_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "requests",
        "migrated_from_content",
        existing_type=sa.BOOLEAN(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.create_index(
        op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=False
    )
    op.drop_index(op.f("ix_refresh_tokens_token"), table_name="refresh_tokens")
    op.create_index(op.f("ix_refresh_tokens_token"), "refresh_tokens", ["token"], unique=False)
    op.create_unique_constraint(
        op.f("uq_refresh_tokens_token_hash"),
        "refresh_tokens",
        ["token_hash"],
        postgresql_nulls_not_distinct=False,
    )
    op.create_unique_constraint(
        op.f("uq_refresh_tokens_token"),
        "refresh_tokens",
        ["token"],
        postgresql_nulls_not_distinct=False,
    )
    op.alter_column(
        "refresh_tokens",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.drop_index("idx_ratings_rater_profile_id", table_name="ratings")
    op.create_index(op.f("ix_ratings_note_id"), "ratings", ["note_id"], unique=False)
    op.alter_column(
        "ratings",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "ratings",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    # REMOVED: Drop of composite B-tree index that was never created (see upgrade function)
    op.drop_index(
        "idx_previously_seen_messages_embedding_ivfflat",
        table_name="previously_seen_messages",
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )
    op.alter_column(
        "previously_seen_messages",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "previously_seen_messages",
        "embedding_model",
        existing_type=sa.VARCHAR(length=100),
        comment=None,
        existing_comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
        existing_nullable=True,
    )
    op.alter_column(
        "previously_seen_messages",
        "embedding_provider",
        existing_type=sa.VARCHAR(length=50),
        comment=None,
        existing_comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
        existing_nullable=True,
    )
    op.alter_column(
        "previously_seen_messages",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
        type_=postgresql.ARRAY(sa.DOUBLE_PRECISION(precision=53)),
        existing_nullable=True,
    )
    op.alter_column(
        "previously_seen_messages",
        "published_note_id",
        existing_type=sa.UUID(),
        comment=None,
        existing_comment="Note that was published for this message",
        existing_nullable=False,
    )
    op.alter_column(
        "previously_seen_messages",
        "original_message_id",
        existing_type=sa.VARCHAR(length=64),
        comment=None,
        existing_comment="Platform-specific message ID",
        existing_nullable=False,
    )
    op.drop_constraint(None, "notes", type_="foreignkey")
    op.drop_constraint(None, "notes", type_="foreignkey")
    op.drop_constraint(None, "notes", type_="foreignkey")
    op.alter_column(
        "notes",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "notes",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "notes",
        "force_published_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "notes",
        "status",
        existing_type=postgresql.ENUM(
            "NEEDS_MORE_RATINGS",
            "CURRENTLY_RATED_HELPFUL",
            "CURRENTLY_RATED_NOT_HELPFUL",
            name="note_status",
        ),
        server_default=sa.text("'NEEDS_MORE_RATINGS'::note_status"),
        existing_nullable=False,
    )
    op.alter_column(
        "notes",
        "helpfulness_score",
        existing_type=sa.INTEGER(),
        server_default=sa.text("0"),
        existing_nullable=False,
    )
    op.create_index(
        op.f("ix_note_publisher_posts_original_message_id"),
        "note_publisher_posts",
        ["original_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_note_publisher_posts_note_id"), "note_publisher_posts", ["note_id"], unique=False
    )
    op.alter_column(
        "note_publisher_posts",
        "posted_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "audit_logs",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=False)
    op.create_unique_constraint(
        op.f("uq_api_keys_key_hash"), "api_keys", ["key_hash"], postgresql_nulls_not_distinct=False
    )
    op.alter_column(
        "api_keys",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
