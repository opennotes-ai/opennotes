from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth import verify_token
from src.auth.permissions import is_account_active, is_platform_admin, is_service_account
from src.database import get_db
from src.users.crud import get_user_by_id, verify_api_key
from src.users.models import APIKey, User

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
    if user.tokens_valid_after is not None:
        if token_data.iat is None:
            raise credentials_exception
        valid_after_int = int(user.tokens_valid_after.timestamp())
        if token_data.iat < valid_after_int:
            raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not is_account_active(current_user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


async def get_current_user_or_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    x_api_key: Annotated[str | None, Depends(get_x_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    # Check X-API-Key header first (preferred for Cloud Run IAM auth)
    if x_api_key:
        api_key_result = await verify_api_key(db, x_api_key)
        if api_key_result:
            api_key_obj, user = api_key_result
            request.state.api_key = api_key_obj
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
        if user and is_account_active(user):
            if user.tokens_valid_after is not None:
                if token_data.iat is None:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid authentication credentials",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                valid_after_int = int(user.tokens_valid_after.timestamp())
                if token_data.iat < valid_after_int:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid authentication credentials",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            return user

    # Try API key in Authorization header (legacy support)
    api_key_result = await verify_api_key(db, token)
    if api_key_result:
        api_key_obj, user = api_key_result
        request.state.api_key = api_key_obj
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_superuser(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


def require_admin(user: User) -> None:
    if not (is_platform_admin(user) or is_service_account(user)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )


def require_scope_or_admin(user: User, request: Request, scope: str) -> bool:
    """Check if the user has admin privileges or a scoped API key with the required scope.

    Returns True if access is via a scoped API key (caller should apply scope
    restrictions like filtering to public resources), False if access is via
    admin privileges (no restrictions needed).

    Raises HTTPException 403 if neither condition is met.
    """
    is_admin = is_platform_admin(user) or is_service_account(user)

    api_key: APIKey | None = getattr(request.state, "api_key", None)
    if api_key:
        if not api_key.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key lacks required scope",
            )
        return not is_admin or api_key.is_scoped()

    if is_admin:
        return False

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required",
    )


def require_superuser_or_service_account(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    require_admin(current_user)
    return current_user


async def require_platform_adapter(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    request: Request,
) -> User:
    api_key: APIKey | None = getattr(request.state, "api_key", None)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform adapter API key required",
        )
    if not api_key.has_scope("platform:adapter"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key lacks required scope",
        )
    return current_user
