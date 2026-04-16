"""Phase 1.4 — scope tiers + privileged scope gate.

Tests covering:
- Self-service endpoint gates platform:adapter on platform_admin role
- Admin endpoint no longer silently strips restricted scopes
- Adapter-key convention: platform:adapter only for agent/system targets
- Agent principal_type does not bypass scope tier rules
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.auth.password import get_password_hash
from src.database import get_session_maker
from src.main import app
from src.users.models import APIKey, User
from tests.fixtures.principal_factory import (
    make_agent_user,
    make_human_user,
    make_platform_admin,
)


def _make_bearer_headers(user: User) -> dict[str, str]:
    """Create JWT auth headers with all required claims."""
    token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
        }
    )
    return {"Authorization": f"Bearer {token}"}


async def _make_platform_admin_api_key() -> tuple[User, str]:
    """Create a platform_admin user with api-keys:create scope and return (user, raw_key)."""
    raw_key, key_prefix = APIKey.generate_key()
    key_hash = get_password_hash(raw_key)

    async with get_session_maker()() as session:
        admin = await make_platform_admin(
            session,
            username=f"pa-admin-{raw_key[:6]}",
            email=f"pa-admin-{raw_key[:6]}@opennotes.local",
        )
        key = APIKey(
            user_id=admin.id,
            name="pa-admin-key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_active=True,
            scopes=["api-keys:create"],
        )
        session.add(key)
        await session.commit()

    return admin, raw_key


async def _make_regular_api_key() -> tuple[User, str]:
    """Create a regular human user with api-keys:create scope and return (user, raw_key)."""
    raw_key, key_prefix = APIKey.generate_key()
    key_hash = get_password_hash(raw_key)

    async with get_session_maker()() as session:
        user = await make_human_user(
            session,
            username=f"regular-{raw_key[:6]}",
            email=f"regular-{raw_key[:6]}@test.example",
        )
        key = APIKey(
            user_id=user.id,
            name="regular-key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_active=True,
            scopes=["api-keys:create"],
        )
        session.add(key)
        await session.commit()

    return user, raw_key


@pytest.mark.asyncio
class TestSelfServiceScopeTiers:
    async def test_self_service_platform_adapter_denied_for_regular_user(self):
        """Regular user cannot self-assign platform:adapter scope."""
        async with get_session_maker()() as session:
            regular_user = await make_human_user(
                session,
                username="no-adapter-user",
                email="no-adapter@test.example",
            )
            await session.commit()

        headers = _make_bearer_headers(regular_user)

        with patch("src.auth.auth.is_token_revoked_check", new=AsyncMock(return_value=False)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/users/me/api-keys",
                    json={
                        "name": "try-adapter",
                        "scopes": ["platform:adapter"],
                    },
                    headers=headers,
                )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "platform_admin" in response.json()["detail"]

    async def test_self_service_platform_adapter_allowed_for_platform_admin(self):
        """platform_admin user can self-assign platform:adapter scope."""
        async with get_session_maker()() as session:
            admin = await make_platform_admin(
                session,
                username="pa-self-adapter",
                email="pa-self-adapter@opennotes.local",
            )
            await session.commit()

        headers = _make_bearer_headers(admin)

        with patch("src.auth.auth.is_token_revoked_check", new=AsyncMock(return_value=False)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/users/me/api-keys",
                    json={
                        "name": "adapter-key",
                        "scopes": ["platform:adapter"],
                    },
                    headers=headers,
                )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "platform:adapter" in data["scopes"]

    async def test_self_service_empty_scopes_rejected(self):
        """API key creation with empty scopes list is rejected."""
        async with get_session_maker()() as session:
            regular_user = await make_human_user(
                session,
                username="empty-scopes-user",
                email="empty-scopes@test.example",
            )
            await session.commit()

        headers = _make_bearer_headers(regular_user)

        with patch("src.auth.auth.is_token_revoked_check", new=AsyncMock(return_value=False)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/users/me/api-keys",
                    json={
                        "name": "empty-key",
                        "scopes": [],
                    },
                    headers=headers,
                )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
class TestAdminEndpointScopeGate:
    async def test_admin_endpoint_no_silent_strip(self):
        """Non-platform_admin user with api-keys:create scope trying to grant platform:adapter
        receives 403, NOT a silent strip."""
        _, regular_key = await _make_regular_api_key()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "target-nostrip@test.example",
                    "user_display_name": "Target No Strip",
                    "key_name": "no-strip-key",
                    "scopes": ["platform:adapter"],
                },
                headers={"X-API-Key": regular_key},
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_adapter_key_convention_human_target_rejected(self):
        """Admin granting platform:adapter to a human user gets 403 with convention-reserved."""
        _, admin_key = await _make_platform_admin_api_key()

        async with get_session_maker()() as session:
            human_target = await make_human_user(
                session,
                username="human-adapter-target",
                email="human-adapter-target@test.example",
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": human_target.email,
                    "user_display_name": "Human Target",
                    "key_name": "adapter-for-human",
                    "scopes": ["platform:adapter"],
                },
                headers={"X-API-Key": admin_key},
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "convention-reserved" in response.json()["detail"].lower()

    async def test_adapter_key_convention_agent_target_allowed(self):
        """Admin granting platform:adapter to an agent user succeeds (201)."""
        _, admin_key = await _make_platform_admin_api_key()

        agent_email = "agent-adapter-target@agent.example"

        async with get_session_maker()() as session:
            from uuid import uuid4

            agent_target = User(
                id=uuid4(),
                username="agent-adapter-target",
                email=agent_email,
                hashed_password="fakehash",
                is_active=True,
                principal_type="agent",
                platform_roles=[],
            )
            session.add(agent_target)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": agent_email,
                    "user_display_name": "Agent Target",
                    "key_name": "adapter-for-agent",
                    "scopes": ["platform:adapter"],
                },
                headers={"X-API-Key": admin_key},
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "platform:adapter" in data["scopes"]

    async def test_adapter_key_fresh_email_human_target_rejected(self):
        """Brand-new email (no existing User row) must NOT slip through the convention check.
        Before fix: _find_or_create_user creates the user as principal_type='human' AFTER the
        check, allowing the human-bound adapter key. After fix: check runs after resolution."""
        _, admin_key = await _make_platform_admin_api_key()

        fresh_email = "fresh-no-existing@nowhere.example"

        async with get_session_maker()() as session:
            from sqlalchemy import select

            existing = await session.execute(select(User).where(User.email == fresh_email))
            assert existing.scalar_one_or_none() is None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": fresh_email,
                    "user_display_name": "Fresh Human",
                    "key_name": "fresh-adapter-key",
                    "scopes": ["platform:adapter"],
                },
                headers={"X-API-Key": admin_key},
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "convention-reserved" in response.json()["detail"].lower()

        async with get_session_maker()() as session:
            from sqlalchemy import select

            post = await session.execute(select(User).where(User.email == fresh_email))
            assert post.scalar_one_or_none() is None, "Transaction should have rolled back"

    async def test_agent_without_platform_admin_denied_admin_scopes(self):
        """Agent principal_type does NOT bypass scope tier rules.
        An agent without platform_admin cannot grant platform:adapter."""
        raw_key, key_prefix = APIKey.generate_key()
        key_hash = get_password_hash(raw_key)

        async with get_session_maker()() as session:
            agent_user = await make_agent_user(session, name=f"agent-no-admin-{raw_key[:6]}")
            key = APIKey(
                user_id=agent_user.id,
                name="agent-no-admin-key",
                key_prefix=key_prefix,
                key_hash=key_hash,
                is_active=True,
                scopes=["api-keys:create"],
            )
            session.add(key)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v2/admin/api-keys",
                json={
                    "user_email": "agent-target-denied@test.example",
                    "user_display_name": "Agent Target Denied",
                    "key_name": "denied-adapter-key",
                    "scopes": ["platform:adapter"],
                },
                headers={"X-API-Key": raw_key},
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
