"""
CRUD operations for UserProfile and UserIdentity models.

This module provides database operations for the refactored authentication system,
enabling profile-based authentication with multiple identity providers.

Eager Loading Strategy
----------------------
To prevent N+1 query problems, this module uses the centralized loaders module
(src.users.loaders) for eager loading patterns:

1. UserProfile queries (loaders.profile_full):
   - Always loads: identities, community_memberships
   - Rationale: These relationships are frequently accessed together for
     authentication and authorization decisions

2. CommunityMember queries (loaders.member_full):
   - Always loads: profile, inviter
   - Rationale: Profile is required for display, inviter is useful for audit trails

3. UserIdentity queries (loaders.identity_with_profile):
   - Loads profile with its nested relationships (identities, community_memberships)
   - Rationale: Ensures complete profile context when authenticating via identity

See src/users/loaders.py for the composable loader functions.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.models import CommunityServer
from src.users import loaders
from src.users.audit_helper import create_audit_log
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile
from src.users.profile_schemas import (
    AuthProvider,
    CommunityMemberCreate,
    CommunityMemberUpdate,
    CommunityRole,
    UserIdentityCreate,
    UserProfileAdminUpdate,
    UserProfileCreate,
    UserProfileSelfUpdate,
)

logger = logging.getLogger(__name__)


async def get_profile_by_id(db: AsyncSession, profile_id: UUID) -> UserProfile | None:
    result = await db.execute(
        select(UserProfile).where(UserProfile.id == profile_id).options(*loaders.profile_full())
    )
    return result.scalar_one_or_none()


async def get_profile_by_display_name(db: AsyncSession, display_name: str) -> UserProfile | None:
    result = await db.execute(
        select(UserProfile)
        .where(UserProfile.display_name == display_name)
        .options(*loaders.profile_full())
    )
    return result.scalar_one_or_none()


async def create_profile(db: AsyncSession, profile_create: UserProfileCreate) -> UserProfile:
    profile = UserProfile(
        display_name=profile_create.display_name,
        avatar_url=profile_create.avatar_url,
        bio=profile_create.bio,
        is_human=profile_create.is_human,
        reputation=0,
    )

    db.add(profile)
    await db.flush()
    await db.refresh(profile)

    return profile


async def update_profile(
    db: AsyncSession,
    profile: UserProfile,
    profile_update: UserProfileSelfUpdate | UserProfileAdminUpdate,
    requesting_profile_id: UUID | None = None,
    requesting_profile: UserProfile | None = None,
    bypass_admin_check: bool = False,
) -> UserProfile:
    """
    Update a user profile.

    Security:
        - UserProfileSelfUpdate: Only allows user-editable fields (display_name, avatar_url, bio)
        - UserProfileAdminUpdate: Allows admin-only fields, requires admin privileges

    Args:
        db: Database session
        profile: UserProfile instance to update
        profile_update: Update data (UserProfileSelfUpdate or UserProfileAdminUpdate)
        requesting_profile_id: ID of profile making the request (for authorization check)
        requesting_profile: Profile making the request (for admin privilege check)
        bypass_admin_check: If True, skip admin privilege verification. Use ONLY for
            service account operations where authorization has already been verified
            at the endpoint level (e.g., admin_router endpoints).

    Returns:
        Updated UserProfile instance

    Raises:
        HTTPException(403): If requesting_profile_id doesn't match profile.id (unauthorized)
        HTTPException(403): If admin fields are being updated without admin privileges
    """
    is_admin_update = isinstance(profile_update, UserProfileAdminUpdate)

    if is_admin_update and not bypass_admin_check:
        has_admin_fields = any(
            [
                getattr(profile_update, "role", None) is not None,
                getattr(profile_update, "is_opennotes_admin", None) is not None,
                getattr(profile_update, "is_human", None) is not None,
                getattr(profile_update, "is_active", None) is not None,
                getattr(profile_update, "is_banned", None) is not None,
                getattr(profile_update, "banned_at", None) is not None,
                getattr(profile_update, "banned_reason", None) is not None,
            ]
        )

        if has_admin_fields:
            is_admin = requesting_profile is not None and requesting_profile.is_opennotes_admin
            if not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin privileges required to update privileged profile fields",
                )
    elif requesting_profile_id is not None and requesting_profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this profile",
        )

    if profile_update.display_name is not None:
        existing = await get_profile_by_display_name(db, profile_update.display_name)
        if existing and existing.id != profile.id:
            raise ValueError("Display name already in use")
        profile.display_name = profile_update.display_name

    if profile_update.avatar_url is not None:
        profile.avatar_url = profile_update.avatar_url

    if profile_update.bio is not None:
        profile.bio = profile_update.bio

    if is_admin_update:
        admin_fields = [
            "role",
            "is_opennotes_admin",
            "is_human",
            "is_active",
            "is_banned",
            "banned_at",
            "banned_reason",
        ]
        for field in admin_fields:
            value = getattr(profile_update, field, None)
            if value is not None:
                setattr(profile, field, value)

    profile.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(profile)

    return profile


async def get_identity_by_provider(
    db: AsyncSession, provider: AuthProvider, provider_user_id: str
) -> UserIdentity | None:
    result = await db.execute(
        select(UserIdentity)
        .where(
            UserIdentity.provider == provider.value,
            UserIdentity.provider_user_id == provider_user_id,
        )
        .options(*loaders.identity_with_profile())
    )
    return result.scalar_one_or_none()


async def get_identities_by_profile(
    db: AsyncSession, profile_id: UUID, limit: int | None = None, offset: int | None = None
) -> list[UserIdentity]:
    query = (
        select(UserIdentity)
        .where(UserIdentity.profile_id == profile_id)
        .order_by(UserIdentity.created_at)
    )

    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def create_identity(
    db: AsyncSession,
    identity_create: UserIdentityCreate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> UserIdentity:
    identity = UserIdentity(
        profile_id=identity_create.profile_id,
        provider=identity_create.provider.value,
        provider_user_id=identity_create.provider_user_id,
        credentials=identity_create.credentials,
    )

    db.add(identity)
    await db.flush()
    await db.refresh(identity)

    await create_audit_log(
        db=db,
        user_id=None,
        action="LINK_IDENTITY",
        resource="identity",
        resource_id=str(identity.id),
        details={
            "profile_id": str(identity_create.profile_id),
            "provider": identity_create.provider.value,
            "provider_user_id": identity_create.provider_user_id,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return identity


async def authenticate_with_provider(
    db: AsyncSession, provider: AuthProvider, provider_user_id: str
) -> UserProfile | None:
    """
    Authenticate a user via their provider identity.

    Returns the user's profile if authentication succeeds, or None if:
    - No identity found for this provider/user_id combination
    - Profile doesn't exist (data integrity issue)
    - Profile is inactive (is_active=False)
    - Profile is banned (is_banned=True)

    Args:
        db: Database session
        provider: Authentication provider (discord, github, email)
        provider_user_id: User's unique ID on the provider platform

    Returns:
        UserProfile if authentication succeeds, None otherwise
    """
    identity = await get_identity_by_provider(db, provider, provider_user_id)

    if identity is None:
        return None

    profile = identity.profile

    if not profile:
        logger.warning(
            "Identity exists but profile is missing",
            extra={
                "identity_id": str(identity.id),
                "provider": provider.value,
                "provider_user_id": provider_user_id,
            },
        )
        return None

    if not profile.is_active:
        logger.warning(
            "Authentication blocked: profile is inactive",
            extra={
                "profile_id": str(profile.id),
                "provider": provider.value,
                "provider_user_id": provider_user_id,
            },
        )
        return None

    if profile.is_banned:
        logger.warning(
            "Authentication blocked: profile is banned",
            extra={
                "profile_id": str(profile.id),
                "provider": provider.value,
                "provider_user_id": provider_user_id,
                "banned_at": profile.banned_at.isoformat() if profile.banned_at else None,
            },
        )
        return None

    return profile


async def create_profile_with_identity(
    db: AsyncSession,
    profile_create: UserProfileCreate,
    provider: AuthProvider,
    provider_user_id: str,
    credentials: dict[str, Any] | None = None,
) -> tuple[UserProfile, UserIdentity]:
    profile = await create_profile(db, profile_create)

    identity_create = UserIdentityCreate(
        profile_id=profile.id,
        provider=provider,
        provider_user_id=provider_user_id,
        credentials=credentials,
    )

    identity = await create_identity(db, identity_create)

    await db.refresh(profile, attribute_names=["identities"])

    return profile, identity


async def get_community_member(
    db: AsyncSession, community_id: UUID, profile_id: UUID
) -> CommunityMember | None:
    result = await db.execute(
        select(CommunityMember)
        .where(
            CommunityMember.community_id == community_id, CommunityMember.profile_id == profile_id
        )
        .options(*loaders.member_full())
    )
    return result.scalar_one_or_none()


async def create_community_member(
    db: AsyncSession, member_create: CommunityMemberCreate
) -> CommunityMember:
    member = CommunityMember(
        community_id=member_create.community_id,
        profile_id=member_create.profile_id,
        is_external=member_create.is_external,
        role=member_create.role.value,
        permissions=member_create.permissions,
        joined_at=member_create.joined_at,
        invited_by=member_create.invited_by,
        invitation_reason=member_create.invitation_reason,
        is_active=True,
    )

    db.add(member)
    await db.flush()
    await db.refresh(member)

    return member


async def update_community_member(
    db: AsyncSession,
    member: CommunityMember,
    member_update: CommunityMemberUpdate,
    requesting_profile_id: UUID | None = None,
    allow_admin_override: bool = False,
) -> CommunityMember:
    """
    Update a community membership.

    Args:
        db: Database session
        member: CommunityMember instance to update
        member_update: Update data
        requesting_profile_id: ID of profile making the request (for authorization check)
        allow_admin_override: If True, allows admins to update other members (future feature)

    Returns:
        Updated CommunityMember instance

    Raises:
        HTTPException(403): If requesting_profile_id doesn't match member.profile_id
                           and allow_admin_override is False (unauthorized)
    """
    # SECURITY: Verify requesting profile owns this membership (defense in depth)
    # Unless admin override is enabled (for future admin features)
    if (
        not allow_admin_override
        and requesting_profile_id is not None
        and requesting_profile_id != member.profile_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this community membership",
        )

    if member_update.role is not None:
        member.role = member_update.role.value

    if member_update.permissions is not None:
        member.permissions = member_update.permissions

    if member_update.is_active is not None:
        member.is_active = member_update.is_active

    if member_update.reputation_in_community is not None:
        member.reputation_in_community = member_update.reputation_in_community

    if member_update.banned_at is not None:
        member.banned_at = member_update.banned_at

    if member_update.banned_reason is not None:
        member.banned_reason = member_update.banned_reason

    member.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(member)

    return member


async def get_community_members(db: AsyncSession, community_id: UUID) -> list[CommunityMember]:
    result = await db.execute(
        select(CommunityMember)
        .where(CommunityMember.community_id == community_id)
        .options(*loaders.member_full())
        .order_by(CommunityMember.joined_at)
    )
    return list(result.scalars().all())


async def get_profile_communities(
    db: AsyncSession, profile_id: UUID, limit: int | None = None, offset: int | None = None
) -> list[CommunityMember]:
    query = (
        select(CommunityMember)
        .where(CommunityMember.profile_id == profile_id)
        .options(*loaders.member_full())
        .order_by(CommunityMember.joined_at)
    )

    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_identity_by_id(db: AsyncSession, identity_id: UUID) -> UserIdentity | None:
    """Get a user identity by its ID."""
    result = await db.execute(select(UserIdentity).where(UserIdentity.id == identity_id))
    return result.scalar_one_or_none()


async def delete_identity(
    db: AsyncSession,
    identity_id: UUID,
    profile_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """
    Delete a user identity (unlink from profile).

    Returns True if deleted, False if not found or doesn't belong to profile.
    Caller should check that profile has at least one remaining identity.
    """
    identity = await get_identity_by_id(db, identity_id)

    if identity is None or identity.profile_id != profile_id:
        return False

    await create_audit_log(
        db=db,
        user_id=None,
        action="UNLINK_IDENTITY",
        resource="identity",
        resource_id=str(identity_id),
        details={
            "profile_id": str(profile_id),
            "provider": identity.provider,
            "provider_user_id": identity.provider_user_id,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await db.delete(identity)
    await db.flush()
    return True


async def count_identities_for_profile(db: AsyncSession, profile_id: UUID) -> int:
    """Count the number of identities linked to a profile."""
    result = await db.execute(
        select(func.count()).select_from(UserIdentity).where(UserIdentity.profile_id == profile_id)
    )
    return result.scalar_one()


async def count_communities_for_profile(db: AsyncSession, profile_id: UUID) -> int:
    """Count the number of communities a profile is a member of."""
    result = await db.execute(
        select(func.count())
        .select_from(CommunityMember)
        .where(CommunityMember.profile_id == profile_id)
    )
    return result.scalar_one()


async def get_identity_by_verification_token(
    db: AsyncSession, verification_token: str
) -> UserIdentity | None:
    """Get a user identity by its email verification token."""
    result = await db.execute(
        select(UserIdentity)
        .where(UserIdentity.email_verification_token == verification_token)
        .options(*loaders.identity_with_profile())
    )
    return result.scalar_one_or_none()


async def update_identity(
    db: AsyncSession, identity: UserIdentity, update_data: dict[str, Any]
) -> UserIdentity:
    """
    Update a user identity with the provided data.

    Args:
        db: Database session
        identity: The identity to update
        update_data: Dictionary of fields to update

    Returns:
        Updated UserIdentity instance

    Note:
        This function uses flush() instead of commit() to allow the caller
        to manage transaction boundaries. The caller is responsible for
        calling commit() or rollback() on the session.
    """
    for field, value in update_data.items():
        setattr(identity, field, value)

    await db.flush()
    await db.refresh(identity)
    return identity


async def get_or_create_profile_from_discord(
    db: AsyncSession,
    discord_user_id: str,
    username: str,
    display_name: str | None = None,
    avatar_url: str | None = None,
    guild_id: str | None = None,
) -> UserProfile:
    """
    Get or create a user profile from Discord user information.

    This function is idempotent and race-condition safe. It will:
    1. Look up existing Discord identity
    2. If found, update last_interaction_at and optionally refresh metadata
    3. If not found, create profile, identity, and optionally community membership
    4. Handle concurrent creation attempts gracefully (retry on IntegrityError)

    Args:
        db: Database session
        discord_user_id: Discord user ID (snowflake as string)
        username: Discord username
        display_name: Discord display name or global name (fallback to username)
        avatar_url: Discord avatar URL
        guild_id: Discord guild ID (optional, for community membership)

    Returns:
        UserProfile instance (existing or newly created)

    Note:
        This function uses flush() instead of commit() to allow the caller
        to manage transaction boundaries. The caller is responsible for
        calling commit() or rollback() on the session.
    """
    # Try to find existing Discord identity
    identity = await get_identity_by_provider(db, AuthProvider.DISCORD, discord_user_id)

    if identity:
        # Update existing profile
        profile = identity.profile
        profile.last_interaction_at = datetime.now(UTC)

        # Optionally refresh metadata (avatar_url, display_name)
        if avatar_url and profile.avatar_url != avatar_url:
            profile.avatar_url = avatar_url

        effective_display_name = display_name or username
        if profile.display_name != effective_display_name:
            profile.display_name = effective_display_name

        await db.flush()
        await db.refresh(profile)

        # Ensure community membership exists if guild_id provided
        if guild_id:
            await _ensure_community_membership(db, profile.id, guild_id)

        return profile

    # Profile doesn't exist yet - create it
    try:
        effective_display_name = display_name or username

        profile_create = UserProfileCreate(
            display_name=effective_display_name,
            avatar_url=avatar_url,
            bio=None,
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id=discord_user_id,
            credentials=None,
        )

        # Set initial last_interaction_at
        profile.last_interaction_at = datetime.now(UTC)
        await db.flush()

        # Create community membership if guild_id provided
        if guild_id:
            await _ensure_community_membership(db, profile.id, guild_id)

        await db.refresh(profile)
        return profile

    except IntegrityError as e:
        # Race condition: another request created the profile concurrently
        # Rollback and retry lookup
        logger.info(
            "Race condition detected during profile creation, retrying lookup",
            extra={
                "discord_user_id": discord_user_id,
                "error": str(e),
            },
        )
        await db.rollback()

        # Retry lookup - should succeed now
        identity = await get_identity_by_provider(db, AuthProvider.DISCORD, discord_user_id)
        if identity:
            profile = identity.profile
            profile.last_interaction_at = datetime.now(UTC)
            await db.flush()
            await db.refresh(profile)

            # Ensure community membership exists if guild_id provided
            if guild_id:
                await _ensure_community_membership(db, profile.id, guild_id)

            return profile

        # Still not found - unexpected error
        logger.error(
            "Profile creation failed and retry lookup also failed",
            extra={"discord_user_id": discord_user_id},
        )
        raise


async def _ensure_community_membership(
    db: AsyncSession, profile_id: UUID, guild_id: str
) -> CommunityMember | None:
    """
    Ensure community membership exists for the profile in the given guild.

    Internal helper function that creates community membership if:
    1. The community server exists
    2. The profile doesn't already have membership

    Args:
        db: Database session
        profile_id: User profile ID
        guild_id: Discord guild ID

    Returns:
        CommunityMember instance, or None if community server doesn't exist
    """
    # Look up community server by guild_id
    result = await db.execute(
        select(CommunityServer).where(
            CommunityServer.platform == "discord",
            CommunityServer.platform_id == guild_id,
        )
    )
    community_server = result.scalar_one_or_none()

    if not community_server:
        # Community server doesn't exist yet - skip membership creation
        logger.debug(
            "Skipping community membership creation: community server not found",
            extra={"guild_id": guild_id, "profile_id": str(profile_id)},
        )
        return None

    # Check if membership already exists
    existing_member = await get_community_member(db, community_server.id, profile_id)
    if existing_member:
        return existing_member

    # Create community membership
    try:
        member_create = CommunityMemberCreate(
            community_id=community_server.id,
            profile_id=profile_id,
            is_external=False,
            role=CommunityRole.MEMBER,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason=None,
        )

        member = await create_community_member(db, member_create)
        logger.info(
            "Created community membership",
            extra={
                "guild_id": guild_id,
                "community_id": str(community_server.id),
                "profile_id": str(profile_id),
            },
        )
        return member

    except IntegrityError:
        # Race condition: membership was created concurrently
        await db.rollback()
        return await get_community_member(db, community_server.id, profile_id)
