"""Composable SQLAlchemy loader options for User relationships.

This module provides reusable loader option functions that can be composed
to create different loading strategies for UserProfile, CommunityMember,
and UserIdentity queries. Each function returns a tuple of loader options
that can be unpacked into select().options().

Example usage:
    from sqlalchemy import select
    from src.users.loaders import profile_full, member_full
    from src.users.profile_models import UserProfile, CommunityMember

    stmt = select(UserProfile).options(*profile_full())
    stmt = select(CommunityMember).options(*member_full())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

if TYPE_CHECKING:
    from sqlalchemy.orm.strategy_options import _AbstractLoad


def profile_identities() -> tuple[_AbstractLoad, ...]:
    """Load user profile identities.

    Returns:
        Tuple containing selectinload option for UserProfile.identities relationship.
    """
    return (selectinload(UserProfile.identities),)


def profile_memberships() -> tuple[_AbstractLoad, ...]:
    """Load user profile community memberships.

    Returns:
        Tuple containing selectinload option for UserProfile.community_memberships relationship.
    """
    return (selectinload(UserProfile.community_memberships),)


def profile_full() -> tuple[_AbstractLoad, ...]:
    """Standard loading for UserProfile - composes identities + memberships.

    This is the default loader for most profile queries that need
    complete relationship data.

    Returns:
        Tuple containing all options from profile_identities() and profile_memberships().
    """
    return (*profile_identities(), *profile_memberships())


def member_profile() -> tuple[_AbstractLoad, ...]:
    """Load community member's profile.

    Returns:
        Tuple containing selectinload option for CommunityMember.profile relationship.
    """
    return (selectinload(CommunityMember.profile),)


def member_inviter() -> tuple[_AbstractLoad, ...]:
    """Load community member's inviter.

    Returns:
        Tuple containing selectinload option for CommunityMember.inviter relationship.
    """
    return (selectinload(CommunityMember.inviter),)


def member_full() -> tuple[_AbstractLoad, ...]:
    """Standard loading for CommunityMember - composes profile + inviter.

    This is the default loader for most community member queries that need
    complete relationship data.

    Returns:
        Tuple containing all options from member_profile() and member_inviter().
    """
    return (*member_profile(), *member_inviter())


def identity_with_profile() -> tuple[_AbstractLoad, ...]:
    """Load identity with full profile (identities + memberships).

    Use this when querying UserIdentity and need the complete profile
    context including other identities and community memberships.

    Returns:
        Tuple containing chained selectinload options for UserIdentity.profile
        with nested UserProfile.identities and UserProfile.community_memberships.
    """
    return (
        selectinload(UserIdentity.profile).selectinload(UserProfile.identities),
        selectinload(UserIdentity.profile).selectinload(UserProfile.community_memberships),
    )
