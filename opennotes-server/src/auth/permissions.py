"""
Centralized permission checking utilities for OpenNotes.

This module implements the permission hierarchy for admin access:
1. Service accounts (is_service_account=True) - highest priority
2. Open Notes admins (is_opennotes_admin=True) - cross-community admins
3. Community-specific admins (CommunityMember.role='admin')
4. Discord server admins (Manage Server permission) - fallback via Discord bot
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User
from src.users.profile_models import CommunityMember, UserProfile

if TYPE_CHECKING:
    from src.auth.platform_claims import PlatformIdentity


def is_account_active(user: User) -> bool:
    return user.is_active and user.banned_at is None


def has_platform_role(user: User, role: str) -> bool:
    return role in (user.platform_roles or [])


def is_platform_admin(user: User) -> bool:
    return has_platform_role(user, "platform_admin")


def is_system_principal(user: User) -> bool:
    return user.principal_type == "system"


async def set_platform_admin(db: AsyncSession, user: User, is_admin: bool) -> None:
    if is_admin:
        if "platform_admin" not in (user.platform_roles or []):
            user.platform_roles = (user.platform_roles or []) + ["platform_admin"]
        user.is_superuser = True
    else:
        user.platform_roles = [r for r in (user.platform_roles or []) if r != "platform_admin"]
        user.is_superuser = False
    await db.flush()


def is_service_account(user: User) -> bool:
    return user.principal_type in ("agent", "system")


def is_opennotes_admin(profile: UserProfile) -> bool:
    """
    Check if a UserProfile has Open Notes admin privileges.

    Open Notes admins have cross-community administrative access.

    Args:
        profile: UserProfile instance to check

    Returns:
        True if profile has is_opennotes_admin flag, False otherwise
    """
    return bool(profile.is_opennotes_admin)


def is_community_admin(membership: CommunityMember) -> bool:
    """
    Check if a CommunityMember has admin role in their community.

    Args:
        membership: CommunityMember instance to check

    Returns:
        True if membership has 'admin' or 'moderator' role, False otherwise
    """
    return membership.role in ["admin", "moderator"]


def has_community_admin_access(
    membership: CommunityMember | None,
    profile: UserProfile | None = None,
    user: User | None = None,
    has_discord_manage_server: bool = False,
) -> bool:
    """
    Determine if a user has admin access to a community.

    Implements the permission hierarchy:
    1. Service accounts always have access (controlled via API key revocation)
    2. Open Notes admins always have access (cross-community privilege)
    3. Discord Manage Server permission (server owners/admins)
    4. Community admins/moderators have access
    5. Regular members do not have access

    Args:
        membership: CommunityMember instance (can be None for service accounts)
        profile: UserProfile instance (required for is_opennotes_admin check)
        user: User instance (required for service account check)
        has_discord_manage_server: Whether user has Discord Manage Server permission

    Returns:
        True if user has admin access, False otherwise
    """
    # Priority 1: Service accounts
    if user and is_service_account(user):
        return True

    # Priority 2: Open Notes admins
    if profile and is_opennotes_admin(profile):
        return True

    # Priority 3: Discord Manage Server permission (server owners/admins)
    if has_discord_manage_server:
        return True

    # Priority 4: Community-specific admins/moderators
    return bool(membership and is_community_admin(membership))


def has_community_member_access(
    membership: CommunityMember | None,
    profile: UserProfile | None = None,
    user: User | None = None,
) -> bool:
    """
    Determine if a user has member-level access to a community.

    This checks if a user can perform basic operations (reading, writing notes, etc.).

    Args:
        membership: CommunityMember instance (can be None for service accounts)
        profile: UserProfile instance (required for Open Notes admin check)
        user: User instance (required for service account check)

    Returns:
        True if user has member access, False otherwise
    """
    # Service accounts and Open Notes admins automatically have member access
    if user and is_service_account(user):
        return True

    if profile and is_opennotes_admin(profile):
        return True

    # Check if membership exists and is active
    return bool(membership and membership.is_active and not membership.banned_at)


def extract_identity_audit_fields(
    identity: PlatformIdentity | None,
    source: str | None = None,
) -> dict[str, str]:
    if identity is None:
        return {}
    fields: dict[str, str] = {
        "platform_identity_sub": identity.sub,
        "platform_identity_scope": identity.scope,
        "platform_identity_community_id": identity.community_id,
        "platform_identity_platform": identity.platform,
    }
    if source is not None:
        fields["platform_identity_source"] = source
    return fields
