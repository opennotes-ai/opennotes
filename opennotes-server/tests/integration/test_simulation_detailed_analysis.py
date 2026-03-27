from __future__ import annotations

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
            platform_community_server_id=f"playground-detailed-{unique}",
            name=f"Detailed Analysis Playground {unique}",
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
            name=f"DetailedOrch_{unique}",
            turn_cadence_seconds=60,
            max_active_agents=10,
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
            status="completed",
            metrics={
                "scores_computed": 5,
                "tiers_reached": ["minimal"],
                "scorers_used": ["BayesianAverageScorer"],
                "tier_distribution": {"minimal": 5},
                "scorer_breakdown": {"BayesianAverageScorer": 5},
            },
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
async def sim_agent():
    from src.database import get_session_maker
    from src.simulation.models import SimAgent

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        agent = SimAgent(
            name=f"DetailedAgent_{unique}",
            personality="A balanced fact-checker.",
            model_name="openai:gpt-4o-mini",
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return {"id": agent.id, "name": agent.name}


@pytest.fixture
async def user_profile_factory():
    from src.database import get_session_maker
    from src.users.profile_models import UserProfile

    async def _create(display_name: str | None = None) -> dict:
        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            profile = UserProfile(
                display_name=display_name or f"DetailedUser_{unique}",
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

    async def _create(
        author_id: UUID,
        classification: str = "NOT_MISLEADING",
        status: str = "NEEDS_MORE_RATINGS",
        helpfulness_score: int = 0,
        summary: str = "Test detailed note",
    ) -> dict:
        async with get_session_maker()() as session:
            note = Note(
                author_id=author_id,
                community_server_id=playground_community["id"],
                summary=summary,
                classification=classification,
                status=status,
                helpfulness_score=helpfulness_score,
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return {
                "id": note.id,
                "author_id": author_id,
                "classification": classification,
                "status": status,
            }

    return _create


@pytest.fixture
async def admin_auth_client():
    from src.auth.auth import create_access_token
    from src.database import get_session_maker
    from src.users.models import User

    unique = uuid4().hex[:8]
    user_data = {
        "username": f"admin_detailed_{unique}",
        "email": f"admin_detailed_{unique}@example.com",
        "password": "TestPassword123!",
        "full_name": "Admin Detailed User",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=user_data)

    from sqlalchemy import select as sa_select

    async with get_session_maker()() as session:
        stmt = sa_select(User).where(User.username == user_data["username"])
        result = await session.execute(stmt)
        user = result.scalar_one()
        user.is_superuser = True
        await session.commit()
        await session.refresh(user)

    token = create_access_token({"sub": str(user.id), "username": user.username, "role": user.role})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


class TestDetailedAnalysisSortByHasScore:
    @pytest.mark.asyncio
    async def test_sort_by_has_score_puts_scored_notes_first(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        uid = inst["user_profile_id"]

        await note_factory(
            author_id=uid,
            status="NEEDS_MORE_RATINGS",
            summary="Unscored note",
        )
        await note_factory(
            author_id=uid,
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=80,
            summary="Helpful note",
        )
        await note_factory(
            author_id=uid,
            status="CURRENTLY_RATED_NOT_HELPFUL",
            helpfulness_score=-20,
            summary="Not helpful note",
        )

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/analysis/detailed",
            params={"sort_by": "has_score"},
        )

        assert response.status_code == 200
        data = response.json()
        notes = data["data"]
        assert len(notes) == 3

        statuses = [n["attributes"]["status"] for n in notes]
        scored_statuses = {"CURRENTLY_RATED_HELPFUL", "CURRENTLY_RATED_NOT_HELPFUL"}
        scored_indices = [i for i, s in enumerate(statuses) if s in scored_statuses]
        unscored_indices = [i for i, s in enumerate(statuses) if s not in scored_statuses]

        assert all(si < ui for si in scored_indices for ui in unscored_indices), (
            f"Scored notes should appear before unscored. Got statuses: {statuses}"
        )


class TestDetailedAnalysisFilterClassification:
    @pytest.mark.asyncio
    async def test_filter_classification_single(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        uid = inst["user_profile_id"]

        await note_factory(author_id=uid, classification="NOT_MISLEADING")
        await note_factory(author_id=uid, classification="MISINFORMED_OR_POTENTIALLY_MISLEADING")

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/analysis/detailed",
            params={"filter[classification]": "NOT_MISLEADING"},
        )

        assert response.status_code == 200
        data = response.json()
        notes = data["data"]
        assert len(notes) == 1
        assert notes[0]["attributes"]["classification"] == "NOT_MISLEADING"
        assert data["meta"]["count"] == 1

    @pytest.mark.asyncio
    async def test_filter_classification_multiple(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        uid = inst["user_profile_id"]

        await note_factory(author_id=uid, classification="NOT_MISLEADING")
        await note_factory(author_id=uid, classification="MISINFORMED_OR_POTENTIALLY_MISLEADING")

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/analysis/detailed",
            params={
                "filter[classification]": [
                    "NOT_MISLEADING",
                    "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2


class TestDetailedAnalysisFilterStatus:
    @pytest.mark.asyncio
    async def test_filter_status_single(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        uid = inst["user_profile_id"]

        await note_factory(author_id=uid, status="NEEDS_MORE_RATINGS")
        await note_factory(
            author_id=uid,
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=80,
        )

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/analysis/detailed",
            params={"filter[status]": "CURRENTLY_RATED_HELPFUL"},
        )

        assert response.status_code == 200
        data = response.json()
        notes = data["data"]
        assert len(notes) == 1
        assert notes[0]["attributes"]["status"] == "CURRENTLY_RATED_HELPFUL"
        assert data["meta"]["count"] == 1


class TestDetailedAnalysisCombined:
    @pytest.mark.asyncio
    async def test_filter_and_sort_combined(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        uid = inst["user_profile_id"]

        await note_factory(
            author_id=uid,
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
        )
        await note_factory(
            author_id=uid,
            classification="NOT_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=80,
        )
        await note_factory(
            author_id=uid,
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=60,
        )

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/analysis/detailed",
            params={
                "filter[classification]": "NOT_MISLEADING",
                "sort_by": "has_score",
            },
        )

        assert response.status_code == 200
        data = response.json()
        notes = data["data"]
        assert len(notes) == 2
        assert data["meta"]["count"] == 2

        assert notes[0]["attributes"]["status"] == "CURRENTLY_RATED_HELPFUL"
        assert notes[1]["attributes"]["status"] == "NEEDS_MORE_RATINGS"


class TestDetailedAnalysisDefaultBehavior:
    @pytest.mark.asyncio
    async def test_no_params_returns_default_order(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        uid = inst["user_profile_id"]

        await note_factory(author_id=uid, summary="First note")
        await note_factory(author_id=uid, summary="Second note")

        response = await admin_auth_client.get(
            f"/api/v2/simulations/{sim_run['id']}/analysis/detailed"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["meta"]["count"] == 2
