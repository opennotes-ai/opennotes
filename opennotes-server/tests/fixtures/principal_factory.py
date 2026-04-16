"""Shared test factories for authorization redesign.

Usage in tests:
    from tests.fixtures.principal_factory import make_human_user, make_api_key
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import APIKey, User


async def make_human_user(
    db: AsyncSession,
    *,
    username: str | None = None,
    email: str | None = None,
    platform_roles: list[str] | None = None,
) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        username=username or f"human-{uid.hex[:8]}",
        email=email or f"human-{uid.hex[:8]}@test.example",
        hashed_password="fakehash",
        is_active=True,
        principal_type="human",
        platform_roles=platform_roles if platform_roles is not None else [],
        banned_at=None,
    )
    db.add(user)
    await db.flush()
    return user


async def make_agent_user(
    db: AsyncSession,
    *,
    name: str | None = None,
) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        username=name or f"agent-{uid.hex[:8]}",
        email=f"agent-{uid.hex[:8]}@opennotes.local",
        hashed_password="fakehash",
        is_active=True,
        principal_type="agent",
        platform_roles=[],
    )
    db.add(user)
    await db.flush()
    return user


async def make_system_user(
    db: AsyncSession,
    *,
    name: str = "platform-service",
) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        username=name,
        email=f"{name}@opennotes.local",
        hashed_password="fakehash",
        is_active=True,
        principal_type="system",
        platform_roles=["platform_admin"],
    )
    db.add(user)
    await db.flush()
    return user


async def make_platform_admin(
    db: AsyncSession,
    **kwargs,
) -> User:
    return await make_human_user(db, platform_roles=["platform_admin"], **kwargs)


async def make_api_key(
    db: AsyncSession,
    user: User,
    *,
    scopes: list[str] | None = None,
    name: str = "test-key",
) -> APIKey:
    uid = uuid4()
    key = APIKey(
        id=uid,
        user_id=user.id,
        name=name,
        key_hash=f"fakehash-{uid.hex}",
        key_prefix="test_",
        scopes=scopes if scopes is not None else [],
        is_active=True,
    )
    db.add(key)
    await db.flush()
    return key


def make_jwt_headers(user: User) -> dict[str, str]:
    from src.auth.auth import create_access_token

    token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def make_api_key_headers(raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}
