import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import APIKeyCreate, UserCreate, UserUpdate
from src.auth.password import get_password_hash, verify_password
from src.users.audit_helper import create_audit_log
from src.users.models import APIKey, AuditLog, RefreshToken, User

DUMMY_PASSWORD_HASH = get_password_hash("dummy_password_for_timing_protection")


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_email_for_update(db: AsyncSession, email: str) -> User | None:
    """
    Get user by email with SELECT FOR UPDATE lock.

    This prevents race conditions during user registration and email updates
    by locking the row if it exists. The lock is held until the transaction commits.

    Use this when you need to check email uniqueness and then perform an INSERT/UPDATE
    in the same transaction to prevent TOCTOU (Time-Of-Check-Time-Of-Use) races.
    """
    result = await db.execute(select(User).where(User.email == email).with_for_update())
    return result.scalar_one_or_none()


async def get_user_by_username_for_update(db: AsyncSession, username: str) -> User | None:
    """
    Get user by username with SELECT FOR UPDATE lock.

    This prevents race conditions during user registration by locking the row
    if it exists. The lock is held until the transaction commits.

    Use this when you need to check username uniqueness and then perform an INSERT
    in the same transaction to prevent TOCTOU (Time-Of-Check-Time-Of-Use) races.
    """
    result = await db.execute(select(User).where(User.username == username).with_for_update())
    return result.scalar_one_or_none()


async def get_user_by_discord_id(db: AsyncSession, discord_id: str) -> User | None:
    result = await db.execute(select(User).where(User.discord_id == discord_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    user_create: UserCreate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    hashed_password = get_password_hash(user_create.password)

    user = User(
        username=user_create.username,
        email=user_create.email,
        hashed_password=hashed_password,
        full_name=user_create.full_name,
        role="user",
        is_active=True,
        is_superuser=False,
    )

    db.add(user)
    await db.flush()
    await db.refresh(user)

    await create_audit_log(
        db=db,
        user_id=user.id,
        action="CREATE_USER",
        resource="user",
        resource_id=str(user.id),
        details={"username": user.username, "email": user.email},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return user


async def update_user(
    db: AsyncSession,
    user: User,
    user_update: UserUpdate,
    requesting_user_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    """
    Update a user's information.

    Args:
        db: Database session
        user: User instance to update
        user_update: Update data
        requesting_user_id: ID of user making the request (for authorization check)
        ip_address: IP address of the request (for audit logging)
        user_agent: User agent string (for audit logging)

    Returns:
        Updated User instance

    Raises:
        HTTPException(403): If requesting_user_id doesn't match user.id (unauthorized)
    """
    # SECURITY: Verify requesting user owns this account (defense in depth)
    if requesting_user_id is not None and requesting_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this user's information",
        )

    changed_fields = []

    if user_update.email is not None:
        old_email = user.email
        user.email = user_update.email
        changed_fields.append("email")
        await create_audit_log(
            db=db,
            user_id=user.id,
            action="UPDATE_EMAIL",
            resource="user",
            resource_id=str(user.id),
            details={"old_email": old_email, "new_email": user.email},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    if user_update.full_name is not None:
        user.full_name = user_update.full_name
        changed_fields.append("full_name")

    if user_update.password is not None:
        user.hashed_password = get_password_hash(user_update.password)
        changed_fields.append("password")

        # Invalidate all existing tokens by setting tokens_valid_after to 1 second in the future.
        # This ensures all tokens with iat < tokens_valid_after are rejected, including
        # tokens created in the same second as this password change.
        # Security note: Users must wait ~1s before re-login due to JWT's second-level iat precision.
        now = datetime.now(UTC)
        current_second = int(now.timestamp())
        user.tokens_valid_after = datetime.fromtimestamp(current_second + 1, tz=UTC)

        await create_audit_log(
            db=db,
            user_id=user.id,
            action="UPDATE_PASSWORD",
            resource="user",
            resource_id=str(user.id),
            details={"changed_fields": changed_fields, "tokens_invalidated": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    user.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(user)

    return user


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User | None:
    user = await get_user_by_username(db, username)

    if user is None:
        _ = verify_password(password, DUMMY_PASSWORD_HASH)
        await asyncio.sleep(secrets.randbelow(41) / 1000)
        await create_audit_log(
            db=db,
            user_id=None,
            action="LOGIN_FAILED",
            resource="authentication",
            details={"username": username, "reason": "user_not_found"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        return None

    is_valid, needs_rehash = verify_password(password, user.hashed_password)
    if not is_valid:
        await asyncio.sleep(secrets.randbelow(41) / 1000)
        await create_audit_log(
            db=db,
            user_id=user.id,
            action="LOGIN_FAILED",
            resource="authentication",
            resource_id=str(user.id),
            details={"username": username, "reason": "invalid_password"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        return None

    if needs_rehash:
        user.hashed_password = get_password_hash(password)
        await db.flush()

    if not user.is_active:
        await asyncio.sleep(secrets.randbelow(41) / 1000)
        await create_audit_log(
            db=db,
            user_id=user.id,
            action="LOGIN_FAILED",
            resource="authentication",
            resource_id=str(user.id),
            details={"username": username, "reason": "account_inactive"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        return None

    await create_audit_log(
        db=db,
        user_id=user.id,
        action="LOGIN_SUCCESS",
        resource="authentication",
        resource_id=str(user.id),
        details={"username": username},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return user


async def create_refresh_token(
    db: AsyncSession, user_id: UUID, token: str, expires_days: int
) -> RefreshToken:
    expires_at = datetime.now(UTC) + timedelta(days=expires_days)
    token_hash = get_password_hash(token)

    refresh_token = RefreshToken(
        user_id=user_id,
        token=None,
        token_hash=token_hash,
        expires_at=expires_at,
        is_revoked=False,
    )

    db.add(refresh_token)
    await db.flush()
    await db.refresh(refresh_token)

    return refresh_token


async def get_refresh_token(db: AsyncSession, token: str) -> RefreshToken | None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    refresh_tokens = result.scalars().all()

    for refresh_token in refresh_tokens:
        if refresh_token.token_hash:
            is_valid, _ = verify_password(token, refresh_token.token_hash)
            if is_valid:
                return refresh_token
        elif refresh_token.token == token:
            return refresh_token

    return None


async def revoke_refresh_token(db: AsyncSession, token: str, user_id: UUID | None = None) -> bool:
    """
    Revoke a refresh token.

    Args:
        db: Database session
        token: The refresh token to revoke
        user_id: If provided, only revoke the token if it belongs to this user

    Returns:
        True if token was revoked, False if token not found or doesn't belong to user
    """
    refresh_token = await get_refresh_token(db, token)

    if refresh_token is None:
        return False

    if user_id is not None and refresh_token.user_id != user_id:
        return False

    refresh_token.is_revoked = True
    await db.flush()

    return True


async def revoke_all_user_refresh_tokens(db: AsyncSession, user_id: UUID) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        )
    )
    tokens = result.scalars().all()

    for token in tokens:
        token.is_revoked = True

    await db.flush()


async def create_api_key(
    db: AsyncSession,
    user_id: UUID,
    api_key_create: APIKeyCreate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[APIKey, str]:
    """
    Create a new API key with prefix for O(1) verification.

    Returns:
        tuple[APIKey, str]: The created APIKey record and the raw key string
    """
    raw_key, key_prefix = APIKey.generate_key()
    key_hash = get_password_hash(raw_key)

    expires_at = None
    if api_key_create.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=api_key_create.expires_in_days)

    api_key = APIKey(
        user_id=user_id,
        name=api_key_create.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        expires_at=expires_at,
        is_active=True,
    )

    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    await create_audit_log(
        db=db,
        user_id=user_id,
        action="CREATE_API_KEY",
        resource="api_key",
        resource_id=str(api_key.id),
        details={"name": api_key.name, "expires_at": str(expires_at) if expires_at else None},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return api_key, raw_key


async def get_api_keys_by_user(db: AsyncSession, user_id: UUID) -> list[APIKey]:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user_id, APIKey.is_active == True)
        .order_by(APIKey.created_at.desc())
    )
    return list(result.scalars().all())


async def get_api_key_by_id(db: AsyncSession, api_key_id: UUID) -> APIKey | None:
    result = await db.execute(select(APIKey).where(APIKey.id == api_key_id))
    return result.scalar_one_or_none()


async def verify_api_key(db: AsyncSession, raw_key: str) -> tuple[APIKey, User] | None:  # noqa: PLR0911
    """
    Verify an API key and return the associated APIKey and User.

    Uses key prefix for O(1) database lookup instead of O(n) iteration.
    Falls back to O(n) verification for legacy keys without prefix.

    Args:
        db: Database session
        raw_key: The raw API key (e.g., "opk_abc123_secretpart")

    Returns:
        Tuple of (APIKey, User) if valid, None otherwise
    """
    if raw_key.startswith("opk_"):
        parts = raw_key.split("_", 2)
        if len(parts) == 3:
            key_prefix = parts[1]

            result = await db.execute(
                select(APIKey).where(
                    APIKey.key_prefix == key_prefix,
                    APIKey.is_active == True,
                )
            )
            api_key = result.scalar_one_or_none()

            if api_key is None:
                _ = verify_password("dummy", DUMMY_PASSWORD_HASH)
                return None

            is_valid, _ = verify_password(raw_key, api_key.key_hash)
            if not is_valid:
                return None

            if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
                return None

            api_key.last_used_at = datetime.now(UTC)
            await db.flush()

            user = await get_user_by_id(db, api_key.user_id)
            if user is None:
                return None

            if not user.is_active:
                return None

            return api_key, user

    result = await db.execute(
        select(APIKey).where(
            APIKey.is_active == True,
        )
    )
    api_keys = result.scalars().all()

    for api_key in api_keys:
        is_valid, _ = verify_password(raw_key, api_key.key_hash)
        if is_valid:
            if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
                continue

            api_key.last_used_at = datetime.now(UTC)
            await db.flush()

            user = await get_user_by_id(db, api_key.user_id)
            if user and user.is_active:
                return api_key, user

    return None


async def revoke_api_key(
    db: AsyncSession,
    api_key_id: UUID,
    user_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> bool:
    api_key = await get_api_key_by_id(db, api_key_id)

    if api_key is None or api_key.user_id != user_id:
        return False

    api_key.is_active = False
    await db.flush()

    await create_audit_log(
        db=db,
        user_id=user_id,
        action="REVOKE_API_KEY",
        resource="api_key",
        resource_id=str(api_key_id),
        details={"name": api_key.name},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return True


async def get_user_audit_logs(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
    action_filter: list[str] | None = None,
) -> list[AuditLog]:
    query = select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at.desc())

    if action_filter:
        query = query.where(AuditLog.action.in_(action_filter))

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())
