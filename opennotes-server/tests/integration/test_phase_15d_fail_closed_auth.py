"""Phase 1.5d (TASK-1451.13) - fail-closed auth when APIKey.scopes empty/None.

`scopes=None` and `scopes=[]` both mean "no access" by design (see APIKey model).
verify_api_key() must NOT return such keys to callers, because routes that
authenticate via get_current_user_or_api_key without then calling
require_scope_or_admin would otherwise accept zero-access keys.

This is the auth-layer complement to the has_scope() fix from Phase 1.5
(TASK-1433.09).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from src.auth.password import get_password_hash
from src.database import get_session_maker
from src.main import app
from src.users.crud import verify_api_key
from src.users.models import APIKey
from tests.fixtures.principal_factory import make_human_user


@pytest.mark.asyncio
class TestVerifyApiKeyFailsClosedOnEmptyScopes:
    async def test_verify_api_key_rejects_empty_scopes_list_prefix_fastpath(self):
        """Prefix-fast-path: verify_api_key returns None for an active key with scopes=[]."""
        raw_key, key_prefix = APIKey.generate_key()
        key_hash = get_password_hash(raw_key)

        async with get_session_maker()() as session:
            user = await make_human_user(session)
            key = APIKey(
                user_id=user.id,
                name="empty-scopes-key",
                key_prefix=key_prefix,
                key_hash=key_hash,
                is_active=True,
                scopes=[],
            )
            session.add(key)
            await session.commit()

        async with get_session_maker()() as session:
            result = await verify_api_key(session, raw_key)

        assert result is None, "verify_api_key must reject zero-scope keys (fail-closed)"

    async def test_verify_api_key_accepts_scoped_key_prefix_fastpath(self):
        """Sanity: a key with at least one scope still verifies successfully."""
        raw_key, key_prefix = APIKey.generate_key()
        key_hash = get_password_hash(raw_key)

        async with get_session_maker()() as session:
            user = await make_human_user(session)
            key = APIKey(
                user_id=user.id,
                name="scoped-key",
                key_prefix=key_prefix,
                key_hash=key_hash,
                is_active=True,
                scopes=["notes:read"],
            )
            session.add(key)
            await session.commit()

        async with get_session_maker()() as session:
            result = await verify_api_key(session, raw_key)

        assert result is not None, "scoped key should verify successfully"
        api_key_obj, returned_user = result
        assert api_key_obj.scopes == ["notes:read"]
        assert returned_user.id == user.id

    async def test_verify_api_key_rejects_none_scopes_prefix_fastpath(self):
        """Prefix-fast-path: verify_api_key returns None when scopes=None.

        Even though the schema is nullable=False since Phase 15c, we defend in depth:
        legacy rows or direct SQL writes could still produce NULL. We force NULL via
        a raw SQL UPDATE that bypasses the SQLAlchemy attribute-level constraint.
        """
        raw_key, key_prefix = APIKey.generate_key()
        key_hash = get_password_hash(raw_key)

        async with get_session_maker()() as session:
            user = await make_human_user(session)
            key = APIKey(
                user_id=user.id,
                name="none-scopes-key",
                key_prefix=key_prefix,
                key_hash=key_hash,
                is_active=True,
                scopes=[],
            )
            session.add(key)
            await session.commit()
            key_id = key.id

        async with get_session_maker()() as session:
            await session.execute(update(APIKey).where(APIKey.id == key_id).values(scopes=None))
            await session.commit()

        async with get_session_maker()() as session:
            result = await verify_api_key(session, raw_key)

        assert result is None, "verify_api_key must reject scopes=None (fail-closed)"


@pytest.mark.asyncio
class TestUnscopedKeyBlockedAtEndpoint:
    async def test_unscoped_key_returns_401_at_get_current_user_or_api_key(self):
        """HTTP boundary: a real route that depends on get_current_user_or_api_key
        rejects an empty-scope key with 401 (no successful authentication).

        Uses GET /api/v1/community-config/{id} which requires
        get_current_user_or_api_key. With no valid auth (because verify_api_key
        now returns None), the dependency falls through and raises 401.
        """
        raw_key, key_prefix = APIKey.generate_key()
        key_hash = get_password_hash(raw_key)

        async with get_session_maker()() as session:
            user = await make_human_user(
                session,
                username="empty-scopes-http-user",
                email="empty-scopes-http@test.example",
            )
            key = APIKey(
                user_id=user.id,
                name="empty-scopes-http-key",
                key_prefix=key_prefix,
                key_hash=key_hash,
                is_active=True,
                scopes=[],
            )
            session.add(key)
            await session.commit()

        with patch("src.auth.auth.is_token_revoked_check", new=AsyncMock(return_value=False)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/community-config/some-platform-id",
                    headers={"X-API-Key": raw_key},
                )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Empty-scope keys must be rejected at the auth boundary, "
            f"got {response.status_code}: {response.text}"
        )


@pytest.mark.asyncio
class TestVerifyApiKeyLegacyLoopFailsClosed:
    async def test_legacy_loop_rejects_empty_scopes(self):
        """Legacy O(n) loop path (raw key without 'opk_' prefix) must also fail-closed.

        The fallback loop iterates all active keys and verify_password matches by
        bcrypt comparison; we must reject the match if scopes are empty.
        """
        raw_key = "legacy-no-prefix-key-secret-value"
        key_hash = get_password_hash(raw_key)

        async with get_session_maker()() as session:
            user = await make_human_user(session)
            key = APIKey(
                user_id=user.id,
                name="legacy-empty-scopes-key",
                key_prefix="legacy",
                key_hash=key_hash,
                is_active=True,
                scopes=[],
            )
            session.add(key)
            await session.commit()

        async with get_session_maker()() as session:
            result = await verify_api_key(session, raw_key)

        assert result is None, "legacy O(n) loop must also reject zero-scope keys"
