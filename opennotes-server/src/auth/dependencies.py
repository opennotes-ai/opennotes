from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth import verify_token
from src.database import get_db
from src.users.crud import get_user_by_id, verify_api_key
from src.users.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
http_bearer = HTTPBearer(auto_error=False)


def get_x_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> str | None:
    return x_api_key


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode JWT once to get user_id and iat
    token_data = await verify_token(token)
    if not token_data:
        raise credentials_exception

    # Fetch user from database
    user = await get_user_by_id(db, token_data.user_id)
    if not user:
        raise credentials_exception

    # Validate tokens_valid_after using already-decoded token data (no re-decode)
    if user.tokens_valid_after and token_data.iat is not None:
        # Compare token iat (integer seconds) with tokens_valid_after (datetime).
        # Convert tokens_valid_after to integer seconds for comparison.
        # Reject only tokens issued strictly before tokens_valid_after.
        # This allows tokens issued in the same second as revoke to be accepted
        # if they were created after the revoke call.
        valid_after_int = int(user.tokens_valid_after.timestamp())
        if token_data.iat < valid_after_int:
            raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


async def get_current_user_or_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    x_api_key: Annotated[str | None, Depends(get_x_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    # Check X-API-Key header first (preferred for Cloud Run IAM auth)
    if x_api_key:
        api_key_result = await verify_api_key(db, x_api_key)
        if api_key_result:
            _, user = api_key_result
            return user

    # Fall back to Authorization header (Bearer token)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Try JWT token first
    token_data = await verify_token(token)
    if token_data:
        user = await get_user_by_id(db, token_data.user_id)
        if user and user.is_active:
            return user

    # Try API key in Authorization header (legacy support)
    api_key_result = await verify_api_key(db, token)
    if api_key_result:
        _, user = api_key_result
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(required_role: str) -> Any:
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        role_hierarchy = {
            "user": 0,
            "moderator": 1,
            "admin": 2,
        }

        user_level = role_hierarchy.get(current_user.role, -1)
        required_level = role_hierarchy.get(required_role, 999)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}",
            )

        return current_user

    return role_checker


def require_superuser(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


def require_admin(user: User) -> None:
    if not (user.is_superuser or user.is_service_account):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )


def require_superuser_or_service_account(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    require_admin(current_user)
    return current_user
