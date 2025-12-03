"""add user profile identity system

Revision ID: 1fc2d611a071
Revises: 998489108130
Create Date: 2025-10-29 09:23:59.648811

Creates three new tables for the refactored user authentication system:
- user_profiles: Core user profile with display information and reputation
- user_identities: Authentication provider credentials linking to a profile
- community_members: Membership relationship between profiles and communities

This enables multiple authentication methods (Discord, GitHub, email) to link
to the same user profile, and tracks community membership with role-based access control.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "1fc2d611a071"
down_revision: str | Sequence[str] | None = "998489108130"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Creates user_profiles table with indexes for common queries.
    Creates user_identities table with FK to user_profiles (CASCADE delete).
    Creates community_members table with FKs to user_profiles (CASCADE/SET NULL).
    """
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("reputation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_human", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_profiles_is_human", "user_profiles", ["is_human"], unique=False)
    op.create_index("idx_user_profiles_reputation", "user_profiles", ["reputation"], unique=False)
    op.create_index("idx_user_profiles_created_at", "user_profiles", ["created_at"], unique=False)
    op.create_index("ix_user_profiles_id", "user_profiles", ["id"], unique=False)

    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("credentials", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_user_identities_provider_user",
        "user_identities",
        ["provider", "provider_user_id"],
        unique=True,
    )
    op.create_index(
        "idx_user_identities_profile_id", "user_identities", ["profile_id"], unique=False
    )
    op.create_index("ix_user_identities_id", "user_identities", ["id"], unique=False)

    op.create_table(
        "community_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("community_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reputation_in_community", sa.Integer(), nullable=True),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invitation_reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("banned_at", sa.DateTime(), nullable=True),
        sa.Column("banned_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["invited_by"], ["user_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_community_members_community_profile",
        "community_members",
        ["community_id", "profile_id"],
        unique=True,
    )
    op.create_index(
        "idx_community_members_community_id", "community_members", ["community_id"], unique=False
    )
    op.create_index(
        "idx_community_members_profile_id", "community_members", ["profile_id"], unique=False
    )
    op.create_index(
        "idx_community_members_is_external", "community_members", ["is_external"], unique=False
    )
    op.create_index("idx_community_members_role", "community_members", ["role"], unique=False)
    op.create_index(
        "idx_community_members_is_active", "community_members", ["is_active"], unique=False
    )
    op.create_index(
        "idx_community_members_joined_at", "community_members", ["joined_at"], unique=False
    )
    op.create_index("ix_community_members_id", "community_members", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Removes community_members, user_identities, and user_profiles tables in reverse order.
    """
    op.drop_index("ix_community_members_id", table_name="community_members")
    op.drop_index("idx_community_members_joined_at", table_name="community_members")
    op.drop_index("idx_community_members_is_active", table_name="community_members")
    op.drop_index("idx_community_members_role", table_name="community_members")
    op.drop_index("idx_community_members_is_external", table_name="community_members")
    op.drop_index("idx_community_members_profile_id", table_name="community_members")
    op.drop_index("idx_community_members_community_id", table_name="community_members")
    op.drop_index("idx_community_members_community_profile", table_name="community_members")
    op.drop_table("community_members")

    op.drop_index("ix_user_identities_id", table_name="user_identities")
    op.drop_index("idx_user_identities_profile_id", table_name="user_identities")
    op.drop_index("idx_user_identities_provider_user", table_name="user_identities")
    op.drop_table("user_identities")

    op.drop_index("ix_user_profiles_id", table_name="user_profiles")
    op.drop_index("idx_user_profiles_created_at", table_name="user_profiles")
    op.drop_index("idx_user_profiles_reputation", table_name="user_profiles")
    op.drop_index("idx_user_profiles_is_human", table_name="user_profiles")
    op.drop_table("user_profiles")
