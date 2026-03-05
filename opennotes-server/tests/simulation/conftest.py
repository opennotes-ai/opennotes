from uuid import uuid4

import pendulum
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
        SimAgentRunLog,
        SimChannelMessage,
        SimulationOrchestrator,
        SimulationRun,
        SimulationRunConfig,
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


@pytest.fixture
async def playground_community():
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        cs = CommunityServer(
            platform="playground",
            platform_community_server_id=f"playground-{unique}",
            name=f"Test Playground {unique}",
            is_active=True,
            is_public=True,
        )
        session.add(cs)
        await session.commit()
        await session.refresh(cs)
        return {"id": cs.id, "name": cs.name}


@pytest.fixture
async def orchestrator():
    from src.database import get_session_maker
    from src.simulation.models import SimulationOrchestrator

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        orch = SimulationOrchestrator(
            name=f"TestOrch_{unique}",
            turn_cadence_seconds=60,
            max_agents=10,
            removal_rate=0.1,
            max_turns_per_agent=100,
            agent_profile_ids=[],
        )
        session.add(orch)
        await session.commit()
        await session.refresh(orch)
        return {"id": orch.id, "name": orch.name}


@pytest.fixture
async def simulation_run_factory(playground_community, orchestrator):
    from src.database import get_session_maker
    from src.simulation.models import SimulationRun

    async def _create(
        status_val: str = "pending",
        restart_count: int = 0,
        cumulative_turns: int = 0,
        generation: int = 1,
    ) -> dict:
        now = pendulum.now("UTC")
        async with get_session_maker()() as session:
            run = SimulationRun(
                orchestrator_id=orchestrator["id"],
                community_server_id=playground_community["id"],
                status=status_val,
                restart_count=restart_count,
                cumulative_turns=cumulative_turns,
                generation=generation,
                started_at=now.subtract(hours=1),
                completed_at=now if status_val == "completed" else None,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return {
                "id": run.id,
                "status": run.status,
                "restart_count": run.restart_count,
                "cumulative_turns": run.cumulative_turns,
                "generation": run.generation,
            }

    return _create


@pytest.fixture
async def agent_instance_factory():
    from src.database import get_session_maker
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    async def _create(
        simulation_run_id,
        *,
        state: str = "active",
        turn_count: int = 0,
        cumulative_turn_count: int = 0,
        removal_reason: str | None = None,
    ) -> dict:
        async with get_session_maker()() as session:
            unique = uuid4().hex[:8]
            agent = SimAgent(
                name=f"agent-{unique}",
                personality="test personality",
                model_name="gpt-4o",
            )
            session.add(agent)
            await session.flush()

            profile = UserProfile(
                display_name=f"sim-{unique}",
                is_human=False,
            )
            session.add(profile)
            await session.flush()

            inst = SimAgentInstance(
                simulation_run_id=simulation_run_id,
                agent_profile_id=agent.id,
                user_profile_id=profile.id,
                state=state,
                turn_count=turn_count,
                cumulative_turn_count=cumulative_turn_count,
                removal_reason=removal_reason,
            )
            session.add(inst)
            await session.commit()
            await session.refresh(inst)
            return {
                "id": inst.id,
                "state": inst.state,
                "turn_count": inst.turn_count,
                "cumulative_turn_count": inst.cumulative_turn_count,
            }

    return _create
