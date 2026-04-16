"""Phase 1.3 registration hardening tests.

Verifies that public registration:
- Blocks usernames ending in -service (reserved for agent/system principals)
- Blocks emails ending in @opennotes.local (reserved for platform-internal)
- Hardcodes principal_type='human', is_active=True, banned_at=None, platform_roles=[]
- Ignores or rejects principal_type / platform_roles in the request body
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User


@pytest.mark.asyncio
class TestRegistrationHardening:
    async def test_register_service_username_blocked(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "evil-service",
                "email": "normal@example.com",
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 400
        assert "reserved" in resp.json()["detail"].lower()

    async def test_register_service_username_suffix_only_blocked(
        self, async_client: AsyncClient
    ) -> None:
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "my-bot-service",
                "email": "bot@example.com",
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 400
        assert "reserved" in resp.json()["detail"].lower()

    async def test_register_service_prefix_not_blocked(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "serviceuser",
                "email": "serviceuser@example.com",
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 201

    async def test_register_opennotes_local_email_blocked(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "normaluser",
                "email": "evil@opennotes.local",
                "password": "StrongPass123!",
            },
        )
        # Either 400 (handler's reserved-pattern check) or 422 (Pydantic EmailStr
        # rejects .local TLD). Both outcomes prevent registration as intended.
        assert resp.status_code in (400, 422)

    async def test_register_normal_user_succeeds_with_hardcoded_fields(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "gooduser",
                "email": "good@example.com",
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 201

        user = (
            await db_session.execute(select(User).where(User.username == "gooduser"))
        ).scalar_one()
        assert user.principal_type == "human"
        assert user.is_active is True
        assert user.banned_at is None
        assert user.platform_roles == []

    async def test_register_ignores_principal_type_in_body(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "fuzzuser",
                "email": "fuzz@example.com",
                "password": "StrongPass123!",
                "principal_type": "system",
                "platform_roles": ["platform_admin"],
            },
        )
        assert resp.status_code in (201, 422)

        if resp.status_code == 201:
            user = (
                await db_session.execute(select(User).where(User.username == "fuzzuser"))
            ).scalar_one()
            assert user.principal_type == "human"
            assert user.platform_roles == []
