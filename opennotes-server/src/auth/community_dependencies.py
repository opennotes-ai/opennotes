"""
FastAPI dependency injection for community-based authorization.

This module provides dependencies for endpoints that require authorization
to access community resources. It verifies that users are members of the
community and optionally checks for admin/moderator roles.

SECURITY NOTE (task-682):
Discord permissions (like Manage Server) are only trusted from:
1. Signed JWT in X-Discord-Claims header (created by Discord bot)
2. Service accounts (authenticated via API key)

Raw X-Discord-* headers are stripped by HeaderStrippingMiddleware
to prevent spoofing attacks.
"""

import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.auth.discord_claims import get_discord_manage_server_from_request
from src.auth.permissions import (
    has_community_admin_access,
    is_service_account,
)
from src.database import get_db
from src.llm_config.models import CommunityServer
from src.users.models import User
from src.users.profile_crud import (
    create_community_member,
    create_profile_with_identity,
    get_community_member,
    get_identity_by_provider,
    get_profile_by_id,
)
from src.users.profile_models import CommunityMember, UserProfile
from src.users.profile_schemas import (
    AuthProvider,
    CommunityMemberCreate,
    CommunityRole,
    UserProfileCreate,
)


async def _get_profile_id_from_user(db: AsyncSession, user: User) -> UUID | None:
    """
    Convert a User to profile_id by looking up their identity.

    For service accounts, automatically creates UserProfile and UserIdentity
    if they don't exist, enabling bot users to access protected endpoints.

    Args:
        db: Database session
        user: User instance from authentication

    Returns:
        UUID of the user's profile, or None if profile cannot be determined
    """
    if user.discord_id:
        provider = AuthProvider.DISCORD
        provider_user_id = user.discord_id
    elif user.email:
        provider = AuthProvider.EMAIL
        provider_user_id = user.email
    else:
        return None

    identity = await get_identity_by_provider(db, provider, provider_user_id)
    if identity:
        return identity.profile_id

    # If no identity exists and this is a service account, auto-create profile + identity
    if is_service_account(user):
        profile_create = UserProfileCreate(
            display_name=user.username or user.email,
            avatar_url=None,
            bio=f"Service account: {user.full_name or user.username}",
            role="user",
            is_opennotes_admin=False,
            is_human=False,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )
        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=provider,
            provider_user_id=provider_user_id,
            credentials=None,
        )
        return profile.id

    return None


def _is_uuid_format(value: str) -> bool:
    """Check if a string looks like a UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)."""
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return bool(re.match(uuid_pattern, value.lower()))


async def get_community_server_by_platform_id(
    db: AsyncSession, community_server_id: str, platform: str = "discord", auto_create: bool = True
) -> CommunityServer | None:
    """
    Look up CommunityServer by platform_community_server_id (e.g., Discord guild ID).

    Args:
        db: Database session
        community_server_id: Platform-specific community ID (must be platform-native format)
        platform: Platform type (default: "discord")
        auto_create: If True, automatically create the community server if it doesn't exist

    Returns:
        CommunityServer instance, or None if not found and auto_create=False

    Raises:
        HTTPException: 400 if community_server_id format is invalid for the platform
    """
    if platform == "discord" and _is_uuid_format(community_server_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Discord community server ID: '{community_server_id}'. "
            "Discord IDs are numeric snowflakes, not UUIDs. "
            "Use the Discord guild ID, not the internal community server UUID.",
        )

    result = await db.execute(
        select(CommunityServer).where(
            CommunityServer.platform_community_server_id == community_server_id,
            CommunityServer.platform == platform,
        )
    )
    server = result.scalar_one_or_none()

    if not server and auto_create:
        # Auto-create community server with default values
        server = CommunityServer(
            platform=platform,
            platform_community_server_id=community_server_id,
            name=f"{platform.capitalize()} Server {community_server_id}",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.flush()  # Flush to get the ID but don't commit yet
        await db.refresh(server)

    return server


async def _ensure_membership_with_permissions(
    community: CommunityServer,
    profile: UserProfile,
    has_discord_manage_server: bool,
    db: AsyncSession,
) -> CommunityMember:
    """
    Ensure user has membership, creating it if needed for Discord admins or service accounts.

    Args:
        community: Community server instance
        profile: User profile instance
        has_discord_manage_server: Whether user has Discord Manage Server permission
        db: Database session

    Returns:
        CommunityMember: The user's membership record

    Raises:
        HTTPException: 403 if user is not a member and doesn't qualify for auto-creation
    """
    membership = await get_community_member(db, community.id, profile.id)

    # Auto-create membership for service accounts (bots) or Discord server admins
    if not membership:
        should_auto_create = (
            not profile.is_human  # Service accounts
            or has_discord_manage_server  # Discord server admins
        )

        if should_auto_create:
            invitation_reason = (
                "Auto-created for service account"
                if not profile.is_human
                else "Auto-created for Discord server admin with Manage Server permission"
            )
            member_create = CommunityMemberCreate(
                community_id=community.id,
                profile_id=profile.id,
                is_external=False,
                role=CommunityRole.MEMBER,
                permissions=None,
                joined_at=datetime.now(UTC),
                invited_by=None,
                invitation_reason=invitation_reason,
            )
            membership = await create_community_member(db, member_create)
            await db.flush()

    if not membership or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User is not a member of community server {community.id}",
        )

    # Skip banned_at check for service accounts (controlled via API key revocation)
    if profile.is_human and membership.banned_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is banned from this community server",
        )

    return membership


async def verify_community_membership(
    community_server_id: str,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CommunityMember:
    """
    Verify that the current user is a member of the specified community.

    Community servers are auto-created if they don't exist (with default config).
    Service accounts (bots) are auto-granted membership with role="member".
    This allows the Discord bot to work immediately after joining a guild.

    Args:
        community_server_id: Platform-specific community ID (e.g., Discord guild ID)
        current_user: Current authenticated user
        db: Database session

    Returns:
        CommunityMember: The user's membership record

    Raises:
        HTTPException: 403 if user is not a member or is banned
    """
    # Auto-create community server if it doesn't exist
    community = await get_community_server_by_platform_id(db, community_server_id, auto_create=True)
    if not community:
        # This should never happen with auto_create=True, but handle it safely
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create or retrieve community server {community_server_id}",
        )

    profile_id = await _get_profile_id_from_user(db, current_user)
    if not profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Cannot verify community membership.",
        )

    # Fetch profile
    profile = await get_profile_by_id(db, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Cannot verify community membership.",
        )

    # Get Discord permission from signed JWT claims (secure)
    # Raw X-Discord-Has-Manage-Server header is stripped by middleware
    has_discord_manage_server = get_discord_manage_server_from_request(dict(request.headers))

    # Use shared membership validation and auto-creation logic
    return await _ensure_membership_with_permissions(
        community=community,
        profile=profile,
        has_discord_manage_server=has_discord_manage_server,
        db=db,
    )


async def verify_community_admin(
    community_server_id: str,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CommunityMember:
    """
    Verify that the current user is an admin or moderator of the specified community.

    Implements permission hierarchy:
    1. Service accounts - always granted admin access
    2. Open Notes admins (is_opennotes_admin=True) - cross-community admins
    3. Discord Manage Server permission (from signed JWT in X-Discord-Claims header)
    4. Community admins/moderators (role='admin'/'moderator')

    SECURITY NOTE (task-682):
    Discord permissions are ONLY trusted from signed JWT claims.
    Raw X-Discord-* headers are stripped by HeaderStrippingMiddleware.

    Args:
        community_server_id: Platform-specific community ID (e.g., Discord guild ID)
        current_user: Current authenticated user
        db: Database session
        request: HTTP request (for reading Discord permission headers)

    Returns:
        CommunityMember: The user's membership record

    Raises:
        HTTPException: 404 if community not found, 403 if user is not an admin/moderator
    """
    # Get membership (with auto-creation for service accounts and Discord admins)
    membership = await verify_community_membership(community_server_id, current_user, db, request)

    # Get Discord permission from signed JWT claims (secure)
    # Raw X-Discord-Has-Manage-Server header is stripped by middleware
    has_discord_manage_server = get_discord_manage_server_from_request(dict(request.headers))

    # Use centralized permission check with hierarchy
    if not has_community_admin_access(
        membership=membership,
        profile=membership.profile,
        user=current_user,
        has_discord_manage_server=has_discord_manage_server,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. User role '{membership.role}' cannot perform this action. Required: admin, moderator, Discord Manage Server permission, or Open Notes admin.",
        )

    return membership


async def verify_community_membership_by_uuid(
    community_server_id: UUID,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CommunityMember:
    """
    Verify that the current user is a member of the specified community (by UUID).

    This dependency verifies membership without requiring admin/moderator privileges.
    Use this for endpoints that need to verify the user belongs to a community
    but don't require elevated permissions.

    Community membership is auto-created for:
    - Service accounts (bots) - always granted membership
    - Users with Discord Manage Server permission (from signed JWT)

    SECURITY NOTE (task-682):
    Discord permissions are ONLY trusted from signed JWT claims.
    Raw X-Discord-* headers are stripped by HeaderStrippingMiddleware.

    Args:
        community_server_id: Community server database UUID
        current_user: Current authenticated user
        db: Database session
        request: HTTP request (for reading Discord permission headers)

    Returns:
        CommunityMember: The user's membership record

    Raises:
        HTTPException: 404 if community not found, 403 if user is not a member
    """
    result = await db.execute(
        select(CommunityServer).where(CommunityServer.id == community_server_id)
    )
    community = result.scalar_one_or_none()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server {community_server_id} not found",
        )

    profile_id = await _get_profile_id_from_user(db, current_user)
    if not profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Cannot verify community membership.",
        )

    profile = await get_profile_by_id(db, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Cannot verify community membership.",
        )

    has_discord_manage_server = get_discord_manage_server_from_request(dict(request.headers))

    return await _ensure_membership_with_permissions(
        community=community,
        profile=profile,
        has_discord_manage_server=has_discord_manage_server,
        db=db,
    )


async def verify_community_admin_by_uuid(
    community_server_id: UUID,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CommunityMember:
    """
    Verify that the current user is an admin or moderator of the specified community (by UUID).

    Implements permission hierarchy:
    1. Service accounts - always granted admin access
    2. Open Notes admins (is_opennotes_admin=True) - cross-community admins
    3. Discord Manage Server permission (from signed JWT in X-Discord-Claims header)
    4. Community admins/moderators (role='admin'/'moderator')

    SECURITY NOTE (task-682):
    Discord permissions are ONLY trusted from signed JWT claims.
    Raw X-Discord-* headers are stripped by HeaderStrippingMiddleware.

    Args:
        community_server_id: Community server database UUID
        current_user: Current authenticated user
        db: Database session
        request: HTTP request (for reading Discord permission headers)

    Returns:
        CommunityMember: The user's membership record

    Raises:
        HTTPException: 404 if community not found, 403 if user is not an admin/moderator
    """
    # Look up community by UUID
    result = await db.execute(
        select(CommunityServer).where(CommunityServer.id == community_server_id)
    )
    community = result.scalar_one_or_none()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server {community_server_id} not found",
        )

    profile_id = await _get_profile_id_from_user(db, current_user)
    if not profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Cannot verify community membership.",
        )

    profile = await get_profile_by_id(db, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Cannot verify community membership.",
        )

    # Get Discord permission from signed JWT claims (secure)
    # Raw X-Discord-Has-Manage-Server header is stripped by middleware
    has_discord_manage_server = get_discord_manage_server_from_request(dict(request.headers))

    # Use shared membership validation and auto-creation logic
    membership = await _ensure_membership_with_permissions(
        community=community,
        profile=profile,
        has_discord_manage_server=has_discord_manage_server,
        db=db,
    )

    # Use centralized permission check with hierarchy
    if not has_community_admin_access(
        membership=membership,
        profile=membership.profile,
        user=current_user,
        has_discord_manage_server=has_discord_manage_server,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. User role '{membership.role}' cannot perform this action. Required: admin, moderator, Discord Manage Server permission, or Open Notes admin.",
        )

    return membership


async def get_user_community_ids(
    current_user: User,
    db: AsyncSession,
) -> list[UUID]:
    """
    Get all community server IDs that the user is an active member of.

    For service accounts, returns an empty list (caller should bypass filtering).
    For regular users, returns UUIDs of all communities they can access.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        List of community server UUIDs the user is a member of.
        Empty list if user has no profile or no memberships.
    """
    if is_service_account(current_user):
        return []

    profile_id = await _get_profile_id_from_user(db, current_user)
    if not profile_id:
        return []

    result = await db.execute(
        select(CommunityMember.community_id).where(
            CommunityMember.profile_id == profile_id,
            CommunityMember.is_active == True,
            CommunityMember.banned_at.is_(None),
        )
    )
    return list(result.scalars().all())
