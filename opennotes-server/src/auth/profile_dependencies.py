"""
FastAPI dependency injection for profile-based authentication.

This module provides dependencies for endpoints that require authentication
using the new UserProfile/UserIdentity pattern. It supports backward compatibility
with the legacy User-based authentication during the transition period.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth import verify_token
from src.auth.profile_auth import verify_profile_token
from src.database import get_db
from src.users.crud import get_user_by_id
from src.users.models import User
from src.users.profile_crud import (
    get_identity_by_provider,
    get_profile_by_id,
)
from src.users.profile_models import UserProfile
from src.users.profile_schemas import AuthProvider

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_profile(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfile:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    profile_token_data = await verify_profile_token(token)

    if profile_token_data is not None:
        profile = await get_profile_by_id(db, profile_token_data.profile_id)

        if profile is not None:
            return profile

    legacy_token_data = await verify_token(token)

    if legacy_token_data is not None:
        user = await get_user_by_id(db, legacy_token_data.user_id)

        if user is not None:
            legacy_profile = await _get_profile_from_user(db, user)
            if legacy_profile is not None:
                return legacy_profile

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Profile migration required. Please call POST /api/v1/auth/migrate-profile to migrate your account.",
                headers={"X-Migration-Required": "true"},
            )

    raise credentials_exception


async def get_current_active_profile(
    current_profile: Annotated[UserProfile, Depends(get_current_profile)],
) -> UserProfile:
    if not current_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_profile


def require_profile_role(required_role: str) -> Callable[..., Awaitable[UserProfile]]:
    """
    Dependency that verifies the current user profile has the required platform-level role.

    Args:
        required_role: Minimum role required ('user', 'moderator', 'admin')

    Returns:
        Callable dependency that returns the UserProfile if authorized

    Raises:
        HTTPException: 403 if user doesn't have the required role level
    """

    async def role_checker(
        current_profile: Annotated[UserProfile, Depends(get_current_active_profile)],
    ) -> UserProfile:
        role_hierarchy = {
            "user": 0,
            "moderator": 1,
            "admin": 2,
        }

        user_level = role_hierarchy.get(current_profile.role, 0)
        required_level = role_hierarchy.get(required_role, 999)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. User role '{current_profile.role}' < required role '{required_role}'",
            )

        return current_profile

    return role_checker


async def _get_profile_from_user(db: AsyncSession, user: User) -> UserProfile | None:
    if user.discord_id:
        provider = AuthProvider.DISCORD
        provider_user_id = user.discord_id
    else:
        provider = AuthProvider.EMAIL
        provider_user_id = user.email

    existing_identity = await get_identity_by_provider(db, provider, provider_user_id)

    if existing_identity:
        return existing_identity.profile

    return None
