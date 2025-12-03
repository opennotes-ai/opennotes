"""
Centralized permission checking utilities for OpenNotes.

This module implements the permission hierarchy for admin access:
1. Service accounts (is_service_account=True) - highest priority
2. Open Notes admins (is_opennotes_admin=True) - cross-community admins
3. Community-specific admins (CommunityMember.role='admin')
4. Discord server admins (Manage Server permission) - fallback via Discord bot
"""

from src.users.models import User
from src.users.profile_models import CommunityMember, UserProfile


def is_service_account(user: User) -> bool:
    """
    Check if a User is a service account.

    Service accounts are identified by:
    - is_service_account flag on User model
    - Email ending with @opennotes.local
    - Username ending with -service

    Args:
        user: User instance to check

    Returns:
        True if user is a service account, False otherwise
    """
    return bool(
        user.is_service_account
        or (user.email and user.email.endswith("@opennotes.local"))
        or (user.username and user.username.endswith("-service"))
    )


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
