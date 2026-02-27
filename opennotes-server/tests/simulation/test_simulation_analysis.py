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
            platform_community_server_id=f"playground-analysis-{unique}",
            name=f"Analysis Playground {unique}",
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
            name=f"AnalysisOrch_{unique}",
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
            name=f"AnalysisAgent_{unique}",
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
                display_name=display_name or f"AnalysisUser_{unique}",
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
    ) -> dict:
        async with get_session_maker()() as session:
            note = Note(
                author_id=author_id,
                community_server_id=playground_community["id"],
                summary="Test analysis note",
                classification=classification,
                status=status,
                helpfulness_score=helpfulness_score,
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return {"id": note.id, "author_id": author_id}

    return _create


@pytest.fixture
async def rating_factory():
    from src.database import get_session_maker
    from src.notes.models import Rating

    async def _create(
        rater_id: UUID,
        note_id: UUID,
        helpfulness_level: str = "HELPFUL",
    ) -> dict:
        async with get_session_maker()() as session:
            rating = Rating(
                rater_id=rater_id,
                note_id=note_id,
                helpfulness_level=helpfulness_level,
            )
            session.add(rating)
            await session.commit()
            await session.refresh(rating)
            return {"id": rating.id, "rater_id": rater_id, "note_id": note_id}

    return _create


@pytest.fixture
async def memory_factory():
    from src.database import get_session_maker
    from src.simulation.models import SimAgentMemory

    async def _create(
        agent_instance_id: UUID,
        recent_actions: list | None = None,
        turn_count: int = 0,
    ) -> dict:
        async with get_session_maker()() as session:
            memory = SimAgentMemory(
                agent_instance_id=agent_instance_id,
                message_history=[],
                turn_count=turn_count,
                recent_actions=recent_actions or [],
            )
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return {"id": memory.id, "agent_instance_id": agent_instance_id}

    return _create


class TestAnalysisRatingDistribution:
    @pytest.mark.asyncio
    async def test_analysis_returns_rating_distribution(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=3)
        inst2 = await agent_instance_factory(state="active", turn_count=5)

        note = await note_factory(author_id=inst1["user_profile_id"])

        await rating_factory(
            rater_id=inst1["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="HELPFUL",
        )
        await rating_factory(
            rater_id=inst2["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="NOT_HELPFUL",
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        dist = data["data"]["attributes"]["rating_distribution"]
        assert dist["total_ratings"] == 2
        assert dist["overall"]["HELPFUL"] == 1
        assert dist["overall"]["NOT_HELPFUL"] == 1

    @pytest.mark.asyncio
    async def test_analysis_per_agent_ratings(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=2)
        inst2 = await agent_instance_factory(state="active", turn_count=4)

        note1 = await note_factory(author_id=inst1["user_profile_id"])
        note2 = await note_factory(author_id=inst2["user_profile_id"])

        await rating_factory(
            rater_id=inst2["user_profile_id"],
            note_id=note1["id"],
            helpfulness_level="HELPFUL",
        )
        await rating_factory(
            rater_id=inst1["user_profile_id"],
            note_id=note2["id"],
            helpfulness_level="SOMEWHAT_HELPFUL",
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        per_agent = response.json()["data"]["attributes"]["rating_distribution"]["per_agent"]
        assert len(per_agent) == 2

        agent_map = {a["agent_instance_id"]: a for a in per_agent}
        inst1_data = agent_map[str(inst1["id"])]
        assert inst1_data["distribution"]["SOMEWHAT_HELPFUL"] == 1
        assert inst1_data["total"] == 1


class TestAnalysisConsensus:
    @pytest.mark.asyncio
    async def test_analysis_consensus_unanimous(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=2)
        inst2 = await agent_instance_factory(state="active", turn_count=2)

        note = await note_factory(author_id=inst1["user_profile_id"])

        await rating_factory(
            rater_id=inst1["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="HELPFUL",
        )
        await rating_factory(
            rater_id=inst2["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="HELPFUL",
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        consensus = response.json()["data"]["attributes"]["consensus_metrics"]
        assert consensus["mean_agreement"] == 1.0
        assert consensus["notes_with_consensus"] == 1
        assert consensus["notes_with_disagreement"] == 0
        assert consensus["polarization_index"] == 0.0

    @pytest.mark.asyncio
    async def test_analysis_polarization_split(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=2)
        inst2 = await agent_instance_factory(state="active", turn_count=2)

        note = await note_factory(author_id=inst1["user_profile_id"])

        await rating_factory(
            rater_id=inst1["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="HELPFUL",
        )
        await rating_factory(
            rater_id=inst2["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="NOT_HELPFUL",
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        consensus = response.json()["data"]["attributes"]["consensus_metrics"]
        assert consensus["mean_agreement"] == 0.5
        assert consensus["polarization_index"] > 0
        assert consensus["notes_with_disagreement"] == 1


class TestAnalysisScoringCoverage:
    @pytest.mark.asyncio
    async def test_analysis_scoring_coverage(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=3)
        await note_factory(
            author_id=inst["user_profile_id"],
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=75,
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        coverage = response.json()["data"]["attributes"]["scoring_coverage"]
        assert "current_tier" in coverage
        assert "total_scores_computed" in coverage
        assert isinstance(coverage["tiers_reached"], list)
        assert isinstance(coverage["scorers_exercised"], list)
        assert "minimal" in coverage["tiers_reached"]
        assert "BayesianAverageScorer" in coverage["scorers_exercised"]


class TestAnalysisAgentBehavior:
    @pytest.mark.asyncio
    async def test_analysis_per_agent_behavior(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
        memory_factory,
    ):
        inst = await agent_instance_factory(state="active", turn_count=5)
        note = await note_factory(author_id=inst["user_profile_id"])
        await rating_factory(
            rater_id=inst["user_profile_id"],
            note_id=note["id"],
            helpfulness_level="HELPFUL",
        )
        await memory_factory(
            agent_instance_id=inst["id"],
            recent_actions=["write_note", "rate_note", "write_note"],
            turn_count=5,
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        behaviors = response.json()["data"]["attributes"]["agent_behaviors"]
        assert len(behaviors) == 1
        agent = behaviors[0]
        assert agent["agent_instance_id"] == str(inst["id"])
        assert agent["notes_written"] == 1
        assert agent["ratings_given"] == 1
        assert agent["turn_count"] == 5
        assert agent["state"] == "active"
        assert agent["action_distribution"]["write_note"] == 2
        assert agent["action_distribution"]["rate_note"] == 1

    @pytest.mark.asyncio
    async def test_analysis_helpfulness_trend(
        self,
        admin_auth_client,
        sim_run,
        agent_instance_factory,
        note_factory,
        rating_factory,
    ):
        inst1 = await agent_instance_factory(state="active", turn_count=3)
        inst2 = await agent_instance_factory(state="active", turn_count=3)

        note1 = await note_factory(author_id=inst2["user_profile_id"])
        note2 = await note_factory(author_id=inst2["user_profile_id"])

        await rating_factory(
            rater_id=inst1["user_profile_id"],
            note_id=note1["id"],
            helpfulness_level="HELPFUL",
        )
        await rating_factory(
            rater_id=inst1["user_profile_id"],
            note_id=note2["id"],
            helpfulness_level="NOT_HELPFUL",
        )

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        behaviors = response.json()["data"]["attributes"]["agent_behaviors"]
        agent_map = {b["agent_instance_id"]: b for b in behaviors}
        trend = agent_map[str(inst1["id"])]["helpfulness_trend"]
        assert len(trend) == 2
        assert "HELPFUL" in trend
        assert "NOT_HELPFUL" in trend


class TestAnalysisEdgeCases:
    @pytest.mark.asyncio
    async def test_analysis_empty_simulation(
        self,
        admin_auth_client,
        sim_run,
    ):
        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        attrs = response.json()["data"]["attributes"]
        assert attrs["rating_distribution"]["total_ratings"] == 0
        assert attrs["rating_distribution"]["overall"] == {}
        assert attrs["rating_distribution"]["per_agent"] == []
        assert attrs["consensus_metrics"]["total_notes_rated"] == 0
        assert attrs["agent_behaviors"] == []
        assert attrs["note_quality"]["avg_helpfulness_score"] is None

    @pytest.mark.asyncio
    async def test_analysis_not_found(self, admin_auth_client):
        fake_id = str(uuid4())
        response = await admin_auth_client.get(f"/api/v2/simulations/{fake_id}/analysis")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analysis_response_structure(
        self,
        admin_auth_client,
        sim_run,
    ):
        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")

        assert response.status_code == 200
        data = response.json()

        assert data["jsonapi"]["version"] == "1.1"
        assert data["data"]["type"] == "simulation-analysis"
        assert data["data"]["id"] == str(sim_run["id"])

        attrs = data["data"]["attributes"]
        assert "rating_distribution" in attrs
        assert "consensus_metrics" in attrs
        assert "scoring_coverage" in attrs
        assert "agent_behaviors" in attrs
        assert "note_quality" in attrs


class TestAnalysisUnauthenticated:
    @pytest.mark.asyncio
    async def test_analysis_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis")
            assert response.status_code == 401
