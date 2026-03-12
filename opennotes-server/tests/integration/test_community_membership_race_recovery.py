import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.auth import community_dependencies
from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.users.profile_models import CommunityMember, UserProfile

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_membership_auto_create_recovers_duplicate(setup_database):
    async with get_session_maker()() as session:
        community = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id=f"guild-{uuid4().hex[:8]}",
            name="Race Recovery Test Server",
            is_active=True,
            is_public=True,
        )
        profile = UserProfile(
            display_name="Concurrent Member",
            is_human=True,
            is_active=True,
        )
        session.add_all([community, profile])
        await session.commit()

        community_id = community.id
        profile_id = profile.id

    ready_count = 0
    ready_lock = asyncio.Lock()
    release_create = asyncio.Event()
    real_create_member = community_dependencies.create_community_member

    async def coordinated_create(db, member_create):
        nonlocal ready_count
        async with ready_lock:
            ready_count += 1
            if ready_count == 2:
                release_create.set()

        await asyncio.wait_for(release_create.wait(), timeout=5)
        return await real_create_member(db, member_create)

    async def ensure_membership():
        async with get_session_maker()() as session:
            community = await session.get(CommunityServer, community_id)
            profile = await session.get(UserProfile, profile_id)

            membership = await community_dependencies._ensure_membership_with_permissions(
                community=community,
                profile=profile,
                has_discord_manage_server=True,
                db=session,
            )
            await session.commit()
            return membership.id

    patched_create = AsyncMock(side_effect=coordinated_create)
    with patch(
        "src.auth.community_dependencies.create_community_member",
        new=patched_create,
    ):
        membership_ids = await asyncio.gather(ensure_membership(), ensure_membership())

    assert membership_ids[0] == membership_ids[1]

    async with get_session_maker()() as session:
        count_result = await session.execute(
            select(func.count(CommunityMember.id)).where(
                CommunityMember.community_id == community_id,
                CommunityMember.profile_id == profile_id,
            )
        )
        membership_count = count_result.scalar_one()

    assert membership_count == 1
