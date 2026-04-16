"""Regression tests for TASK-1433.09: unscoped API keys returning True for has_scope().

Phase 1.5 fix: has_scope() must return False when scopes is None or empty.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.database import get_session_maker
from src.main import app
from src.users.models import APIKey
from tests.fixtures.principal_factory import make_human_user


@pytest.mark.unit
class TestHasScopeUnitBehavior:
    def test_has_scope_returns_false_for_none(self):
        key = APIKey(scopes=None)
        assert key.has_scope("anything") is False

    def test_has_scope_returns_false_for_empty(self):
        key = APIKey(scopes=[])
        assert key.has_scope("anything") is False

    def test_has_scope_returns_true_for_matching(self):
        key = APIKey(scopes=["notes:read"])
        assert key.has_scope("notes:read") is True

    def test_has_scope_returns_false_for_non_matching(self):
        key = APIKey(scopes=["notes:read"])
        assert key.has_scope("notes:write") is False


@pytest.mark.unit
class TestIsScopedUnitBehavior:
    def test_is_scoped_returns_false_for_none(self):
        key = APIKey(scopes=None)
        assert key.is_scoped() is False

    def test_is_scoped_returns_false_for_empty(self):
        key = APIKey(scopes=[])
        assert key.is_scoped() is False

    def test_is_scoped_returns_true_for_non_empty(self):
        key = APIKey(scopes=["notes:read"])
        assert key.is_scoped() is True


@pytest.mark.asyncio
class TestEmptyScopesRejectedAtCreation:
    async def test_empty_scopes_rejected_at_creation(self):
        async with get_session_maker()() as session:
            user = await make_human_user(session)
            await session.commit()
            await session.refresh(user)

        token = create_access_token(data={"sub": str(user.id), "username": user.username})
        headers = {"Authorization": f"Bearer {token}"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/me/api-keys",
                json={"name": "empty-scopes-key", "scopes": []},
                headers=headers,
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
