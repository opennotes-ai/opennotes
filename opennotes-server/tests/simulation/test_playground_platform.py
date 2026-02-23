from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_community_server_accepts_playground_platform(db):
    from src.llm_config.models import CommunityServer

    server = CommunityServer(
        id=uuid4(),
        platform="playground",
        platform_community_server_id=f"playground-{uuid4().hex[:8]}",
        name="Test Playground",
        is_active=True,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    result = await db.execute(select(CommunityServer).where(CommunityServer.id == server.id))
    row = result.scalar_one()
    assert row.platform == "playground"
    assert row.name == "Test Playground"


@pytest.mark.asyncio
async def test_community_server_rejects_invalid_platform(db):
    from src.llm_config.models import CommunityServer

    server = CommunityServer(
        id=uuid4(),
        platform="invalid_platform",
        platform_community_server_id=f"invalid-{uuid4().hex[:8]}",
        name="Invalid Server",
    )
    db.add(server)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


@pytest.mark.asyncio
async def test_playground_community_server_fixture(playground_community_server, db):
    from src.llm_config.models import CommunityServer

    result = await db.execute(
        select(CommunityServer).where(CommunityServer.id == playground_community_server)
    )
    row = result.scalar_one()
    assert row.platform == "playground"
