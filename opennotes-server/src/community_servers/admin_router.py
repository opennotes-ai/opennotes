"""
Community admin management API endpoints.

This module provides endpoints for managing community-level admin privileges.
Community admins can perform administrative actions within a specific Discord server
without requiring Discord's Manage Server permission.

Permission Hierarchy (any grants admin access):
1. Service accounts (automatic admin)
2. Open Notes platform admins (is_opennotes_admin=True)
3. Community admins (CommunityMember.role='admin')
4. Discord Manage Server permission (via Discord bot check)
"""

import logging
from typing import Annotated

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_community_server_by_platform_id,
    verify_community_admin,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.users.models import User
from src.users.profile_crud import (
    create_community_member,
    create_profile_with_identity,
    get_community_member,
    get_community_members,
    get_identity_by_provider,
    update_community_member,
)
from src.users.profile_models import CommunityMember
from src.users.profile_schemas import (
    AddCommunityAdminRequest,
    AdminSource,
    AuthProvider,
    CommunityAdminResponse,
    CommunityMemberCreate,
    CommunityMemberUpdate,
    CommunityRole,
    RemoveCommunityAdminResponse,
    UserProfileCreate,
)

router = APIRouter(
    prefix="/community-servers", tags=["community-admin"], responses=AUTHENTICATED_RESPONSES
)
logger = logging.getLogger(__name__)


async def _get_admin_sources(
    membership: CommunityMember | None,
    profile_is_opennotes_admin: bool,
) -> list[AdminSource]:
    """
    Determine all sources of admin privileges for a user.

    Args:
        membership: CommunityMember instance (can be None)
        profile_is_opennotes_admin: Whether profile has is_opennotes_admin=True

    Returns:
        List of AdminSource enum values
    """
    sources = []

    if profile_is_opennotes_admin:
        sources.append(AdminSource.OPENNOTES_PLATFORM)

    if membership and membership.role in ["admin", "moderator"]:
        sources.append(AdminSource.COMMUNITY_ROLE)

    return sources


@router.post("/{community_server_id}/admins", response_model=CommunityAdminResponse)
async def add_community_admin(
    community_server_id: str,
    request_body: AddCommunityAdminRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
) -> CommunityAdminResponse:
    """
    Add a user as admin for a specific community server.

    Sets CommunityMember.role = 'admin' for the specified user. Requires the requester
    to have existing admin privileges (service account, Open Notes admin, community admin,
    or Discord Manage Server permission).

    Args:
        community_server_id: Discord guild ID
        request_body: Request containing user_discord_id
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        CommunityAdminResponse: Updated community member information

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 400: Invalid input
    """
    # Verify requester is an admin
    await verify_community_admin(community_server_id, current_user, db, http_request)

    # Look up community server
    community = await get_community_server_by_platform_id(
        db, community_server_id, platform="discord", auto_create=False
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server {community_server_id} not found",
        )

    # Look up user by Discord ID, or create if doesn't exist
    identity = await get_identity_by_provider(
        db, AuthProvider.DISCORD, request_body.user_discord_id
    )

    if not identity:
        # Auto-create profile and identity for new users
        display_name = (
            request_body.display_name
            or request_body.username
            or f"Discord User {request_body.user_discord_id}"
        )

        profile_create = UserProfileCreate(
            display_name=display_name,
            avatar_url=request_body.avatar_url,
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
            db,
            profile_create,
            AuthProvider.DISCORD,
            request_body.user_discord_id,
            credentials=None,
        )

        logger.info(
            f"Auto-created profile {profile.id} and Discord identity for user {request_body.user_discord_id}"
        )
    else:
        profile = identity.profile

    # Get or create community membership
    membership = await get_community_member(db, community.id, profile.id)

    if not membership:
        # Create new membership with admin role
        member_create = CommunityMemberCreate(
            community_id=community.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=pendulum.now("UTC"),
            invited_by=None,
            invitation_reason="Promoted to admin",
        )
        membership = await create_community_member(db, member_create)
        await db.flush()
        await db.refresh(membership)
        logger.info(
            f"Created community membership and promoted user {profile.id} to admin "
            f"in community {community.id}"
        )
    elif membership.role != "admin":
        # Update existing membership to admin role
        member_update = CommunityMemberUpdate(
            role=CommunityRole.ADMIN,
            permissions=None,
            is_active=None,
            reputation_in_community=None,
            banned_at=None,
            banned_reason=None,
        )
        membership = await update_community_member(db, membership, member_update)
        await db.flush()
        await db.refresh(membership)
        logger.info(f"Promoted user {profile.id} to admin in community {community.id}")

    await db.commit()

    # Determine admin sources
    admin_sources = await _get_admin_sources(membership, profile.is_opennotes_admin)

    return CommunityAdminResponse(
        profile_id=profile.id,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        discord_id=request_body.user_discord_id,
        admin_sources=admin_sources,
        is_opennotes_admin=profile.is_opennotes_admin,
        community_role=membership.role,
        joined_at=membership.joined_at,
    )


@router.delete(
    "/{community_server_id}/admins/{user_discord_id}",
    response_model=RemoveCommunityAdminResponse,
)
async def remove_community_admin(
    community_server_id: str,
    user_discord_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
) -> RemoveCommunityAdminResponse:
    """
    Remove admin status from a user in a specific community server.

    Sets CommunityMember.role = 'member'. Prevents removing the last admin to ensure
    the community always has at least one admin.

    Args:
        community_server_id: Discord guild ID
        user_discord_id: Discord ID of user to demote
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        RemoveCommunityAdminResponse: Operation result

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 409: Cannot remove last admin
    """
    # Verify requester is an admin
    await verify_community_admin(community_server_id, current_user, db, http_request)

    # Look up community server
    community = await get_community_server_by_platform_id(
        db, community_server_id, platform="discord", auto_create=False
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server {community_server_id} not found",
        )

    # Look up user by Discord ID
    identity = await get_identity_by_provider(db, AuthProvider.DISCORD, user_discord_id)
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with Discord ID {user_discord_id} not found",
        )

    profile = identity.profile

    # Get community membership
    membership = await get_community_member(db, community.id, profile.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User is not a member of community {community_server_id}",
        )

    previous_role = membership.role

    # Check if user is currently an admin
    if membership.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User is not an admin (current role: {membership.role})",
        )

    # Count current community admins (excluding Open Notes platform admins who always have access)
    all_members = await get_community_members(db, community.id)
    community_admin_count = sum(
        1 for m in all_members if m.role == "admin" and m.is_active and not m.banned_at
    )

    # Prevent removing the last admin
    if community_admin_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the last admin. Promote another user to admin first.",
        )

    # Demote to member
    member_update = CommunityMemberUpdate(
        role=CommunityRole.MEMBER,
        permissions=None,
        is_active=None,
        reputation_in_community=None,
        banned_at=None,
        banned_reason=None,
    )
    membership = await update_community_member(db, membership, member_update)
    await db.flush()
    await db.commit()

    logger.info(f"Demoted user {profile.id} from admin to member in community {community.id}")

    return RemoveCommunityAdminResponse(
        success=True,
        message=f"User {profile.display_name} has been demoted from admin to member",
        profile_id=profile.id,
        previous_role=previous_role,
        new_role=membership.role,
    )


@router.get("/{community_server_id}/admins", response_model=list[CommunityAdminResponse])
async def list_community_admins(
    community_server_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    http_request: Request,
) -> list[CommunityAdminResponse]:
    """
    List all admins for a specific community server.

    Returns admins with their sources of admin privileges:
    - Open Notes platform admin (is_opennotes_admin=True)
    - Community admin (role='admin')
    - Discord Manage Server permission (checked by Discord bot)

    Args:
        community_server_id: Discord guild ID
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        List of CommunityAdminResponse with admin information

    Raises:
        HTTPException 404: Community server not found
        HTTPException 403: Not authorized
    """
    # Verify requester is an admin
    await verify_community_admin(community_server_id, current_user, db, http_request)

    # Look up community server
    community = await get_community_server_by_platform_id(
        db, community_server_id, platform="discord", auto_create=False
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server {community_server_id} not found",
        )

    # Get all community members
    all_members = await get_community_members(db, community.id)

    # Filter for admins or Open Notes platform admins
    admins = []
    for membership in all_members:
        profile = membership.profile
        is_admin = membership.role in ("admin", "moderator") or profile.is_opennotes_admin

        if is_admin and membership.is_active and not membership.banned_at:
            # Get Discord ID from user identity
            discord_identity = next(
                (
                    identity
                    for identity in profile.identities
                    if identity.provider == AuthProvider.DISCORD.value
                ),
                None,
            )

            if discord_identity:
                admin_sources = await _get_admin_sources(membership, profile.is_opennotes_admin)

                admins.append(
                    CommunityAdminResponse(
                        profile_id=profile.id,
                        display_name=profile.display_name,
                        avatar_url=profile.avatar_url,
                        discord_id=discord_identity.provider_user_id,
                        admin_sources=admin_sources,
                        is_opennotes_admin=profile.is_opennotes_admin,
                        community_role=membership.role,
                        joined_at=membership.joined_at,
                    )
                )

    logger.info(f"Listed {len(admins)} admins for community {community.id}")

    return admins
