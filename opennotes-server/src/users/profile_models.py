"""
User profile models for the refactored authentication system.

This module implements the separation of user identities (login credentials)
from user profiles (authorship records), enabling multiple authentication methods
to link to the same profile.

Models:
    - UserProfile: Core user profile with display information and reputation
    - UserIdentity: Authentication provider credentials linking to a profile
    - CommunityMember: Membership relationship between profiles and communities
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base, EncryptedJSONB
from src.llm_config.models import CommunityServer
from src.notes.models import TimestampMixin


class UserProfile(Base, TimestampMixin):
    """
    User profile representing a unique authorship identity.

    Separates profile information from authentication credentials, allowing
    multiple authentication methods (Discord, GitHub, email) to link to the
    same profile.

    Attributes:
        id: Unique profile identifier (UUID v7, server-generated)
        display_name: User's display name
        avatar_url: URL to user's avatar image
        bio: User biography/description
        reputation: Global reputation score (default: 0)
        role: Platform-level role ('user', 'moderator', 'admin')
        is_opennotes_admin: OpenNotes-specific admin flag (grants cross-community admin privileges)
        is_human: Distinguishes human users from bot accounts
        is_active: Whether the profile is active (default: True)
        is_banned: Whether the profile is banned (default: False)
        banned_at: Timestamp when the profile was banned (nullable)
        banned_reason: Reason for ban (nullable)
        last_interaction_at: Timestamp of the user's last interaction (nullable)
        identities: List of authentication identities linked to this profile
        community_memberships: List of communities this profile is a member of
    """

    __tablename__ = "user_profiles"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    reputation: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), default="user", server_default="user", nullable=False, index=True
    )
    is_opennotes_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    is_human: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    is_banned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Timestamp of the user's last interaction",
    )

    # Relationships
    identities: Mapped[list["UserIdentity"]] = relationship(
        back_populates="profile", lazy="selectin", cascade="all, delete-orphan"
    )
    community_memberships: Mapped[list["CommunityMember"]] = relationship(
        "CommunityMember",
        foreign_keys="CommunityMember.profile_id",
        back_populates="profile",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_user_profiles_is_human", "is_human"),
        Index("idx_user_profiles_is_opennotes_admin", "is_opennotes_admin"),
        Index("idx_user_profiles_reputation", "reputation"),
        Index("idx_user_profiles_created_at", "created_at"),
        Index("idx_user_profiles_is_active", "is_active"),
        Index("idx_user_profiles_is_banned", "is_banned"),
    )

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, display_name='{self.display_name}', is_human={self.is_human})>"


class UserIdentity(Base, TimestampMixin):
    """
    Authentication identity linking a provider account to a user profile.

    Enables multiple authentication methods to link to the same profile.
    For example, a user could link both their Discord and GitHub accounts
    to a single profile.

    Attributes:
        id: Unique identity identifier (UUID)
        profile_id: Foreign key to the associated user profile
        provider: Authentication provider ('discord', 'github', 'email')
        provider_user_id: User's unique ID on the provider platform
        credentials: JSON blob storing provider-specific credential data
        profile: Related UserProfile instance
    """

    __tablename__ = "user_identities"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'discord', 'github', 'email'
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    credentials: Mapped[dict[str, Any] | None] = mapped_column(
        EncryptedJSONB, nullable=True
    )  # Encrypted storage for provider-specific credential data
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False, index=True
    )
    email_verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verification_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile", back_populates="identities", lazy="selectin"
    )

    # Unique constraint: one provider account can only link to one profile
    __table_args__ = (
        Index(
            "idx_user_identities_provider_user",
            "provider",
            "provider_user_id",
            unique=True,
        ),
        Index("idx_user_identities_profile_id", "profile_id"),
    )

    def __repr__(self) -> str:
        return f"<UserIdentity(id={self.id}, provider='{self.provider}', provider_user_id='{self.provider_user_id}')>"


class CommunityMember(Base, TimestampMixin):
    """
    Membership relationship between a user profile and a community.

    Tracks both internal members (registered users) and external participants
    (users from other communities/platforms who interact with this community's
    notes via federation).

    Attributes:
        id: Unique membership identifier (UUID)
        community_id: Foreign key to community_servers table
        profile_id: Foreign key to the user profile
        is_external: True for external participants, False for internal members
        role: Member role in the community ('admin', 'moderator', 'member')
        permissions: JSON blob storing role-specific permissions
        reputation_in_community: Community-specific reputation score
        joined_at: Timestamp when the user joined this community
        invited_by: Profile ID of the user who invited this member (nullable)
        invitation_reason: Reason/context for invitation
        is_active: Whether the membership is currently active
        banned_at: Timestamp when the user was banned (nullable)
        banned_reason: Reason for ban
        community_server: Related CommunityServer instance
        profile: Related UserProfile instance
        inviter: Related UserProfile of the inviter (nullable)
    """

    __tablename__ = "community_members"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )
    community_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_external: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), default="member", server_default="member", nullable=False
    )
    permissions: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # Flexible role-based permissions
    reputation_in_community: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    invitation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    community_server: Mapped["CommunityServer"] = relationship("CommunityServer", lazy="selectin")
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        foreign_keys=[profile_id],
        back_populates="community_memberships",
        lazy="selectin",
    )
    inviter: Mapped["UserProfile | None"] = relationship(
        "UserProfile", foreign_keys=[invited_by], lazy="selectin"
    )

    # Unique constraint: one profile can only have one membership per community
    __table_args__ = (
        Index(
            "idx_community_members_community_profile",
            "community_id",
            "profile_id",
            unique=True,
        ),
        Index("idx_community_members_community_id", "community_id"),
        Index("idx_community_members_profile_id", "profile_id"),
        Index("idx_community_members_is_external", "is_external"),
        Index("idx_community_members_role", "role"),
        Index("idx_community_members_is_active", "is_active"),
        Index("idx_community_members_joined_at", "joined_at"),
    )

    def __repr__(self) -> str:
        return f"<CommunityMember(id={self.id}, community_id={self.community_id}, profile_id={self.profile_id}, role='{self.role}', is_external={self.is_external})>"
