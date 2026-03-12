import asyncio
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from src.auth import community_dependencies
from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.users.models import User
from src.users.profile_crud import create_profile_with_identity
from src.users.profile_models import (
    COMMUNITY_MEMBER_COMMUNITY_PROFILE_UNIQUE_CONSTRAINT,
    CommunityMember,
    UserProfile,
)
from src.users.profile_schemas import AuthProvider, UserProfileCreate

pytestmark = pytest.mark.integration


def _make_integrity_error(constraint_name: str) -> IntegrityError:
    diag = MagicMock()
    diag.constraint_name = constraint_name
    orig = MagicMock()
    orig.diag = diag
    return IntegrityError("duplicate key", params=None, orig=orig)


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

    real_create_member = community_dependencies.create_community_member
    expected_membership_id = None

    async def create_member_after_race(_db, member_create):
        nonlocal expected_membership_id
        async with get_session_maker()() as competing_session:
            competing_membership = await real_create_member(competing_session, member_create)
            await competing_session.commit()
            expected_membership_id = competing_membership.id
        raise _make_integrity_error(COMMUNITY_MEMBER_COMMUNITY_PROFILE_UNIQUE_CONSTRAINT)

    async with get_session_maker()() as session:
        community = CommunityServer(
            id=community_id,
            platform="discord",
            platform_community_server_id="unused-for-race-test",
            name="Race Recovery Test Server",
            is_active=True,
            is_public=True,
        )
        profile = UserProfile(
            id=profile_id,
            display_name="Concurrent Member",
            is_human=True,
            is_active=True,
        )

        with patch(
            "src.auth.community_dependencies.create_community_member",
            new=AsyncMock(side_effect=create_member_after_race),
        ):
            membership = await community_dependencies._ensure_membership_with_permissions(
                community=community,
                profile=profile,
                has_discord_manage_server=True,
                db=session,
            )
            await session.commit()

    assert membership.id == expected_membership_id

    async with get_session_maker()() as session:
        count_result = await session.execute(
            select(func.count(CommunityMember.id)).where(
                CommunityMember.community_id == community_id,
                CommunityMember.profile_id == profile_id,
            )
        )
        membership_count = count_result.scalar_one()

    assert membership_count == 1


@pytest.mark.asyncio
async def test_concurrent_verify_membership_recovers_server_and_membership_duplicates(
    setup_database,
):
    async with get_session_maker()() as session:
        profile_create = UserProfileCreate(
            display_name="Concurrent Service Account",
            avatar_url=None,
            bio="Service account seeded for verify_community_membership race test",
            is_human=False,
        )
        profile, _identity = await create_profile_with_identity(
            db=session,
            profile_create=profile_create,
            provider=AuthProvider.EMAIL,
            provider_user_id="verify-service@opennotes.local",
            credentials=None,
        )
        await session.commit()
        profile_id = profile.id

    guild_id = f"guild-{uuid4().hex[:8]}"
    user = User(
        id=1,
        username="verify-service",
        email="verify-service@opennotes.local",
        hashed_password="unused",
        role="admin",
    )
    mock_request = MagicMock()
    mock_request.headers = {}

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

    async with AsyncExitStack() as stack:
        session_one = await stack.enter_async_context(get_session_maker()())
        session_two = await stack.enter_async_context(get_session_maker()())

        await session_one.execute(text("SELECT 1"))
        await session_two.execute(text("SELECT 1"))

        async def verify_membership(session):
            membership = await community_dependencies.verify_community_membership(
                guild_id,
                user,
                session,
                mock_request,
            )
            await session.commit()
            return membership.id

        with patch(
            "src.auth.community_dependencies.get_profile_id_from_user",
            new=AsyncMock(return_value=profile_id),
        ):
            results = await asyncio.gather(
                verify_membership(session_one),
                verify_membership(session_two),
                return_exceptions=True,
            )

    assert not [result for result in results if isinstance(result, Exception)], results
    membership_ids = results
    assert membership_ids[0] == membership_ids[1]

    async with get_session_maker()() as session:
        server_count_result = await session.execute(
            select(func.count(CommunityServer.id)).where(
                CommunityServer.platform == "discord",
                CommunityServer.platform_community_server_id == guild_id,
            )
        )
        membership_count_result = await session.execute(
            select(func.count(CommunityMember.id)).where(
                CommunityMember.profile_id == profile_id,
            )
        )

    assert server_count_result.scalar_one() == 1
    assert membership_count_result.scalar_one() == 1
