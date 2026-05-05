from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.users.crud import verify_api_key
from src.users.models import APIKey

VIBECHECK_SUBMIT_SCOPE = "vibecheck:submit"
API_KEY_PREFIX = "opk_"

http_bearer = HTTPBearer(auto_error=False)


class UrlScanAuthError(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error_code = error_code
        self.message = message


def get_url_scan_x_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> str | None:
    return x_api_key


async def get_url_scan_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    x_api_key: Annotated[str | None, Depends(get_url_scan_x_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> APIKey:
    raw_api_key = x_api_key or (credentials.credentials if credentials is not None else None)
    if not raw_api_key:
        raise UrlScanAuthError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="unauthorized",
            message="Missing API key credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not raw_api_key.startswith(API_KEY_PREFIX):
        raise UrlScanAuthError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="unauthorized",
            message="Invalid API key credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key_result = await verify_api_key(db, raw_api_key)
    if api_key_result is None:
        raise UrlScanAuthError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="unauthorized",
            message="Invalid API key credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key, _user = api_key_result
    if not api_key.has_scope(VIBECHECK_SUBMIT_SCOPE):
        raise UrlScanAuthError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="forbidden",
            message="API key lacks required scope",
        )

    request.state.api_key = api_key
    request.state.url_scan_api_key = api_key
    return api_key
