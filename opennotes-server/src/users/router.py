"""
User authentication and management router.

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
        result = await create_user(db, user_create)
        # Commit the transaction
        await db.commit()
        return result
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

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth import create_access_token, create_refresh_token, verify_refresh_token
from src.auth.dependencies import get_current_active_user
from src.auth.models import (
    APIKeyCreate,
    APIKeyResponse,
    AuditLogResponse,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from src.auth.revocation import revoke_all_user_tokens, revoke_token
from src.config import settings
from src.database import get_db
from src.middleware.rate_limiting import limiter
from src.users.audit_helper import create_audit_log, extract_request_context
from src.users.crud import (
    authenticate_user,
    create_api_key,
    create_user,
    get_api_keys_by_user,
    get_refresh_token,
    get_user_audit_logs,
    get_user_by_email_for_update,
    get_user_by_username_for_update,
    revoke_all_user_refresh_tokens,
    revoke_api_key,
    revoke_refresh_token,
    update_user,
)
from src.users.crud import (
    create_refresh_token as db_create_refresh_token,
)
from src.users.models import User

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
async def register(
    request: Request,
    user_create: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        existing_user = await get_user_by_username_for_update(db, user_create.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )

        existing_email = await get_user_by_email_for_update(db, user_create.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        ip_address, user_agent = extract_request_context(request)
        user = await create_user(db, user_create, ip_address, user_agent)
        await db.commit()
        return user
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "username" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            ) from e
        if "email" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User registration failed due to duplicate constraint",
        ) from e
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/login", response_model=Token)
@limiter.limit("5/15minutes")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    try:
        ip_address, user_agent = extract_request_context(request)
        user = await authenticate_user(
            db, form_data.username, form_data.password, ip_address, user_agent
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role},
            expires_delta=access_token_expires,
        )

        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )

        await db_create_refresh_token(
            db, user.id, refresh_token, settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        await db.commit()

        return Token(
            access_token=access_token,
            token_type="bearer",
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/refresh", response_model=Token)
@limiter.limit("20/hour")
async def refresh_access_token(
    http_request: Request,
    request: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """
    Refresh access token using a refresh token.

    The refresh token must be provided in the request body (not as a query parameter)
    to prevent token leakage in server logs, browser history, and referrer headers.
    """
    ip_address, user_agent = extract_request_context(http_request)

    token_data = await verify_refresh_token(request.refresh_token)

    if token_data is None:
        await create_audit_log(
            db=db,
            user_id=None,
            action="TOKEN_REFRESH_FAILED",
            resource="authentication",
            details={"reason": "invalid_refresh_token"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    db_refresh_token = await get_refresh_token(db, request.refresh_token)

    if db_refresh_token is None:
        await create_audit_log(
            db=db,
            user_id=token_data.user_id,
            action="TOKEN_REFRESH_FAILED",
            resource="authentication",
            resource_id=str(token_data.user_id),
            details={"reason": "refresh_token_not_found"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or expired",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data={
            "sub": str(token_data.user_id),
            "username": token_data.username,
            "role": token_data.role,
        },
        expires_delta=access_token_expires,
    )

    await create_audit_log(
        db=db,
        user_id=token_data.user_id,
        action="TOKEN_REFRESH_SUCCESS",
        resource="authentication",
        resource_id=str(token_data.user_id),
        details={"username": token_data.username},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()

    return Token(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    refresh_token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """
    Logout by revoking the provided refresh token and current access token.

    Only revokes the token if it belongs to the current user, preventing
    cross-user token revocation attacks.
    """
    try:
        ip_address, user_agent = extract_request_context(request)

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header.replace("Bearer ", "")
            await revoke_token(access_token)

        success = await revoke_refresh_token(db, refresh_token, user_id=current_user.id)
        if not success:
            await create_audit_log(
                db=db,
                user_id=current_user.id,
                action="LOGOUT_FAILED",
                resource="authentication",
                resource_id=str(current_user.id),
                details={"reason": "token_not_found"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Refresh token not found or does not belong to current user",
            )
        await create_audit_log(
            db=db,
            user_id=current_user.id,
            action="LOGOUT_SUCCESS",
            resource="authentication",
            resource_id=str(current_user.id),
            details={"username": current_user.username, "access_token_revoked": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    try:
        ip_address, user_agent = extract_request_context(request)
        await revoke_all_user_refresh_tokens(db, current_user.id)

        # Invalidate all existing access tokens by setting tokens_valid_after to 1 second in the future.
        # This ensures all tokens with iat < tokens_valid_after are rejected, including
        # tokens created in the same second as this logout-all call.
        # Security note: Users must wait ~1s before re-login due to JWT's second-level iat precision.
        now = datetime.now(UTC)
        current_second = int(now.timestamp())
        current_user.tokens_valid_after = datetime.fromtimestamp(current_second + 1, tz=UTC)
        await db.flush()

        await create_audit_log(
            db=db,
            user_id=current_user.id,
            action="LOGOUT_ALL_SUCCESS",
            resource="authentication",
            resource_id=str(current_user.id),
            details={"username": current_user.username, "tokens_invalidated": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/revoke-token", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_current_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    try:
        ip_address, user_agent = extract_request_context(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header",
            )

        token = auth_header.replace("Bearer ", "")
        success = await revoke_token(token)

        if not success:
            await create_audit_log(
                db=db,
                user_id=current_user.id,
                action="REVOKE_TOKEN_FAILED",
                resource="authentication",
                resource_id=str(current_user.id),
                details={"reason": "token_revocation_failed"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to revoke token",
            )

        await create_audit_log(
            db=db,
            user_id=current_user.id,
            action="REVOKE_TOKEN_SUCCESS",
            resource="authentication",
            resource_id=str(current_user.id),
            details={"username": current_user.username},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise


@router.post("/auth/revoke-all-tokens", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_tokens(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    try:
        ip_address, user_agent = extract_request_context(request)

        await revoke_all_user_refresh_tokens(db, current_user.id)

        # Invalidate all existing access tokens by setting tokens_valid_after to 1 second in the future.
        # This ensures all tokens with iat < tokens_valid_after are rejected, including
        # tokens created in the same second as this revoke-all-tokens call.
        # Security note: Users must wait ~1s before re-login due to JWT's second-level iat precision.
        now = datetime.now(UTC)
        current_second = int(now.timestamp())
        current_user.tokens_valid_after = datetime.fromtimestamp(current_second + 1, tz=UTC)
        await db.flush()

        await revoke_all_user_tokens(current_user.id)

        await create_audit_log(
            db=db,
            user_id=current_user.id,
            action="REVOKE_ALL_TOKENS_SUCCESS",
            resource="authentication",
            resource_id=str(current_user.id),
            details={"username": current_user.username, "all_tokens_revoked": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user


@router.get("/users/me/login-history", response_model=list[AuditLogResponse])
async def get_login_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLogResponse]:
    authentication_actions = [
        "LOGIN_SUCCESS",
        "LOGIN_FAILED",
        "TOKEN_REFRESH_SUCCESS",
        "TOKEN_REFRESH_FAILED",
        "LOGOUT_SUCCESS",
        "LOGOUT_FAILED",
        "LOGOUT_ALL_SUCCESS",
        "CREATE_USER",
    ]

    audit_logs = await get_user_audit_logs(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        action_filter=authentication_actions,
    )

    return [AuditLogResponse.model_validate(log) for log in audit_logs]


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user_profile(
    request: Request,
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    try:
        if user_update.email:
            existing_email = await get_user_by_email_for_update(db, user_update.email)
            if existing_email and existing_email.id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use",
                )

        ip_address, user_agent = extract_request_context(request)
        user = await update_user(
            db, current_user, user_update, current_user.id, ip_address, user_agent
        )
        await db.commit()
        return user
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "email" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User update failed due to constraint violation",
        ) from e
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/users/me/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED
)
async def create_user_api_key(
    request: Request,
    api_key_create: APIKeyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> APIKeyResponse:
    try:
        ip_address, user_agent = extract_request_context(request)
        api_key, raw_key = await create_api_key(
            db, current_user.id, api_key_create, ip_address, user_agent
        )
        await db.commit()

        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=raw_key,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
        )
    except Exception:
        await db.rollback()
        raise


@router.get("/users/me/api-keys", response_model=list[APIKeyResponse])
async def list_user_api_keys(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[APIKeyResponse]:
    api_keys = await get_api_keys_by_user(db, current_user.id)

    return [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            key="***",
            created_at=key.created_at,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
        )
        for key in api_keys
    ]


@router.delete("/users/me/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_api_key(
    request: Request,
    api_key_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    try:
        ip_address, user_agent = extract_request_context(request)
        success = await revoke_api_key(db, api_key_id, current_user.id, ip_address, user_agent)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
