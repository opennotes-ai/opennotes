from __future__ import annotations

from uuid import UUID, uuid4

import pytest


@pytest.fixture
async def playground_community():
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        cs = CommunityServer(
            platform="playground",
            platform_community_server_id=f"playground-agg-{unique}",
            name=f"Aggregation Playground {unique}",
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
            name=f"AggOrch_{unique}",
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
async def sim_agent_factory():
    from src.database import get_session_maker
    from src.simulation.models import SimAgent

    async def _create(name=None):
        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            agent = SimAgent(
                name=name or f"Agent_{unique}",
                personality="Test personality",
                model_name="openai:gpt-4o-mini",
            )
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
            return {"id": agent.id, "name": agent.name}

    return _create


@pytest.fixture
async def user_profile_factory():
    from src.database import get_session_maker
    from src.users.profile_models import UserProfile

    async def _create(display_name: str | None = None) -> dict:
        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            profile = UserProfile(
                display_name=display_name or f"AggUser_{unique}",
                is_human=False,
                is_active=True,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return {"id": profile.id, "display_name": profile.display_name}

    return _create


@pytest.fixture
async def multi_instance_factory(sim_run, user_profile_factory):
    from src.database import get_session_maker
    from src.simulation.models import SimAgentInstance

    async def _create(
        agent_profile_id: UUID,
        state: str = "active",
        turn_count: int = 0,
    ) -> dict:
        profile = await user_profile_factory()
        async with get_session_maker()() as session:
            instance = SimAgentInstance(
                simulation_run_id=sim_run["id"],
                agent_profile_id=agent_profile_id,
                user_profile_id=profile["id"],
                state=state,
                turn_count=turn_count,
            )
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return {
                "id": instance.id,
                "agent_profile_id": agent_profile_id,
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
                summary="Test aggregation note",
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
        message_history: list | None = None,
        token_count: int = 0,
        compaction_strategy: str | None = None,
    ) -> dict:
        async with get_session_maker()() as session:
            memory = SimAgentMemory(
                agent_instance_id=agent_instance_id,
                message_history=message_history or [],
                turn_count=turn_count,
                recent_actions=recent_actions or [],
                token_count=token_count,
                compaction_strategy=compaction_strategy,
            )
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return {"id": memory.id, "agent_instance_id": agent_instance_id}

    return _create


@pytest.fixture
async def multi_profile_setup(
    sim_agent_factory,
    multi_instance_factory,
    note_factory,
    rating_factory,
    memory_factory,
):
    profile_a = await sim_agent_factory(name="ProfileA")
    profile_b = await sim_agent_factory(name="ProfileB")
    profile_c = await sim_agent_factory(name="ProfileC")

    inst1 = await multi_instance_factory(profile_a["id"], state="removed", turn_count=10)
    inst2 = await multi_instance_factory(profile_a["id"], state="active", turn_count=5)
    inst3 = await multi_instance_factory(profile_b["id"], state="active", turn_count=8)
    inst4 = await multi_instance_factory(profile_c["id"], state="removed", turn_count=0)

    note_a1 = await note_factory(author_id=inst1["user_profile_id"])
    note_a2 = await note_factory(author_id=inst2["user_profile_id"])
    note_b = await note_factory(author_id=inst3["user_profile_id"])

    await rating_factory(
        rater_id=inst1["user_profile_id"],
        note_id=note_b["id"],
        helpfulness_level="HELPFUL",
    )
    await rating_factory(
        rater_id=inst2["user_profile_id"],
        note_id=note_b["id"],
        helpfulness_level="SOMEWHAT_HELPFUL",
    )
    await rating_factory(
        rater_id=inst3["user_profile_id"],
        note_id=note_a1["id"],
        helpfulness_level="NOT_HELPFUL",
    )

    await memory_factory(
        agent_instance_id=inst1["id"],
        recent_actions=["write_note", "rate_note"],
        turn_count=10,
    )
    await memory_factory(
        agent_instance_id=inst2["id"],
        recent_actions=["write_note", "rate_note", "write_note"],
        turn_count=5,
    )
    await memory_factory(
        agent_instance_id=inst3["id"],
        recent_actions=["write_note", "rate_note"],
        turn_count=8,
    )

    return {
        "profile_a": profile_a,
        "profile_b": profile_b,
        "profile_c": profile_c,
        "inst1": inst1,
        "inst2": inst2,
        "inst3": inst3,
        "inst4": inst4,
        "note_a1": note_a1,
        "note_a2": note_a2,
        "note_b": note_b,
    }


class TestAnalysisAggregationMultiInstance:
    @pytest.mark.asyncio
    async def test_analysis_aggregates_across_instances(
        self,
        admin_auth_client,
        sim_run,
        multi_profile_setup,
    ):
        setup = multi_profile_setup

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        attrs = data["data"]["attributes"]

        behaviors = attrs["agent_behaviors"]
        profile_ids = {b["agent_profile_id"] for b in behaviors}
        assert len(behaviors) == 2, (
            f"Expected 2 profiles (A and B), got {len(behaviors)}: {profile_ids}"
        )

        assert str(setup["profile_c"]["id"]) not in profile_ids

        behavior_a = next(
            b for b in behaviors if b["agent_profile_id"] == str(setup["profile_a"]["id"])
        )
        assert behavior_a["turn_count"] == 15
        assert behavior_a["notes_written"] == 2
        assert behavior_a["ratings_given"] == 2

        behavior_b = next(
            b for b in behaviors if b["agent_profile_id"] == str(setup["profile_b"]["id"])
        )
        assert behavior_b["turn_count"] == 8
        assert behavior_b["notes_written"] == 1
        assert behavior_b["ratings_given"] == 1

    @pytest.mark.asyncio
    async def test_rating_distribution_per_agent_by_profile(
        self,
        admin_auth_client,
        sim_run,
        multi_profile_setup,
    ):
        setup = multi_profile_setup

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")
        assert response.status_code == 200

        dist = response.json()["data"]["attributes"]["rating_distribution"]
        per_agent = dist["per_agent"]
        per_agent_ids = {pa["agent_profile_id"] for pa in per_agent}

        assert len(per_agent) == 2
        assert str(setup["profile_c"]["id"]) not in per_agent_ids

        agent_a = next(
            pa for pa in per_agent if pa["agent_profile_id"] == str(setup["profile_a"]["id"])
        )
        assert agent_a["total"] == 2
        assert agent_a["distribution"]["HELPFUL"] == 1
        assert agent_a["distribution"]["SOMEWHAT_HELPFUL"] == 1


class TestProgressCountsByProfile:
    @pytest.mark.asyncio
    async def test_progress_active_agents_counts_profiles(
        self,
        admin_auth_client,
        sim_run,
        multi_profile_setup,
    ):
        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/progress")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        attrs = response.json()["data"]["attributes"]

        assert attrs["active_agents"] == 2, (
            f"Expected 2 active profiles (A and B), got {attrs['active_agents']}"
        )

        assert attrs["turns_completed"] == 23
        assert attrs["notes_written"] == 3
        assert attrs["ratings_given"] == 3


class TestResultsUsesAgentProfileId:
    @pytest.mark.asyncio
    async def test_results_include_agent_profile_id(
        self,
        admin_auth_client,
        sim_run,
        multi_profile_setup,
    ):
        setup = multi_profile_setup

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/results")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        notes = data["data"]
        assert len(notes) == 3

        valid_profile_ids = {
            str(setup["profile_a"]["id"]),
            str(setup["profile_b"]["id"]),
        }

        for note_resource in notes:
            agent_profile_id = note_resource["attributes"]["agent_profile_id"]
            assert agent_profile_id != "", f"Note {note_resource['id']} has empty agent_profile_id"
            assert agent_profile_id in valid_profile_ids, (
                f"Note {note_resource['id']} has unexpected agent_profile_id {agent_profile_id}"
            )


class TestZeroActivityExclusion:
    @pytest.mark.asyncio
    async def test_zero_activity_excluded_from_analysis(
        self,
        admin_auth_client,
        sim_run,
        multi_profile_setup,
    ):
        setup = multi_profile_setup
        zero_activity_id = str(setup["profile_c"]["id"])

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/analysis")
        assert response.status_code == 200

        attrs = response.json()["data"]["attributes"]

        behavior_ids = {b["agent_profile_id"] for b in attrs["agent_behaviors"]}
        assert zero_activity_id not in behavior_ids

        per_agent_ids = {pa["agent_profile_id"] for pa in attrs["rating_distribution"]["per_agent"]}
        assert zero_activity_id not in per_agent_ids

    @pytest.mark.asyncio
    async def test_zero_activity_excluded_from_progress(
        self,
        admin_auth_client,
        sim_run,
        sim_agent_factory,
        multi_instance_factory,
    ):
        await sim_agent_factory(name="ZeroOnly")
        zero_profile = await sim_agent_factory(name="ZeroOnly2")
        await multi_instance_factory(zero_profile["id"], state="removed", turn_count=0)

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/progress")
        assert response.status_code == 200

        attrs = response.json()["data"]["attributes"]
        assert attrs["active_agents"] == 0

    @pytest.mark.asyncio
    async def test_zero_activity_excluded_from_results(
        self,
        admin_auth_client,
        sim_run,
        sim_agent_factory,
        multi_instance_factory,
    ):
        zero_profile = await sim_agent_factory(name="ZeroResults")
        await multi_instance_factory(zero_profile["id"], state="active", turn_count=0)

        response = await admin_auth_client.get(f"/api/v2/simulations/{sim_run['id']}/results")
        assert response.status_code == 200

        data = response.json()
        assert data["data"] == []
