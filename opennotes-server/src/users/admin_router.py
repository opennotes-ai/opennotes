"""
Admin endpoints for managing OpenNotes-wide administrative privileges.

This module provides endpoints for super-administrators to grant/revoke
Open Notes admin privileges to user profiles. Open Notes admins have cross-community
administrative access.

Security:
- All endpoints require the requester to be a service account
- Service accounts are the only entities allowed to grant/revoke Open Notes admin status
- Changes are logged for audit purposes
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.users.models import User
from src.users.profile_crud import get_profile_by_id, update_profile
from src.users.profile_schemas import UserProfileResponse, UserProfileUpdate

router = APIRouter(
    prefix="/api/v1/admin/profiles", tags=["admin"], responses=AUTHENTICATED_RESPONSES
)
logger = logging.getLogger(__name__)


async def verify_service_account(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    """
    Verify that the current user is a service account.

    Only service accounts are allowed to grant/revoke Open Notes admin status.

    Args:
        current_user: Current authenticated user

    Returns:
        User: The service account user

    Raises:
        HTTPException: 403 if user is not a service account
    """
    if not is_service_account(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can perform this action",
        )
    return current_user


@router.patch("/{profile_id}/opennotes-admin", response_model=UserProfileResponse)
async def set_opennotes_admin_status(
    profile_id: UUID,
    is_admin: bool,
    db: Annotated[AsyncSession, Depends(get_db)],
    service_account: Annotated[User, Depends(verify_service_account)],
) -> UserProfileResponse:
    """
    Grant or revoke Open Notes admin status for a user profile.

    Open Notes admins have cross-community administrative privileges. This endpoint
    is restricted to service accounts only.

    Args:
        profile_id: UUID of the profile to modify
        is_admin: True to grant admin status, False to revoke
        db: Database session
        service_account: Service account making the request

    Returns:
        UserProfileResponse: Updated profile with new admin status

    Raises:
        HTTPException 404: If profile not found
        HTTPException 403: If requester is not a service account
    """
    try:
        profile = await get_profile_by_id(db, profile_id)

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile {profile_id} not found",
            )

        action = "granted" if is_admin else "revoked"
        logger.info(
            f"Open Notes admin status {action} for profile {profile_id} "
            f"by service account {service_account.username}"
        )

        profile_update = UserProfileUpdate(is_opennotes_admin=is_admin)
        updated_profile = await update_profile(db, profile, profile_update, bypass_admin_check=True)

        await db.commit()
        await db.refresh(updated_profile)

        return UserProfileResponse.model_validate(updated_profile)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise


@router.get("/{profile_id}/opennotes-admin", response_model=dict[str, bool])
async def get_opennotes_admin_status(
    profile_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _service_account: Annotated[User, Depends(verify_service_account)],
) -> dict[str, bool]:
    """
    Get the Open Notes admin status for a user profile.

    Args:
        profile_id: UUID of the profile to check
        db: Database session
        _service_account: Service account making the request (required)

    Returns:
        dict: {"is_opennotes_admin": bool}

    Raises:
        HTTPException 404: If profile not found
        HTTPException 403: If requester is not a service account
    """
    profile = await get_profile_by_id(db, profile_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )

    return {"is_opennotes_admin": profile.is_opennotes_admin}
