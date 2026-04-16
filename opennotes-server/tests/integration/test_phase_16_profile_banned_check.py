"""Regression tests for TASK-1451.16: profile auth path must check banned_at.

Phase 1.6 fix: ``get_current_active_profile`` previously only checked
``profile.is_active``. The user-token path uses ``is_account_active(user)``
which also rejects ``banned_at != None``. This left a gap where banned users
could continue to authenticate via profile-token routes.

The dependency now rejects authentication when any of the following holds:

- ``profile.is_active`` is False
- ``profile.is_banned`` is True
- ``profile.banned_at`` is not None
"""

from __future__ import annotations

from uuid import uuid4

import pendulum
import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.profile_auth import create_profile_access_token
from src.database import get_session_maker
from src.main import app
from src.users.profile_models import UserProfile
from src.users.profile_schemas import AuthProvider

PROTECTED_ROUTE = "/api/v1/profile/me"


async def _make_profile(
    *,
    is_active: bool = True,
    is_banned: bool = False,
    banned_at: object = None,
) -> UserProfile:
    """Insert a UserProfile row directly with the given activation/ban fields."""
    async with get_session_maker()() as session:
        profile = UserProfile(
            id=uuid4(),
            display_name=f"phase16-{uuid4().hex[:8]}",
            is_active=is_active,
            is_banned=is_banned,
            banned_at=banned_at,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


def _auth_headers(profile: UserProfile) -> dict[str, str]:
    token = create_profile_access_token(
        profile_id=profile.id,
        display_name=profile.display_name,
        provider=AuthProvider.EMAIL.value,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestPhase16ProfileBannedCheck:
    async def test_active_profile_authenticates(self) -> None:
        profile = await _make_profile(is_active=True, is_banned=False, banned_at=None)
        headers = _auth_headers(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(PROTECTED_ROUTE, headers=headers)

        assert response.status_code == 200, response.text

    async def test_inactive_profile_401(self) -> None:
        profile = await _make_profile(is_active=False, is_banned=False, banned_at=None)
        headers = _auth_headers(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(PROTECTED_ROUTE, headers=headers)

        assert response.status_code == 401

    async def test_banned_profile_via_is_banned_flag_401(self) -> None:
        profile = await _make_profile(is_active=True, is_banned=True, banned_at=None)
        headers = _auth_headers(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(PROTECTED_ROUTE, headers=headers)

        assert response.status_code == 401

    async def test_banned_profile_via_banned_at_timestamp_401(self) -> None:
        banned_at = pendulum.now("UTC").subtract(hours=1)
        profile = await _make_profile(is_active=True, is_banned=False, banned_at=banned_at)
        headers = _auth_headers(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(PROTECTED_ROUTE, headers=headers)

        assert response.status_code == 401

    async def test_banned_profile_both_flags_401(self) -> None:
        banned_at = pendulum.now("UTC").subtract(minutes=5)
        profile = await _make_profile(is_active=False, is_banned=True, banned_at=banned_at)
        headers = _auth_headers(profile)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(PROTECTED_ROUTE, headers=headers)

        assert response.status_code == 401
