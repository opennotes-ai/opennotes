"""JSON:API v2 profiles router.

This module implements a JSON:API 1.1 compliant endpoint for user profiles.
It provides:
- Standard JSON:API response envelope structure
- Profile retrieval (current user and public profiles)
- Profile update operations
- Community membership listing
- Identity management (list, link, unlink)
- Admin status operations (get, update)
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.auth.profile_dependencies import get_current_active_profile
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
    JSONAPIMeta,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.database import get_db
from src.monitoring import get_logger
from src.users.audit_helper import extract_request_context
from src.users.models import User
from src.users.profile_crud import (
    count_communities_for_profile,
    count_identities_for_profile,
    create_identity,
    delete_identity,
    get_identities_by_profile,
    get_identity_by_id,
    get_identity_by_provider,
    get_or_create_profile_from_discord,
    get_profile_by_id,
    get_profile_communities,
    update_profile,
)
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile
from src.users.profile_schemas import (
    AuthProvider,
    UserIdentityCreate,
    UserProfileSelfUpdate,
    UserProfileUpdate,
)

logger = get_logger(__name__)

router = APIRouter(tags=["profiles-jsonapi"])


class ProfileAttributes(SQLAlchemySchema):
    """Profile attributes for JSON:API resource."""

    display_name: str
    avatar_url: str | None = None
    bio: str | None = None
    reputation: int = 0
    is_opennotes_admin: bool = False
    is_human: bool = True
    is_active: bool = True
    is_banned: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfileResource(BaseModel):
    """JSON:API resource object for a profile."""

    type: Literal["profiles"] = "profiles"
    id: str
    attributes: ProfileAttributes


class ProfileSingleResponse(SQLAlchemySchema):
    """JSON:API response for a single profile resource."""

    data: ProfileResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class CommunityMembershipAttributes(SQLAlchemySchema):
    """Community membership attributes for JSON:API resource."""

    community_id: str
    role: str
    is_external: bool = False
    is_active: bool = True
    joined_at: datetime | None = None
    reputation_in_community: int | None = None


class CommunityMembershipResource(BaseModel):
    """JSON:API resource object for a community membership."""

    type: Literal["community-memberships"] = "community-memberships"
    id: str
    attributes: CommunityMembershipAttributes


class CommunityMembershipListResponse(SQLAlchemySchema):
    """JSON:API response for a list of community membership resources."""

    data: list[CommunityMembershipResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class ProfileUpdateRequest(BaseModel):
    """JSON:API request for updating a profile."""

    model_config = ConfigDict(extra="forbid")

    data: "ProfileUpdateData"


class ProfileUpdateData(BaseModel):
    """JSON:API data object for profile update request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["profiles"] = "profiles"
    id: str
    attributes: "ProfileUpdateAttributes"


class ProfileUpdateAttributes(StrictInputSchema):
    """Attributes for profile update request."""

    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None


class IdentityAttributes(SQLAlchemySchema):
    """Identity attributes for JSON:API resource."""

    provider: str
    provider_user_id: str
    email_verified: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IdentityResource(BaseModel):
    """JSON:API resource object for an identity."""

    type: Literal["identities"] = "identities"
    id: str
    attributes: IdentityAttributes


class IdentitySingleResponse(SQLAlchemySchema):
    """JSON:API response for a single identity resource."""

    data: IdentityResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class IdentityListResponse(SQLAlchemySchema):
    """JSON:API response for a list of identity resources."""

    data: list[IdentityResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class IdentityCreateAttributes(StrictInputSchema):
    """Attributes for identity create request."""

    provider: str
    provider_user_id: str
    credentials: dict[str, Any] | None = None


class IdentityCreateData(BaseModel):
    """JSON:API data object for identity create request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["identities"] = "identities"
    attributes: IdentityCreateAttributes


class IdentityCreateRequest(BaseModel):
    """JSON:API request for creating an identity."""

    model_config = ConfigDict(extra="forbid")

    data: IdentityCreateData


class AdminStatusAttributes(SQLAlchemySchema):
    """Admin status attributes for JSON:API resource."""

    is_opennotes_admin: bool


class AdminStatusResource(BaseModel):
    """JSON:API resource object for admin status."""

    type: Literal["admin-status"] = "admin-status"
    id: str
    attributes: AdminStatusAttributes


class AdminStatusSingleResponse(SQLAlchemySchema):
    """JSON:API response for admin status resource."""

    data: AdminStatusResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class AdminStatusUpdateAttributes(StrictInputSchema):
    """Attributes for admin status update request."""

    is_opennotes_admin: bool


class AdminStatusUpdateData(BaseModel):
    """JSON:API data object for admin status update request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["admin-status"] = "admin-status"
    id: str
    attributes: AdminStatusUpdateAttributes


class AdminStatusUpdateRequest(BaseModel):
    """JSON:API request for updating admin status."""

    model_config = ConfigDict(extra="forbid")

    data: AdminStatusUpdateData


class UserProfileLookupAttributes(SQLAlchemySchema):
    """Attributes for user profile lookup response."""

    platform: str
    platform_user_id: str
    display_name: str | None = None


class UserProfileLookupResource(BaseModel):
    """JSON:API resource object for user profile lookup response."""

    type: Literal["user-profiles"] = "user-profiles"
    id: str
    attributes: UserProfileLookupAttributes


class UserProfileLookupResponse(SQLAlchemySchema):
    """JSON:API response for user profile lookup."""

    data: UserProfileLookupResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def profile_to_resource(profile: UserProfile) -> ProfileResource:
    """Convert a UserProfile model to a JSON:API resource object."""
    return ProfileResource(
        type="profiles",
        id=str(profile.id),
        attributes=ProfileAttributes(
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
            bio=profile.bio,
            reputation=profile.reputation,
            is_opennotes_admin=profile.is_opennotes_admin,
            is_human=profile.is_human,
            is_active=profile.is_active,
            is_banned=profile.is_banned,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        ),
    )


def membership_to_resource(member: CommunityMember) -> CommunityMembershipResource:
    """Convert a CommunityMember model to a JSON:API resource object."""
    return CommunityMembershipResource(
        type="community-memberships",
        id=str(member.id),
        attributes=CommunityMembershipAttributes(
            community_id=str(member.community_id),
            role=member.role,
            is_external=member.is_external,
            is_active=member.is_active,
            joined_at=member.joined_at,
            reputation_in_community=member.reputation_in_community,
        ),
    )


def identity_to_resource(identity: UserIdentity) -> IdentityResource:
    """Convert a UserIdentity model to a JSON:API resource object."""
    return IdentityResource(
        type="identities",
        id=str(identity.id),
        attributes=IdentityAttributes(
            provider=identity.provider,
            provider_user_id=identity.provider_user_id,
            email_verified=identity.email_verified,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
        ),
    )


def admin_status_to_resource(profile: UserProfile) -> AdminStatusResource:
    """Convert a UserProfile's admin status to a JSON:API resource object."""
    return AdminStatusResource(
        type="admin-status",
        id=str(profile.id),
        attributes=AdminStatusAttributes(
            is_opennotes_admin=profile.is_opennotes_admin,
        ),
    )


def create_error_response(
    status_code: int,
    title: str,
    detail: str | None = None,
) -> JSONResponse:
    """Create a JSON:API formatted error response as a JSONResponse."""
    error_response = create_error_response_model(
        status_code=status_code,
        title=title,
        detail=detail,
    )
    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(by_alias=True),
        media_type=JSONAPI_CONTENT_TYPE,
    )


async def get_current_profile_id(
    current_profile: Annotated[UserProfile, Depends(get_current_active_profile)],
) -> UUID:
    """Extract profile_id from the current authenticated profile."""
    return current_profile.id


async def verify_service_account(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    """
    Verify that the current user is a service account.

    Only service accounts are allowed to access admin status endpoints.
    """
    if not is_service_account(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can perform this action",
        )
    return current_user


@router.get("/profiles/me", response_class=JSONResponse, response_model=ProfileSingleResponse)
async def get_current_profile_jsonapi(
    request: HTTPRequest,
    profile_id: Annotated[UUID, Depends(get_current_profile_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Get the authenticated user's profile with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    """
    try:
        profile = await get_profile_by_id(db, profile_id)

        if not profile:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                "Profile not found",
            )

        profile_resource = profile_to_resource(profile)

        response = ProfileSingleResponse(
            data=profile_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get profile (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get profile",
        )


@router.get(
    "/profiles/me/identities", response_class=JSONResponse, response_model=IdentityListResponse
)
async def list_user_identities_jsonapi(
    request: HTTPRequest,
    profile_id: Annotated[UUID, Depends(get_current_profile_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """List all identities linked to the current user's profile with JSON:API format.

    Returns JSON:API formatted response with data array and jsonapi keys.

    Query Parameters:
        limit: Maximum number of identities to return (1-100, default 50)
        offset: Number of identities to skip (>=0, default 0)
    """
    if limit < 1 or limit > 100:
        return create_error_response(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Limit must be between 1 and 100",
        )

    if offset < 0:
        return create_error_response(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Offset must be non-negative",
        )

    try:
        total = await count_identities_for_profile(db, profile_id)
        identities = await get_identities_by_profile(db, profile_id, limit=limit, offset=offset)

        identity_resources = [identity_to_resource(identity) for identity in identities]

        response = IdentityListResponse(
            data=identity_resources,
            links=JSONAPILinks(self_=str(request.url)),
            meta=JSONAPIMeta(count=total, limit=limit, offset=offset),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list user identities (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list identities",
        )


@router.post(
    "/profiles/me/identities",
    response_class=JSONResponse,
    response_model=IdentitySingleResponse,
    status_code=201,
)
async def link_identity_jsonapi(
    request: HTTPRequest,
    create_request: IdentityCreateRequest,
    profile_id: Annotated[UUID, Depends(get_current_profile_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Link a new authentication identity to the current user's profile.

    JSON:API POST request should use standard JSON:API request body format
    with data object containing type and attributes.

    Security: Requires oauth_verified in credentials to prevent linking
    accounts the user doesn't own.
    """
    try:
        attrs = create_request.data.attributes

        if attrs.credentials is None or "oauth_verified" not in attrs.credentials:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                f"OAuth verification required. You must complete OAuth flow to verify "
                f"ownership of this provider account before linking. "
                f"Please initiate OAuth for {attrs.provider}.",
            )

        try:
            provider = AuthProvider(attrs.provider)
        except ValueError:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                f"Invalid provider: {attrs.provider}. Must be one of: discord, github, email",
            )

        existing_identity = await get_identity_by_provider(db, provider, attrs.provider_user_id)

        if existing_identity is not None:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                f"This {attrs.provider} account is already linked to a profile",
            )

        identity_create = UserIdentityCreate(
            profile_id=profile_id,
            provider=provider,
            provider_user_id=attrs.provider_user_id,
            credentials=attrs.credentials,
        )

        ip_address, user_agent = extract_request_context(request)
        new_identity = await create_identity(db, identity_create, ip_address, user_agent)
        await db.commit()

        identity_resource = identity_to_resource(new_identity)

        response = IdentitySingleResponse(
            data=identity_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to link identity (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to link identity",
        )


@router.delete("/profiles/me/identities/{identity_id}", response_model=None)
async def unlink_identity_jsonapi(
    request: HTTPRequest,
    identity_id: UUID,
    profile_id: Annotated[UUID, Depends(get_current_profile_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response | JSONResponse:
    """Unlink an authentication identity from the current user's profile.

    Note: Cannot unlink the last remaining identity. Users must have at least
    one authentication method linked to their profile.

    Returns 204 No Content on success.
    """
    try:
        stmt = select(UserProfile).where(UserProfile.id == profile_id).with_for_update()
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile is None:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                "Profile not found",
            )

        identity = await get_identity_by_id(db, identity_id)

        if identity is None or identity.profile_id != profile_id:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                "Identity not found or does not belong to your profile",
            )

        identity_count = await count_identities_for_profile(db, profile_id)

        if identity_count <= 1:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "Cannot unlink the last authentication identity. "
                "Users must have at least one authentication method linked to their profile.",
            )

        ip_address, user_agent = extract_request_context(request)
        success = await delete_identity(db, identity_id, profile_id, ip_address, user_agent)

        if not success:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                "Identity not found",
            )

        await db.commit()

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to unlink identity (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to unlink identity",
        )


@router.get(
    "/profiles/me/communities",
    response_class=JSONResponse,
    response_model=CommunityMembershipListResponse,
)
async def list_user_communities_jsonapi(
    request: HTTPRequest,
    profile_id: Annotated[UUID, Depends(get_current_profile_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """List all communities the current user is a member of with JSON:API format.

    Returns JSON:API formatted response with data array and jsonapi keys.

    Query Parameters:
        limit: Maximum number of communities to return (1-100, default 50)
        offset: Number of communities to skip (>=0, default 0)
    """
    if limit < 1 or limit > 100:
        return create_error_response(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Limit must be between 1 and 100",
        )

    if offset < 0:
        return create_error_response(
            status.HTTP_400_BAD_REQUEST,
            "Bad Request",
            "Offset must be non-negative",
        )

    try:
        total = await count_communities_for_profile(db, profile_id)

        communities = await get_profile_communities(db, profile_id, limit=limit, offset=offset)

        membership_resources = [membership_to_resource(member) for member in communities]

        response = CommunityMembershipListResponse(
            data=membership_resources,
            links=JSONAPILinks(self_=str(request.url)),
            meta=JSONAPIMeta(count=total, limit=limit, offset=offset),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list user communities (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list communities",
        )


@router.get(
    "/profiles/{profile_id}", response_class=JSONResponse, response_model=ProfileSingleResponse
)
async def get_public_profile_jsonapi(
    profile_id: UUID,
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Get a public profile by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.
    """
    try:
        profile = await get_profile_by_id(db, profile_id)

        if not profile:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Profile {profile_id} not found",
            )

        profile_resource = profile_to_resource(profile)

        response = ProfileSingleResponse(
            data=profile_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get public profile (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get profile",
        )


@router.get(
    "/profiles/{profile_id}/opennotes-admin",
    response_class=JSONResponse,
    response_model=AdminStatusSingleResponse,
)
async def get_admin_status_jsonapi(
    request: HTTPRequest,
    profile_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _service_account: Annotated[User, Depends(verify_service_account)],
) -> JSONResponse:
    """Get the Open Notes admin status for a user profile.

    Returns JSON:API formatted response with admin status data.

    Security: This endpoint is restricted to service accounts only.
    """
    try:
        profile = await get_profile_by_id(db, profile_id)

        if not profile:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Profile {profile_id} not found",
            )

        admin_resource = admin_status_to_resource(profile)

        response = AdminStatusSingleResponse(
            data=admin_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get admin status (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to get admin status",
        )


@router.patch(
    "/profiles/{profile_id}/opennotes-admin",
    response_class=JSONResponse,
    response_model=AdminStatusSingleResponse,
)
async def update_admin_status_jsonapi(
    request: HTTPRequest,
    profile_id: UUID,
    update_request: AdminStatusUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    service_account: Annotated[User, Depends(verify_service_account)],
) -> JSONResponse:
    """Grant or revoke Open Notes admin status for a user profile.

    JSON:API PATCH request should use standard JSON:API request body format
    with data object containing type, id, and attributes.

    Security: This endpoint is restricted to service accounts only.
    """
    try:
        profile = await get_profile_by_id(db, profile_id)

        if not profile:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Profile {profile_id} not found",
            )

        is_admin = update_request.data.attributes.is_opennotes_admin
        action = "granted" if is_admin else "revoked"
        logger.info(
            f"Open Notes admin status {action} for profile {profile_id} "
            f"by service account {service_account.username}"
        )

        profile_update = UserProfileUpdate(is_opennotes_admin=is_admin)
        updated_profile = await update_profile(db, profile, profile_update, bypass_admin_check=True)

        await db.commit()
        await db.refresh(updated_profile)

        admin_resource = admin_status_to_resource(updated_profile)

        response = AdminStatusSingleResponse(
            data=admin_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update admin status (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update admin status",
        )


@router.patch("/profiles/me", response_class=JSONResponse, response_model=ProfileSingleResponse)
async def update_profile_jsonapi(
    request: HTTPRequest,
    update_request: ProfileUpdateRequest,
    profile_id: Annotated[UUID, Depends(get_current_profile_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Update the authenticated user's profile with JSON:API format.

    Accepts JSON:API formatted request body with data object containing
    type, id, and attributes.

    Returns JSON:API formatted response with updated profile.
    """
    try:
        profile = await get_profile_by_id(db, profile_id)

        if not profile:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                "Profile not found",
            )

        update_data = update_request.data.attributes

        profile_update = UserProfileSelfUpdate(
            display_name=update_data.display_name,
            avatar_url=update_data.avatar_url,
            bio=update_data.bio,
        )

        try:
            updated_profile = await update_profile(db, profile, profile_update, profile_id)
            await db.commit()
        except ValueError as e:
            return create_error_response(
                status.HTTP_409_CONFLICT,
                "Conflict",
                str(e),
            )

        profile_resource = profile_to_resource(updated_profile)

        response = ProfileSingleResponse(
            data=profile_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update profile (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to update profile",
        )


@router.get(
    "/user-profiles/lookup",
    response_class=JSONResponse,
    response_model=UserProfileLookupResponse,
)
async def lookup_user_profile_jsonapi(
    request: HTTPRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    platform: str = Query("discord", description="Platform type"),
    platform_user_id: str = Query(
        ..., description="Platform-specific user ID (e.g., Discord user ID)"
    ),
) -> JSONResponse:
    """Look up a user profile by platform and platform user ID with JSON:API format.

    Returns the internal UUID for a user profile based on its platform-specific identifier.
    Auto-creates the profile if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: "discord")
        platform_user_id: Platform-specific user ID (e.g., Discord user ID)

    Returns:
        JSON:API formatted response with user profile details

    Raises:
        404: If user profile not found and user is not a service account
        400: If platform is not supported (currently only 'discord')
    """
    try:
        logger.info(
            "Looking up user profile (JSON:API)",
            extra={
                "user_id": current_user.id,
                "platform": platform,
                "platform_user_id": platform_user_id,
            },
        )

        # Currently only Discord is supported
        if platform != "discord":
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                f"Unsupported platform: {platform}. Currently only 'discord' is supported.",
            )

        # Check if identity already exists
        identity = await get_identity_by_provider(db, AuthProvider.DISCORD, platform_user_id)

        if identity:
            # Return existing profile
            profile = identity.profile
        else:
            # Auto-create only for service accounts (bots)
            if not is_service_account(current_user):
                return create_error_response(
                    status.HTTP_404_NOT_FOUND,
                    "Not Found",
                    f"User profile not found: {platform}:{platform_user_id}",
                )

            # Create new profile with Discord identity
            profile = await get_or_create_profile_from_discord(
                db=db,
                discord_user_id=platform_user_id,
                username=f"user_{platform_user_id}",  # Placeholder username
                display_name=None,
                avatar_url=None,
                platform_community_server_id=None,
            )
            await db.commit()
            await db.refresh(profile)

        lookup_resource = UserProfileLookupResource(
            type="user-profiles",
            id=str(profile.id),
            attributes=UserProfileLookupAttributes(
                platform=platform,
                platform_user_id=platform_user_id,
                display_name=profile.display_name,
            ),
        )

        response = UserProfileLookupResponse(
            data=lookup_resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to lookup user profile (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to lookup user profile",
        )
