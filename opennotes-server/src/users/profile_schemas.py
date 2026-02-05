"""
Pydantic schemas for user profile models.

This module provides request/response schemas for the refactored authentication
system, following the schema-driven development workflow where Pydantic models
are the single source of truth for TypeScript type generation.

Schemas follow the pattern:
    - Base: Common fields for create/update operations
    - Create: Fields required for creating new instances
    - Update: Optional fields for partial updates
    - InDB: Complete database representation with all fields
    - Response: API response format with nested relationships
"""

from datetime import UTC, datetime
from enum import Enum as PyEnum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.common.base_schemas import StrictInputSchema, TimestampSchema


class AuthProvider(str, PyEnum):
    """Supported authentication providers."""

    DISCORD = "discord"
    GITHUB = "github"
    EMAIL = "email"


class CommunityRole(str, PyEnum):
    """Community membership roles."""

    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"


# ============================================================================
# UserProfile Schemas
# ============================================================================


class UserProfileBase(BaseModel):
    """Base schema for user profile with common fields."""

    display_name: str = Field(..., min_length=1, max_length=255, description="User's display name")
    avatar_url: str | None = Field(None, max_length=500, description="URL to user's avatar image")
    bio: str | None = Field(None, description="User biography/description")
    role: str = Field("user", description="Platform-level role (user, moderator, admin)")
    is_opennotes_admin: bool = Field(
        False, description="OpenNotes-specific admin flag (grants cross-community admin privileges)"
    )
    is_human: bool = Field(True, description="Distinguishes human users from bot accounts")
    is_active: bool = Field(True, description="Whether the profile is active")
    is_banned: bool = Field(False, description="Whether the profile is banned")
    banned_at: datetime | None = Field(None, description="Timestamp when profile was banned")
    banned_reason: str | None = Field(None, description="Reason for ban")


class UserProfileCreate(UserProfileBase, StrictInputSchema):
    """Schema for creating a new user profile."""


class UserProfileSelfUpdate(StrictInputSchema):
    """
    Schema for users updating their own profile (self-service).

    Security: This schema only exposes user-editable fields.
    Privileged fields (role, is_opennotes_admin, is_banned, etc.) are
    intentionally excluded to prevent privilege escalation attacks.

    Use UserProfileAdminUpdate for admin operations on user profiles.
    """

    display_name: str | None = Field(
        default=None, min_length=1, max_length=255, description="User's display name"
    )
    avatar_url: str | None = Field(
        default=None, max_length=500, description="URL to user's avatar image"
    )
    bio: str | None = Field(default=None, description="User biography/description")


class UserProfileAdminUpdate(StrictInputSchema):
    """
    Schema for admin operations on user profiles.

    Security: This schema contains privileged fields that can only be
    modified by authorized administrators (service accounts or Open Notes admins).

    Includes all self-update fields plus admin-only fields:
    - role: Platform-level role
    - is_opennotes_admin: Cross-community admin privileges
    - is_human: Bot account flag
    - is_active: Account activation status
    - is_banned: Ban status and related fields
    """

    display_name: str | None = Field(
        default=None, min_length=1, max_length=255, description="User's display name"
    )
    avatar_url: str | None = Field(
        default=None, max_length=500, description="URL to user's avatar image"
    )
    bio: str | None = Field(default=None, description="User biography/description")
    role: str | None = Field(
        default=None, description="Platform-level role (user, moderator, admin)"
    )
    is_opennotes_admin: bool | None = Field(
        default=None,
        description="OpenNotes-specific admin flag (grants cross-community admin privileges)",
    )
    is_human: bool | None = Field(
        default=None, description="Distinguishes human users from bot accounts"
    )
    is_active: bool | None = Field(default=None, description="Whether the profile is active")
    is_banned: bool | None = Field(default=None, description="Whether the profile is banned")
    banned_at: datetime | None = Field(
        default=None, description="Timestamp when profile was banned"
    )
    banned_reason: str | None = Field(default=None, description="Reason for ban")


UserProfileUpdate = UserProfileAdminUpdate


class UserProfileInDB(UserProfileBase, TimestampSchema):
    """Complete user profile database representation."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )

    id: UUID = Field(..., description="Unique profile identifier")
    reputation: int = Field(0, description="Global reputation score")


class UserProfileResponse(UserProfileInDB):
    """API response schema for user profile with nested relationships."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )

    identities: list["UserIdentityResponse"] = Field(
        default_factory=list, description="Linked authentication identities"
    )
    community_memberships: list["CommunityMemberResponse"] = Field(
        default_factory=list, description="Community memberships"
    )


class PublicProfileResponse(BaseModel):
    """Public profile response schema (excludes sensitive information like banned_reason)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique profile identifier")
    display_name: str = Field(..., description="User's display name")
    avatar_url: str | None = Field(None, description="URL to user's avatar image")
    bio: str | None = Field(None, description="User biography/description")
    reputation: int = Field(0, description="Global reputation score")
    is_opennotes_admin: bool = Field(
        False, description="OpenNotes-specific admin flag (grants cross-community admin privileges)"
    )
    is_human: bool = Field(True, description="Distinguishes human users from bot accounts")
    is_active: bool = Field(True, description="Whether the profile is active")
    is_banned: bool = Field(False, description="Whether the profile is banned")
    created_at: datetime = Field(..., description="Profile creation timestamp")
    communities_count: int = Field(0, description="Number of communities joined")


# ============================================================================
# UserIdentity Schemas
# ============================================================================


class UserIdentityBase(BaseModel):
    """Base schema for user identity with common fields."""

    provider: AuthProvider = Field(..., description="Authentication provider")
    provider_user_id: str = Field(
        ..., min_length=1, max_length=255, description="User's unique ID on the provider"
    )
    credentials: dict[str, Any] | None = Field(
        None,
        description="Provider-specific credential data. Kept as dict[str, Any] - each OAuth "
        "provider has different token structures (Discord, Google, GitHub, etc.). "
        "Encrypted in database with EncryptedJSONB.",
    )


class UserIdentityCreate(UserIdentityBase, StrictInputSchema):
    """Schema for creating a new user identity."""

    profile_id: UUID = Field(..., description="Associated user profile ID")


class UserIdentityUpdate(StrictInputSchema):
    """Schema for updating an existing user identity (credentials only)."""

    credentials: dict[str, Any] | None = Field(
        None, description="Provider-specific credential data"
    )


class UserIdentityInDB(UserIdentityBase, TimestampSchema):
    """Complete user identity database representation."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )

    id: UUID = Field(..., description="Unique identity identifier")
    profile_id: UUID = Field(..., description="Associated user profile ID")
    email_verified: bool = Field(False, description="Whether email address is verified")
    email_verification_token: str | None = Field(
        None, description="Email verification token (internal use)"
    )
    email_verification_token_expires: datetime | None = Field(
        None, description="Verification token expiration timestamp"
    )


class UserIdentityResponse(TimestampSchema):
    """API response schema for user identity (excludes sensitive fields)."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",  # Ignore extra fields like credentials, email_verification_token
    )

    id: UUID = Field(..., description="Unique identity identifier")
    profile_id: UUID = Field(..., description="Associated user profile ID")
    provider: AuthProvider = Field(..., description="Authentication provider")
    provider_user_id: str = Field(
        ..., min_length=1, max_length=255, description="User's unique ID on the provider"
    )
    email_verified: bool = Field(..., description="Whether email address is verified")


class IdentityLinkRequest(StrictInputSchema):
    """Request schema for linking a new identity to an existing profile."""

    provider: AuthProvider = Field(..., description="Authentication provider to link")
    provider_user_id: str = Field(
        ..., min_length=1, max_length=255, description="User's unique ID on the provider"
    )
    credentials: dict[str, Any] | None = Field(
        None, description="Provider-specific credential data"
    )


# ============================================================================
# CommunityMember Schemas
# ============================================================================


class CommunityMemberBase(BaseModel):
    """Base schema for community member with common fields."""

    community_id: UUID = Field(..., description="Community identifier")
    is_external: bool = Field(
        False,
        description="True for external participants, False for internal members",
    )
    role: CommunityRole = Field(CommunityRole.MEMBER, description="Member role in the community")
    permissions: dict[str, Any] | None = Field(
        None,
        description="Role-specific permissions (JSON object). Kept as dict[str, Any] - "
        "permission structures vary by community platform (Discord roles, Reddit mod powers, etc.)",
    )
    invitation_reason: str | None = Field(None, description="Reason/context for invitation")


class CommunityMemberCreate(CommunityMemberBase, StrictInputSchema):
    """Schema for creating a new community membership."""

    profile_id: UUID = Field(..., description="User profile identifier")
    invited_by: UUID | None = Field(
        None, description="Profile ID of the user who invited this member"
    )
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When the user joined"
    )


class CommunityMemberUpdate(StrictInputSchema):
    """Schema for updating an existing community membership (all fields optional)."""

    role: CommunityRole | None = Field(None, description="Member role")
    permissions: dict[str, Any] | None = Field(None, description="Role-specific permissions")
    is_active: bool | None = Field(None, description="Whether membership is active")
    reputation_in_community: int | None = Field(None, description="Community-specific reputation")
    banned_at: datetime | None = Field(None, description="Ban timestamp")
    banned_reason: str | None = Field(None, description="Reason for ban")


class CommunityMemberInDB(CommunityMemberBase, TimestampSchema):
    """Complete community member database representation."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )

    id: UUID = Field(..., description="Unique membership identifier")
    profile_id: UUID = Field(..., description="User profile identifier")
    reputation_in_community: int | None = Field(None, description="Community-specific reputation")
    joined_at: datetime = Field(..., description="When the user joined")
    invited_by: UUID | None = Field(
        None, description="Profile ID of the user who invited this member"
    )
    is_active: bool = Field(True, description="Whether membership is active")
    banned_at: datetime | None = Field(None, description="Ban timestamp")
    banned_reason: str | None = Field(None, description="Reason for ban")


class CommunityMemberResponse(CommunityMemberInDB):
    """API response schema for community membership with nested profile."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )

    profile: Optional["UserProfileResponse"] = Field(None, description="Associated user profile")
    inviter: Optional["UserProfileResponse"] = Field(
        None, description="Profile of the user who invited this member"
    )


# ============================================================================
# Aggregation and Statistics Schemas
# ============================================================================


class UserProfileStats(BaseModel):
    """Statistics for a user profile across all communities."""

    profile_id: UUID = Field(..., description="User profile identifier")
    total_notes_created: int = Field(0, description="Total notes authored")
    total_ratings_given: int = Field(0, description="Total ratings provided")
    global_reputation: int = Field(0, description="Global reputation score")
    communities_count: int = Field(0, description="Number of communities joined")
    avg_helpfulness_score: float = Field(
        0.0, description="Average helpfulness score across all notes"
    )


class CommunityMemberStats(BaseModel):
    """Statistics for a user's activity within a specific community."""

    profile_id: UUID = Field(..., description="User profile identifier")
    community_id: UUID = Field(..., description="Community identifier")
    notes_in_community: int = Field(0, description="Notes created in this community")
    ratings_in_community: int = Field(0, description="Ratings given in this community")
    reputation_in_community: int = Field(0, description="Community-specific reputation")
    member_since: datetime = Field(..., description="Membership start date")
    is_active: bool = Field(True, description="Whether membership is active")


# ============================================================================
# Discord OAuth2 Schemas
# ============================================================================


class DiscordOAuthInitResponse(BaseModel):
    """Response schema for Discord OAuth2 flow initialization."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    authorization_url: str = Field(
        ..., description="Discord OAuth2 authorization URL to redirect user to"
    )
    state: str = Field(
        ...,
        description="OAuth2 state parameter for CSRF protection (store for callback validation)",
    )


class DiscordOAuthRegisterRequest(StrictInputSchema):
    """Request schema for Discord OAuth2 registration."""

    code: str = Field(..., min_length=1, description="OAuth2 authorization code from Discord")
    state: str = Field(
        ...,
        min_length=1,
        description="OAuth2 state parameter for CSRF protection (must match state from init)",
    )
    display_name: str = Field(
        ..., min_length=1, max_length=255, description="User's desired display name"
    )
    avatar_url: str | None = Field(
        None, max_length=500, description="URL to user's avatar image (optional override)"
    )


class DiscordOAuthLoginRequest(StrictInputSchema):
    """Request schema for Discord OAuth2 login."""

    code: str = Field(..., min_length=1, description="OAuth2 authorization code from Discord")
    state: str = Field(
        ...,
        min_length=1,
        description="OAuth2 state parameter for CSRF protection (must match state from init)",
    )


# ============================================================================
# Community Admin Management Schemas
# ============================================================================


class AddCommunityAdminRequest(StrictInputSchema):
    """Request schema for adding a community admin."""

    user_discord_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Discord ID of the user to promote to admin",
    )
    username: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Discord username (for auto-creating profile if user doesn't exist)",
    )
    display_name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Display name (for auto-creating profile if user doesn't exist)",
    )
    avatar_url: str | None = Field(
        None,
        max_length=500,
        description="Avatar URL (for auto-creating profile if user doesn't exist)",
    )


class AdminSource(str, PyEnum):
    """Source of admin privileges."""

    OPENNOTES_PLATFORM = "opennotes_platform"  # is_opennotes_admin=True
    COMMUNITY_ROLE = "community_role"  # CommunityMember.role='admin'
    DISCORD_MANAGE_SERVER = "discord_manage_server"  # Discord Manage Server permission


class CommunityAdminResponse(BaseModel):
    """Response schema for community admin information."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: UUID = Field(..., description="User profile identifier")
    display_name: str = Field(..., description="User's display name")
    avatar_url: str | None = Field(None, description="URL to user's avatar image")
    discord_id: str = Field(..., description="User's Discord ID")
    admin_sources: list[AdminSource] = Field(
        ..., description="Sources of admin privileges (can have multiple)"
    )
    is_opennotes_admin: bool = Field(
        False, description="Whether user is an Open Notes platform admin"
    )
    community_role: str = Field("member", description="User's role in the community")
    joined_at: datetime = Field(..., description="When the user joined the community")


class RemoveCommunityAdminResponse(BaseModel):
    """Response schema for admin removal."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable result message")
    profile_id: UUID = Field(..., description="Profile ID of the affected user")
    previous_role: str = Field(..., description="User's previous role")
    new_role: str = Field(..., description="User's new role")


# ============================================================================
# Pagination Schemas
# ============================================================================


class PaginationParams(BaseModel):
    """Query parameters for pagination."""

    limit: int = Field(50, ge=1, le=100, description="Number of items to return (max 100)")
    offset: int = Field(0, ge=0, description="Number of items to skip")


class PaginatedIdentitiesResponse(BaseModel):
    """Paginated response for user identities."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    items: list[UserIdentityResponse] = Field(..., description="List of identities")
    total: int = Field(..., description="Total number of identities")
    limit: int = Field(..., description="Number of items per page")
    offset: int = Field(..., description="Number of items skipped")


class PaginatedCommunitiesResponse(BaseModel):
    """Paginated response for community memberships."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    items: list[CommunityMemberResponse] = Field(..., description="List of community memberships")
    total: int = Field(..., description="Total number of memberships")
    limit: int = Field(..., description="Number of items per page")
    offset: int = Field(..., description="Number of items skipped")


# ============================================================================
# Resolve forward references for nested models
# ============================================================================

UserProfileResponse.model_rebuild()
CommunityMemberResponse.model_rebuild()
