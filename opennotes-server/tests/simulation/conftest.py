from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.main import app


@pytest.fixture(autouse=True, scope="session")
def _register_simulation_models():
    from src.community_config.models import CommunityConfig  # noqa: F401
    from src.llm_config.models import CommunityServer, CommunityServerLLMConfig  # noqa: F401
    from src.notes.models import Note  # noqa: F401
    from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost  # noqa: F401
    from src.simulation.models import (  # noqa: F401
        SimAgent,
        SimAgentInstance,
        SimAgentMemory,
        SimulationOrchestrator,
        SimulationRun,
    )
    from src.users.models import User  # noqa: F401
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile  # noqa: F401


@pytest.fixture
async def admin_test_user():
    return {
        "username": f"admin_user_{uuid4().hex[:8]}",
        "email": f"admin_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Admin Test User",
    }


@pytest.fixture
async def admin_registered_user(admin_test_user):
    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=admin_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == admin_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"admin_discord_{uuid4().hex[:8]}"
            user.is_superuser = True

            profile = UserProfile(
                display_name=user.full_name or user.username,
                is_human=True,
                is_active=True,
            )
            session.add(profile)
            await session.flush()

            identity = UserIdentity(
                profile_id=profile.id,
                provider="discord",
                provider_user_id=user.discord_id,
            )
            session.add(identity)

            await session.commit()
            await session.refresh(user)
            await session.refresh(profile)

            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "discord_id": user.discord_id,
                "profile_id": profile.id,
            }


@pytest.fixture
async def admin_auth_headers(admin_registered_user):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(admin_registered_user["id"]),
        "username": admin_registered_user["username"],
        "role": admin_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def admin_auth_client(admin_auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(admin_auth_headers)
        yield client
