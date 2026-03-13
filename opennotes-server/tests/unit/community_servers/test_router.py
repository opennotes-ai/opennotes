from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.community_servers.router import CommunityServerCreateRequest, create_community_server
from src.llm_config.models import COMMUNITY_SERVER_PLATFORM_ID_UNIQUE_CONSTRAINT
from src.users.models import User


def _make_asyncpg_integrity_error(constraint_name: str) -> IntegrityError:
    orig = MagicMock()
    orig.constraint_name = constraint_name
    return IntegrityError("duplicate key", params=None, orig=orig)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_community_server_returns_409_for_asyncpg_unique_conflict():
    request_body = CommunityServerCreateRequest(
        platform="discord",
        platform_community_server_id="guild-asyncpg",
        name="Guild",
    )
    current_user = User(
        id=1,
        username="create-cs-service",
        email="create-cs-service@opennotes.local",
        hashed_password="unused",
        role="admin",
    )
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock(
        side_effect=_make_asyncpg_integrity_error(COMMUNITY_SERVER_PLATFORM_ID_UNIQUE_CONSTRAINT)
    )
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    with (
        patch(
            "src.community_servers.router.get_community_server_by_platform_id",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_community_server(request_body, current_user, db)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in exc_info.value.detail
    db.rollback.assert_awaited_once()
