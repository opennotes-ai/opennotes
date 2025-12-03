"""add_autopost_tables

Revision ID: 998489108130
Revises: 8872d1ee5368
Create Date: 2025-10-28 17:50:49.448035

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "998489108130"
down_revision: str | Sequence[str] | None = "8872d1ee5368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add auto_posts and server_autopost_config tables."""

    conn = op.get_bind()
    inspector = inspect(conn)

    # auto_posts table: tracks all auto-posted notes to prevent duplicates and provide audit trail
    if "auto_posts" not in inspector.get_table_names():
        op.create_table(
            "auto_posts",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("note_id", sa.Integer(), nullable=False),
            sa.Column("original_message_id", sa.String(length=64), nullable=False),
            sa.Column("auto_post_message_id", sa.String(length=64), nullable=False),
            sa.Column("channel_id", sa.String(length=64), nullable=False),
            sa.Column("guild_id", sa.String(length=64), nullable=False),
            sa.Column("score_at_post", sa.Float(), nullable=False),
            sa.Column("confidence_at_post", sa.String(length=32), nullable=False),
            sa.Column("posted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"], ondelete="CASCADE"),
        )

    # Indexes for auto_posts - drop and recreate to ensure consistency
    existing_indexes = (
        {idx["name"] for idx in inspector.get_indexes("auto_posts")}
        if "auto_posts" in inspector.get_table_names()
        else set()
    )

    indexes_to_create = [
        ("ix_auto_posts_note_id", ["note_id"]),
        ("ix_auto_posts_original_message_id", ["original_message_id"]),
        ("ix_auto_posts_channel_id", ["channel_id"]),
        ("ix_auto_posts_posted_at", ["posted_at"]),
        ("ix_auto_posts_guild_id", ["guild_id"]),
    ]

    for index_name, columns in indexes_to_create:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="auto_posts")
        op.create_index(op.f(index_name), "auto_posts", columns, unique=False)

    # Unique constraint: one auto-post per original message
    existing_constraints = (
        {c["name"] for c in inspector.get_unique_constraints("auto_posts")}
        if "auto_posts" in inspector.get_table_names()
        else set()
    )
    if "uq_auto_posts_original_message" not in existing_constraints:
        op.create_unique_constraint(
            "uq_auto_posts_original_message", "auto_posts", ["original_message_id"]
        )

    # server_autopost_config table: per-server and per-channel configuration
    if "server_autopost_config" not in inspector.get_table_names():
        op.create_table(
            "server_autopost_config",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("guild_id", sa.String(length=64), nullable=False),
            sa.Column("channel_id", sa.String(length=64), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("threshold", sa.Float(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_by", sa.String(length=64), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    # Indexes for server_autopost_config - drop and recreate to ensure consistency
    existing_config_indexes = (
        {idx["name"] for idx in inspector.get_indexes("server_autopost_config")}
        if "server_autopost_config" in inspector.get_table_names()
        else set()
    )

    config_indexes_to_create = [
        ("ix_server_autopost_config_guild_id", ["guild_id"]),
        ("ix_server_autopost_config_channel_id", ["channel_id"]),
    ]

    for index_name, columns in config_indexes_to_create:
        if index_name in existing_config_indexes:
            op.drop_index(index_name, table_name="server_autopost_config")
        op.create_index(op.f(index_name), "server_autopost_config", columns, unique=False)

    # Unique constraint: one config per guild+channel combination (null channel_id = server-wide)
    existing_config_constraints = (
        {c["name"] for c in inspector.get_unique_constraints("server_autopost_config")}
        if "server_autopost_config" in inspector.get_table_names()
        else set()
    )
    if "uq_server_autopost_config_guild_channel" not in existing_config_constraints:
        op.create_unique_constraint(
            "uq_server_autopost_config_guild_channel",
            "server_autopost_config",
            ["guild_id", "channel_id"],
        )


def downgrade() -> None:
    """Downgrade schema - remove auto_posts and server_autopost_config tables."""

    # Drop server_autopost_config
    op.drop_constraint(
        "uq_server_autopost_config_guild_channel", "server_autopost_config", type_="unique"
    )
    op.drop_index(op.f("ix_server_autopost_config_channel_id"), table_name="server_autopost_config")
    op.drop_index(op.f("ix_server_autopost_config_guild_id"), table_name="server_autopost_config")
    op.drop_table("server_autopost_config")

    # Drop auto_posts
    op.drop_constraint("uq_auto_posts_original_message", "auto_posts", type_="unique")
    op.drop_index(op.f("ix_auto_posts_guild_id"), table_name="auto_posts")
    op.drop_index(op.f("ix_auto_posts_posted_at"), table_name="auto_posts")
    op.drop_index(op.f("ix_auto_posts_channel_id"), table_name="auto_posts")
    op.drop_index(op.f("ix_auto_posts_original_message_id"), table_name="auto_posts")
    op.drop_index(op.f("ix_auto_posts_note_id"), table_name="auto_posts")
    op.drop_table("auto_posts")
