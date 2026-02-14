"""
Profile-based authentication router.

This module provides authentication endpoints using the new UserProfile/UserIdentity
pattern. It supports Discord OAuth, email/password authentication, and maintains
backward compatibility with the legacy User-based system during the transition.

Transaction Management
----------------------
This module follows a consistent transaction boundary pattern:

1. Router endpoints manage transaction commits/rollbacks
2. CRUD functions use flush() to stage changes within transactions
3. All mutation endpoints wrap operations in try-except blocks
4. Commits happen explicitly after successful operations
5. Rollbacks happen automatically on any exception

Pattern:
    try:
        # Call CRUD functions (which use flush())
        profile, identity = await create_profile_with_identity(...)
        # Commit the transaction
        await db.commit()
        return profile
    except Exception:
        # Rollback on any error
        await db.rollback()
        raise

This ensures:
- No abandoned transactions holding locks
- Atomic operations (all-or-nothing)
- Proper cleanup on errors
- Consistent data integrity
"""

import logging
from typing import Annotated

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.discord_oauth import (
    DiscordOAuthError,
    verify_discord_user,
)
from src.auth.models import Token
from src.auth.oauth_state import (
    OAuthStateError,
    create_oauth_state_with_url,
    validate_oauth_state,
)
from src.auth.password import get_password_hash, verify_password
from src.auth.profile_auth import (
    create_profile_access_token,
    create_profile_refresh_token,
)
from src.auth.profile_dependencies import get_current_active_profile
from src.auth.revocation import revoke_token
from src.config import settings
from src.database import get_db
from src.middleware.rate_limiting import limiter
from src.services.email import email_service
from src.users.models import User
from src.users.profile_crud import (
    authenticate_with_provider,
    create_profile_with_identity,
    get_identity_by_provider,
    get_identity_by_verification_token,
    get_profile_by_display_name,
    update_identity,
    update_profile,
)
from src.users.profile_models import UserProfile
from src.users.profile_schemas import (
    AuthProvider,
    DiscordOAuthInitResponse,
    DiscordOAuthLoginRequest,
    DiscordOAuthRegisterRequest,
    UserProfileCreate,
    UserProfileResponse,
    UserProfileSelfUpdate,
)

router = APIRouter(prefix="/api/v1/profile", tags=["profile-auth"])
logger = logging.getLogger(__name__)


@router.get("/auth/discord/init", response_model=DiscordOAuthInitResponse)
@limiter.limit("10/minute")
async def init_discord_oauth(request: Request) -> DiscordOAuthInitResponse:
    """
    Initialize Discord OAuth2 flow with CSRF protection.

    This endpoint:
    1. Generates a cryptographically secure state parameter
    2. Stores the state in Redis with a 10-minute TTL
    3. Returns the Discord authorization URL with the state parameter

    The client should:
    1. Store the returned state value
    2. Redirect the user to the authorization_url
    3. On callback, send both the code AND state to register/login endpoints

    Security: The state parameter prevents CSRF attacks by ensuring the OAuth
    callback was initiated by this application.
    """
    try:
        state, authorization_url = await create_oauth_state_with_url()
        return DiscordOAuthInitResponse(
            authorization_url=authorization_url,
            state=state,
        )
    except OAuthStateError as e:
        logger.error(f"Failed to initialize Discord OAuth: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth service temporarily unavailable",
        ) from e


@router.post(
    "/auth/register/discord",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/hour")
async def register_discord(
    request: Request,
    oauth_request: DiscordOAuthRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfile:
    """
    Register a new user with Discord OAuth2.

    This endpoint:
    1. Validates the state parameter against stored state (CSRF protection)
    2. Exchanges the authorization code for an access token
    3. Fetches the user's Discord information to verify identity
    4. Creates a new user profile with verified Discord credentials
    5. Stores OAuth tokens securely in the credentials field

    Security: Prevents CSRF attacks via state validation and identity spoofing
    by verifying Discord ownership via OAuth2.
    """
    try:
        try:
            is_valid_state = await validate_oauth_state(oauth_request.state)
            if not is_valid_state:
                logger.warning("Discord OAuth registration failed: invalid or expired state")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired OAuth state. Please restart the authentication flow.",
                )
        except OAuthStateError as e:
            logger.error(f"OAuth state validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OAuth service temporarily unavailable",
            ) from e

        try:
            user_data, token_data = await verify_discord_user(
                code=oauth_request.code,
                client_id=settings.DISCORD_CLIENT_ID,
                client_secret=settings.DISCORD_CLIENT_SECRET,
                redirect_uri=settings.DISCORD_OAUTH_REDIRECT_URI,
            )
        except DiscordOAuthError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Discord OAuth verification failed: {e!s}",
            ) from e

        discord_id = user_data["id"]

        existing_identity = await get_identity_by_provider(db, AuthProvider.DISCORD, discord_id)

        if existing_identity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discord account already registered",
            )

        default_avatar_url = None
        if user_data.get("avatar"):
            default_avatar_url = (
                f"https://cdn.discordapp.com/avatars/{discord_id}/{user_data['avatar']}.png"
            )

        profile_create = UserProfileCreate(
            display_name=oauth_request.display_name,
            avatar_url=oauth_request.avatar_url or default_avatar_url,
            bio=None,
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, _identity = await create_profile_with_identity(
            db,
            profile_create,
            AuthProvider.DISCORD,
            discord_id,
            credentials={
                "discord_id": discord_id,
                "discord_username": user_data.get("username"),
                "discord_discriminator": user_data.get("discriminator"),
                "access_token": token_data["access_token"],
                "token_type": token_data.get("token_type", "Bearer"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in"),
                "scope": token_data.get("scope"),
            },
        )

        await db.commit()
        await db.refresh(profile)

        return profile
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/auth/register/email", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("3/hour")
async def register_email(
    request: Request,
    email: str,
    password: str,
    display_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfile:
    try:
        existing_identity = await get_identity_by_provider(db, AuthProvider.EMAIL, email)

        if existing_identity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        existing_profile = await get_profile_by_display_name(db, display_name)

        if existing_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Display name already taken",
            )

        hashed_password = get_password_hash(password)

        verification_token = email_service.generate_verification_token()
        token_expiry = email_service.generate_token_expiry()

        profile_create = UserProfileCreate(
            display_name=display_name,
            avatar_url=None,
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
            AuthProvider.EMAIL,
            email,
            credentials={"email": email, "hashed_password": hashed_password},
        )

        await update_identity(
            db,
            identity,
            {
                "email_verified": False,
                "email_verification_token": verification_token,
                "email_verification_token_expires": token_expiry,
            },
        )

        await db.commit()
        await db.refresh(profile)

        try:
            await email_service.send_verification_email(
                to_email=email,
                display_name=display_name,
                verification_token=verification_token,
            )
        except Exception as e:
            logger.error(f"Failed to send verification email to {email}: {e}")

        return profile
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/login/discord", response_model=Token)
@limiter.limit("5/15minutes")
async def login_discord(
    request: Request,
    oauth_request: DiscordOAuthLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """
    Login with Discord OAuth2.

    This endpoint:
    1. Validates the state parameter against stored state (CSRF protection)
    2. Exchanges the authorization code for an access token
    3. Fetches the user's Discord information to verify identity
    4. Authenticates the user and issues JWT tokens

    Security: Prevents CSRF attacks via state validation and verifies
    Discord account ownership via OAuth2 before login.
    """
    try:
        is_valid_state = await validate_oauth_state(oauth_request.state)
        if not is_valid_state:
            logger.warning("Discord OAuth login failed: invalid or expired state")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state. Please restart the authentication flow.",
            )
    except OAuthStateError as e:
        logger.error(f"OAuth state validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth service temporarily unavailable",
        ) from e

    try:
        user_data, _token_data = await verify_discord_user(
            code=oauth_request.code,
            client_id=settings.DISCORD_CLIENT_ID,
            client_secret=settings.DISCORD_CLIENT_SECRET,
            redirect_uri=settings.DISCORD_OAUTH_REDIRECT_URI,
        )
    except DiscordOAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Discord OAuth verification failed: {e!s}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    discord_id = user_data["id"]

    profile = await authenticate_with_provider(db, AuthProvider.DISCORD, discord_id)

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Discord account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = pendulum.duration(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_profile_access_token(
        profile.id,
        profile.display_name,
        AuthProvider.DISCORD.value,
        expires_delta=access_token_expires,
    )

    refresh_token = create_profile_refresh_token(
        profile.id, profile.display_name, AuthProvider.DISCORD.value
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/auth/login/email", response_model=Token)
@limiter.limit("5/15minutes")
async def login_email(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    identity = await get_identity_by_provider(db, AuthProvider.EMAIL, form_data.username)

    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stored_password_hash = (
        identity.credentials.get("hashed_password") if identity.credentials else None
    )

    if stored_password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_valid, needs_rehash = verify_password(form_data.password, stored_password_hash)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if needs_rehash and identity.credentials is not None:
        new_hash = get_password_hash(form_data.password)
        identity.credentials = {**identity.credentials, "hashed_password": new_hash}
        await db.commit()

    if not identity.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your email for a verification link.",
        )

    profile = identity.profile

    access_token_expires = pendulum.duration(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_profile_access_token(
        profile.id,
        profile.display_name,
        AuthProvider.EMAIL.value,
        expires_delta=access_token_expires,
    )

    refresh_token = create_profile_refresh_token(
        profile.id, profile.display_name, AuthProvider.EMAIL.value
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/auth/verify-email", response_model=UserProfileResponse)
@limiter.limit("10/hour")
async def verify_email(
    request: Request,
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfile:
    """
    Verify a user's email address using the verification token.

    This endpoint:
    1. Validates the verification token exists and hasn't expired
    2. Marks the email as verified
    3. Clears the verification token
    4. Returns the updated profile

    Args:
        token: The email verification token sent to the user's email
        db: Database session

    Returns:
        UserProfile: The verified user profile

    Raises:
        HTTPException 400: If token is invalid or expired
    """
    try:
        identity = await get_identity_by_verification_token(db, token)

        if identity is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification token",
            )

        if (
            identity.email_verification_token_expires is None
            or identity.email_verification_token_expires < pendulum.now("UTC")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired",
            )

        await update_identity(
            db,
            identity,
            {
                "email_verified": True,
                "email_verification_token": None,
                "email_verification_token_expires": None,
            },
        )

        await db.commit()
        await db.refresh(identity)

        return identity.profile
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("3/hour")
async def resend_verification_email(
    request: Request,
    email: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """
    Resend email verification to a user.

    This endpoint:
    1. Finds the identity by email
    2. Checks if email is already verified
    3. Generates new verification token
    4. Sends new verification email

    Args:
        email: The email address to resend verification to
        db: Database session

    Returns:
        dict: Success message

    Raises:
        HTTPException 400: If email not found or already verified
    """
    try:
        identity = await get_identity_by_provider(db, AuthProvider.EMAIL, email)

        if identity is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not found",
            )

        if identity.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified",
            )

        verification_token = email_service.generate_verification_token()
        token_expiry = email_service.generate_token_expiry()

        await update_identity(
            db,
            identity,
            {
                "email_verification_token": verification_token,
                "email_verification_token_expires": token_expiry,
            },
        )

        await db.commit()

        try:
            await email_service.send_verification_email(
                to_email=email,
                display_name=identity.profile.display_name,
                verification_token=verification_token,
            )
        except Exception as e:
            logger.error(f"Failed to send verification email to {email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email",
            )

        return {"message": "Verification email sent successfully"}
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/migrate-profile", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
async def migrate_legacy_user_to_profile(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    try:
        if current_user.discord_id:
            provider = AuthProvider.DISCORD
            provider_user_id = current_user.discord_id
        else:
            provider = AuthProvider.EMAIL
            provider_user_id = current_user.email

        existing_identity = await get_identity_by_provider(db, provider, provider_user_id)

        if existing_identity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile already migrated",
            )

        profile_create = UserProfileCreate(
            display_name=current_user.username,
            avatar_url=None,
            bio=None,
            role=current_user.role,
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, _ = await create_profile_with_identity(
            db,
            profile_create,
            provider,
            provider_user_id,
            credentials={
                "migrated_from_user_id": current_user.id,
                "migration_timestamp": str(current_user.created_at),
            },
        )

        await db.commit()
        await db.refresh(profile)

        access_token_expires = pendulum.duration(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_profile_access_token(
            profile.id,
            profile.display_name,
            provider.value,
            expires_delta=access_token_expires,
        )

        refresh_token = create_profile_refresh_token(
            profile.id, profile.display_name, provider.value
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except Exception:
        await db.rollback()
        raise


@router.get("/me", response_model=UserProfileResponse)
async def get_current_profile_endpoint(
    current_profile: Annotated[UserProfile, Depends(get_current_active_profile)],
) -> UserProfile:
    return current_profile


@router.patch("/me", response_model=UserProfileResponse)
async def update_current_profile_endpoint(
    profile_update: UserProfileSelfUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_profile: Annotated[UserProfile, Depends(get_current_active_profile)],
) -> UserProfile:
    try:
        if profile_update.display_name:
            existing_profile = await get_profile_by_display_name(db, profile_update.display_name)
            if existing_profile and existing_profile.id != current_profile.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Display name already in use",
                )

        updated_profile = await update_profile(db, current_profile, profile_update)
        await db.commit()

        return updated_profile
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/revoke", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/hour")
async def revoke_profile_token(
    request: Request,
    current_profile: Annotated[UserProfile, Depends(get_current_active_profile)],
) -> None:
    """
    Revoke the current profile access token.

    This endpoint:
    1. Extracts the token from the Authorization header
    2. Adds the token's JTI to the Redis revocation blacklist
    3. The token will be rejected on future verification attempts

    Use this endpoint to invalidate the current access token after logout
    or when a token may be compromised.

    Note: Existing tokens without jti claim (created before this feature)
    cannot be revoked individually and will expire naturally.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = auth_header.replace("Bearer ", "")
    success = await revoke_token(token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token revocation failed. Token may lack jti claim or already be expired.",
        )
