import logging
import re
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.schemas import AdminAPIKeyCreate, AdminAPIKeyListItem, AdminAPIKeyResponse
from src.auth.dependencies import get_current_user_or_api_key, require_scope_or_admin
from src.auth.models import ALLOWED_API_KEY_SCOPES, RESTRICTED_SCOPES
from src.auth.password import get_password_hash
from src.common.responses import AUTHENTICATED_RESPONSES
from src.database import get_db
from src.users.audit_helper import create_audit_log, extract_request_context
from src.users.models import APIKey, User

router = APIRouter(prefix="/api/v2/admin/api-keys", tags=["admin-api-keys"])
logger = logging.getLogger(__name__)


def _slugify_email_local(email: str) -> str:
    local_part = email.split("@")[0]
    return re.sub(r"[^a-z0-9]", "-", local_part.lower()).strip("-")


async def _find_or_create_user(
    db: AsyncSession,
    email: str,
    display_name: str,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    base_username = _slugify_email_local(email)
    username = base_username

    suffix = 2
    while True:
        check = await db.execute(select(User).where(User.username == username))
        if check.scalar_one_or_none() is None:
            break
        username = f"{base_username}-{suffix}"
        suffix += 1

    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(secrets.token_urlsafe(32)),
        full_name=display_name,
        is_active=True,
        is_service_account=False,
        role="user",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post(
    "",
    response_model=AdminAPIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    responses=AUTHENTICATED_RESPONSES,
)
async def create_admin_api_key(
    body: AdminAPIKeyCreate,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminAPIKeyResponse:
    require_scope_or_admin(current_user, request, "api-keys:create")

    invalid = [s for s in body.scopes if s not in ALLOWED_API_KEY_SCOPES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope(s): {', '.join(invalid)}",
        )

    effective_scopes = [s for s in body.scopes if s not in RESTRICTED_SCOPES]
    if not effective_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid scopes remain after removing restricted scopes",
        )

    target_user = await _find_or_create_user(db, body.user_email, body.user_display_name)

    raw_key, key_prefix = APIKey.generate_key()
    key_hash = get_password_hash(raw_key)

    api_key = APIKey(
        user_id=target_user.id,
        name=body.key_name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True,
        scopes=effective_scopes,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    ip_address, user_agent = extract_request_context(request)
    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="ADMIN_CREATE_API_KEY",
        resource="api_key",
        resource_id=str(api_key.id),
        details={
            "target_user_email": body.user_email,
            "key_name": body.key_name,
            "scopes": effective_scopes,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await db.commit()

    return AdminAPIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        scopes=api_key.scopes,
        user_email=target_user.email,
        user_display_name=target_user.full_name or "",
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.get(
    "",
    response_model=list[AdminAPIKeyListItem],
    responses=AUTHENTICATED_RESPONSES,
)
async def list_admin_api_keys(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminAPIKeyListItem]:
    require_scope_or_admin(current_user, request, "api-keys:create")

    result = await db.execute(
        select(APIKey, User)
        .join(User, APIKey.user_id == User.id)
        .where(
            APIKey.is_active == True,
            User.is_service_account == False,
        )
        .order_by(APIKey.created_at.desc())
    )

    items = []
    for api_key, user in result.all():
        items.append(
            AdminAPIKeyListItem(
                id=api_key.id,
                name=api_key.name,
                key_prefix=api_key.key_prefix,
                scopes=api_key.scopes,
                user_email=user.email,
                user_display_name=user.full_name or "",
                created_at=api_key.created_at,
                expires_at=api_key.expires_at,
                is_active=api_key.is_active,
            )
        )

    return items


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=AUTHENTICATED_RESPONSES,
)
async def revoke_admin_api_key(
    key_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    require_scope_or_admin(current_user, request, "api-keys:create")

    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False

    ip_address, user_agent = extract_request_context(request)
    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="ADMIN_REVOKE_API_KEY",
        resource="api_key",
        resource_id=str(api_key.id),
        details={"key_name": api_key.name},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await db.commit()
