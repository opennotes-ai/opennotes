from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


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
async def sim_run(playground_community, orchestrator):
    from src.database import get_session_maker
    from src.simulation.models import SimulationRun

    async with get_session_maker()() as session:
        run = SimulationRun(
            orchestrator_id=orchestrator["id"],
            community_server_id=playground_community["id"],
            status="running",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return {
            "id": run.id,
            "status": run.status,
            "community_server_id": playground_community["id"],
        }


@pytest.fixture
async def sim_agent(playground_community):
    from src.database import get_session_maker
    from src.simulation.models import SimAgent

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        agent = SimAgent(
            name=f"TestAgent_{unique}",
            personality="A helpful fact-checker.",
            model_name="openai:gpt-4o-mini",
            community_server_id=playground_community["id"],
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return {"id": agent.id}


@pytest.fixture
async def user_profile_factory():
    from src.database import get_session_maker
    from src.users.profile_models import UserProfile

    async def _create(display_name: str | None = None) -> dict:
        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            profile = UserProfile(
                display_name=display_name or f"SimUser_{unique}",
                is_human=False,
                is_active=True,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return {"id": profile.id, "display_name": profile.display_name}

    return _create


@pytest.fixture
async def agent_instance_factory(sim_run, sim_agent, user_profile_factory):
    from src.database import get_session_maker
    from src.simulation.models import SimAgentInstance

    async def _create(state: str = "active", turn_count: int = 0) -> dict:
        profile = await user_profile_factory()
        async with get_session_maker()() as session:
            instance = SimAgentInstance(
                simulation_run_id=sim_run["id"],
                agent_profile_id=sim_agent["id"],
                user_profile_id=profile["id"],
                state=state,
                turn_count=turn_count,
            )
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return {
                "id": instance.id,
                "user_profile_id": profile["id"],
                "state": state,
                "turn_count": turn_count,
            }

    return _create


@pytest.fixture
async def note_factory(playground_community):
    from src.database import get_session_maker
    from src.notes.models import Note

    async def _create(author_id: UUID) -> dict:
        async with get_session_maker()() as session:
            note = Note(
                author_id=author_id,
                community_server_id=playground_community["id"],
                summary="Test note from simulation agent",
                classification="NOT_MISLEADING",
                status="NEEDS_MORE_RATINGS",
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return {"id": note.id, "author_id": author_id, "summary": note.summary}

    return _create


@pytest.fixture
async def rating_factory():
    from src.database import get_session_maker
    from src.notes.models import Rating

    async def _create(rater_id: UUID, note_id: UUID) -> dict:
        async with get_session_maker()() as session:
            rating = Rating(
                rater_id=rater_id,
                note_id=note_id,
                helpfulness_level="HELPFUL",
            )
            session.add(rating)
            await session.commit()
            await session.refresh(rating)
            return {"id": rating.id, "rater_id": rater_id, "note_id": note_id}

    return _create


class TestGetSimulationProgress:
    @pytest.mark.asyncio
    async def test_progress_returns_correct_stats(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=5)
        inst2 = await agent_instance_factory(state="active", turn_count=3)
        inst3 = await agent_instance_factory(state="completed", turn_count=10)

        note1 = await note_factory(author_id=inst1["user_profile_id"])
        await note_factory(author_id=inst2["user_profile_id"])

        await rating_factory(rater_id=inst2["user_profile_id"], note_id=note1["id"])
        await rating_factory(rater_id=inst3["user_profile_id"], note_id=note1["id"])

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/progress")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["type"] == "simulation-progress"
        assert data["data"]["id"] == str(sim_run["id"])

        attrs = data["data"]["attributes"]
        assert attrs["turns_completed"] == 18
        assert attrs["notes_written"] == 2
        assert attrs["ratings_given"] == 2
        assert attrs["active_agents"] == 2

    @pytest.mark.asyncio
    async def test_progress_not_found(self, admin_auth_client):
        fake_id = str(uuid4())
        response = await admin_auth_client.get(f"/api/v2/simulations/{fake_id}/progress")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_progress_empty_simulation(
        self,
        admin_auth_client,
        sim_run,
    ):
        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/progress")

        assert response.status_code == 200
        attrs = response.json()["data"]["attributes"]
        assert attrs["turns_completed"] == 0
        assert attrs["notes_written"] == 0
        assert attrs["ratings_given"] == 0
        assert attrs["active_agents"] == 0

    @pytest.mark.asyncio
    async def test_progress_uses_cache(
        self,
        admin_auth_client,
        sim_run,
    ):
        mock_redis = AsyncMock()
        cached_data = json.dumps(
            {
                "data": {
                    "type": "simulation-progress",
                    "id": str(sim_run["id"]),
                    "attributes": {
                        "turns_completed": 99,
                        "turns_errored": 0,
                        "notes_written": 42,
                        "ratings_given": 10,
                        "active_agents": 5,
                    },
                },
                "jsonapi": {"version": "1.1"},
            }
        )
        mock_redis.get = AsyncMock(return_value=cached_data)

        with patch("src.simulation.simulations_jsonapi_router.redis_client", mock_redis):
            response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/progress")

        assert response.status_code == 200
        attrs = response.json()["data"]["attributes"]
        assert attrs["turns_completed"] == 99
        assert attrs["notes_written"] == 42


class TestGetSimulationResults:
    @pytest.mark.asyncio
    async def test_results_returns_notes(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        await note_factory(author_id=inst["user_profile_id"])
        await note_factory(author_id=inst["user_profile_id"])

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/results")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert len(data["data"]) == 2
        assert data["meta"]["count"] == 2

    @pytest.mark.asyncio
    async def test_results_pagination(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=5)
        for _ in range(5):
            await note_factory(author_id=inst["user_profile_id"])

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/results?page[number]=1&page[size]=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["meta"]["count"] == 5
        assert data["links"] is not None

    @pytest.mark.asyncio
    async def test_results_filter_by_agent_instance(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=2)
        inst2 = await agent_instance_factory(state="active", turn_count=3)

        await note_factory(author_id=inst1["user_profile_id"])
        await note_factory(author_id=inst1["user_profile_id"])
        await note_factory(author_id=inst2["user_profile_id"])

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/results?agent_instance_id={inst1['id']}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["meta"]["count"] == 2

    @pytest.mark.asyncio
    async def test_results_not_found(self, admin_auth_client):
        fake_id = str(uuid4())
        response = await admin_auth_client.get(f"/api/v2/simulations/{fake_id}/results")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_results_empty(
        self,
        admin_auth_client,
        sim_run,
    ):
        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/results")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 0
        assert data["meta"]["count"] == 0


class TestProgressUnauthenticated:
    @pytest.mark.asyncio
    async def test_progress_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}/progress")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_results_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}/results")
            assert response.status_code == 401
